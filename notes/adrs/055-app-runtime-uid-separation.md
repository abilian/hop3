# ADR 055: App-Runtime UID Separation

- **Status**: Proposed
- **Type**: Architecture
- **Created**: 2026-07-08
- **Related-ADRs**: [010](./010-security-and-resilience.md) (security and resilience: the unprivileged-`hop3`-user model), [041](./041-privileged-operations-agent.md) (privileged operations agent: whose `SO_PEERCRED` boundary this ADR makes real), [046](./046-declarative-app-resources.md) (declarative app resources: cgroup/mount ops keyed by app), [048](./048-server-config-and-secret-storage.md) (server config and secret storage: the secrets this ADR stops apps from reading), [017](./017-agent-based-architecture.md) (agent-based architecture)

## Context

Hop3 runs its control plane (`hop3-server`, the uWSGI Emperor, the git-push hooks) as the unprivileged `hop3` system user. [ADR 010](./010-security-and-resilience.md) establishes this: `hop3-server` holds no elevated privileges, with every kernel-boundary action routed through `hop3-rootd` ([ADR 041](./041-privileged-operations-agent.md)), whose entire authentication model is `SO_PEERCRED`: the daemon reads the connecting peer's UID from the socket and admits only `hop3` (and `root` for diagnostics). [ADR 041](./041-privileged-operations-agent.md) states its trust model in one line: *"hop3-server compromise = total compromise"*. It drops per-operation authorization on the grounds that the sole caller is the trusted orchestrator.

That reasoning holds only if `hop3-server` is the *only* thing running as the `hop3` user. It is not.

Native (non-Docker) apps run as `hop3`. The uWSGI Emperor is launched by a systemd unit as `User=hop3` (`ExecStart=…/uwsgi --emperor /home/hop3/uwsgi-enabled`), and each app vassal takes its `uid`/`gid` from the running process's own identity: `run/uwsgi/worker.py` sets `("uid", pwd.getpwuid(os.getuid()).pw_name)`. An unprivileged Emperor cannot setuid a vassal to any other user, so every native app process is `hop3:hop3`. Hop3 deliberately does not containerize native apps (no per-app namespace, no `PrivateTmp`), so `/run/hop3-rootd/socket` and the whole `hop3` home are visible to them.

The consequences are structural:

- **The rootd auth boundary is defeated.** Any native app can `connect("/run/hop3-rootd/socket")`. It passes both `SO_PEERCRED` (UID is `hop3`) and the `0660 root:hop3` socket mode (GID is `hop3`), and can invoke every privileged operation directly, bypassing `hop3-server`. This is an escalation from untrusted app code to root, worse than the "compromised orchestrator" case [ADR 041](./041-privileged-operations-agent.md) reasons about: an app need compromise nothing.
- **`app_name` is caller-asserted with no ownership binding.** rootd validates the *shape* of `app_name`, never that the caller owns it ([ADR 041](./041-privileged-operations-agent.md) §1 accepts this for a compromised server). So one app can act on another: `cgroup.remove(app_name="victim")` SIGKILLs a sibling's process tree; `cgroup.set_limits(app_name="victim", memory_max=1)` OOM-strangles it; `firewall.list_rules({app_name:"victim"})` then `firewall.remove_rule` closes its ports; `mount.unmount(app_name="victim", …)` detaches its volume; `postfix.configure(relay_host=…)` repoints all outbound mail. This breaks the platform invariant that apps must coexist without interference.
- **The control plane's secrets are readable by every app.** The auth-token database (`/home/hop3/hop3.db`), every app's injected `[env]`, and all addon credentials ([ADR 048](./048-server-config-and-secret-storage.md)) are owned by `hop3`. A process running *as* `hop3` reads them regardless of file mode. So a single hostile or compromised app reads every other app's secrets and the platform's own auth tokens.

The shared UID collapses two trust domains that must be distinct: the **control plane** (trusted; may call rootd; owns secrets) and the **app runtime** (untrusted; runs arbitrary user-supplied code). `SO_PEERCRED` is the right primitive; it has simply been pointed at a UID that both domains share.

Docker-deployed apps are unaffected: they run in their own mount and user namespaces and never see the host socket or home. The native path (Hop3's flagship production path) is the subject of this ADR.

## Decision

Native app processes run as a dedicated app-runtime identity distinct from the `hop3` orchestrator user, under a **per-app user**. No app-runtime user is a member of the `hop3` group. The `hop3` user remains the sole member of rootd's trust domain.

This makes [ADR 041](./041-privileged-operations-agent.md)'s `SO_PEERCRED` model true as written: `hop3-server` is once again the only non-root peer that can reach rootd, so rootd's "no per-op authorization" decision is sound.

### 1. Two trust domains

| Domain | Identity | May call rootd? | Owns secrets? | Runs |
|---|---|---|---|---|
| Control plane | `hop3` user / group | yes (`SO_PEERCRED`) | yes (`hop3.db`, `[env]`, addon creds) | `hop3-server`, uWSGI Emperor, git hooks, builders |
| App runtime | per-app user `hop3-app-<name>` | no | only its own | uWSGI vassals, app subprocesses |

The boundary between them is a real UID/GID boundary enforced by the kernel. An app-runtime user can read only what it is explicitly granted, cannot open the rootd socket, and cannot read the control plane's database or another app's tree.

### 2. Per-app users

Each app gets its own user and primary group, `hop3-app-<name>` (name derived from the validated app id; the same identifier rootd already validates). Per-app (rather than one shared app user) because the finding above is squarely about *inter-app* interference: a single shared `hop3-apps` user would fix the rootd hole and the control-plane secret exposure, but would leave every app able to read and kill every other app. The platform's premise is several real apps on one box; isolation between them is the point.

Lifecycle:

- **Create** on first deploy of an app (idempotent; a redeploy reuses the existing user).
- **Delete** on `hop3 app destroy`, as part of teardown (see §7).

User and group creation and deletion are privileged rootd operations (see §4 and Open Questions).

### 3. Filesystem ownership and permission model

The deployer writes an app's tree as `hop3`; the app process reads and writes it as `hop3-app-<name>`. The two coexist through ownership and a shared per-app group:

```
/home/hop3/apps/<name>/
├── git/    hop3:hop3            0750   # bare repo: deployer only; app never reads
├── src/    hop3:hop3-app-<name> 0750   # deployer writes; app reads (group r-x)
├── venv/   hop3:hop3-app-<name> 0750   # deployer writes; app reads (group r-x)
├── data/   hop3-app-<name>:hop3-app-<name> 0700  # app read/write; deployer via group/root
└── log/    hop3-app-<name>:hop3 2750  # app writes; hop3 reads via group (setgid)
```

Principles:

- **Deploy-time artifacts (`src`, `venv`) are owned by `hop3`, group-readable by the app.** The control plane produces them; the app only consumes them. The app cannot modify its own code at runtime.
- **Runtime state (`data`) is owned by the app user.** The control plane does not need to read app data during normal operation; when it must (backups, teardown), it acts through rootd or membership arrangements, never by sharing the app's UID.
- **Logs stay readable by the control plane**, so `hop3 app logs` works, without `hop3` joining any app's group. `log/` belongs to the app user with group `hop3` and the setgid bit, so every file the app creates there inherits group `hop3` and is written `0640`. The vassal sets no `logfile-chown`, which would hand the group back to the app. The asymmetry holds: the control plane reads down into an app, and an app never reads up or sideways.

The precise scheme (POSIX groups vs ACLs, and how apps reach addon Unix sockets such as PostgreSQL/Redis) is an open question (§Open questions); the constraint it must satisfy is the read-down / no-read-up / no-read-sideways property above.

The app user must also be able to reach its tree: `/home/hop3` is `0750` today, which stops `hop3-app-<name>` at the first directory. Traverse-only access (`o+x`, or a group granting `x`) on `/home/hop3` and `/home/hop3/apps` is enough, since each app directory below carries its own mode.

### 4. Process launch and the privilege to change UID

Switching a process to a *different* unprivileged UID requires `CAP_SETUID`/`CAP_SETGID`, which the `hop3` user does not hold. So the Emperor as currently configured (an unprivileged `hop3` process) cannot drop vassals to per-app users. The privilege has to come from somewhere. Three shapes are possible, in order of preference:

1. **Capability-scoped Emperor, with the drop done by a wrapper.** The Emperor unit runs as `hop3` with exactly `AmbientCapabilities=CAP_SETUID CAP_SETGID` and nothing else. uWSGI's `emperor-wrapper` starts each vassal through a small root-owned script that calls `setpriv` to become `hop3-app-<name>`, clear the inheritable and ambient sets, and set `no_new_privs`, then `exec`s uWSGI. The Emperor keeps the two identity-changing capabilities; the app receives none.
2. **Root Emperor dropping per vassal.** `User=root` on the Emperor unit; uWSGI drops each vassal to the vassal's declared `uid`/`gid`. The standard uWSGI deployment, and simple, at the cost of a full-root master process: a larger surface than (1) and a partial step back from [ADR 010](./010-security-and-resilience.md)'s "no root control-plane process".
3. **rootd-mediated spawn.** A future `process.*` op family spawns vassals at the requested UID, keeping the single root boundary rootd already owns. Purest, but couples rootd to process lifecycle and is a materially larger rootd surface; deferred.

This ADR selects **(1)**: it keeps the root surface to two capabilities on one unit, and leaves rootd's boundary as the only *general* privileged path.

**Why the drop cannot be left to uWSGI.** uWSGI applies a vassal's `uid`/`gid` only when it runs as uid 0, and ignores them otherwise without logging anything. Given the capabilities alone, a `hop3` Emperor starts every vassal as `hop3`, and the vassal inherits the Emperor's ambient capabilities unchanged, down to its workers and `attach-daemon` children. The kernel clears capabilities on a switch *from* uid 0, never on one between two unprivileged uids. With `CAP_SETUID` still held, app code can call `setuid(0)`. Configuring `uid` in the vassal and granting the Emperor capabilities is therefore worse than today: it turns rootd's reachability into root itself. The wrapper performs the drop outside uWSGI, so it does not depend on uWSGI's check, and it carries over unchanged to any process runner that can start a command.

**Measured.** `scripts/emperor-caps-probe.py` runs each variant in the e2e image and reports every process below the Emperor (uWSGI 2.0.31):

| Emperor | App processes run as | App holds capabilities | `setuid(0)` from app code | Reaches a `0660 root:hop3` socket | Reload and removal |
|---|---|---|---|---|---|
| `hop3` + setuid, setgid, chown, dac_override | `hop3` | all four | succeeds | yes | work |
| root (option 2) | the app user | none | refused | no | work |
| `hop3` + setuid, setgid, wrapper (option 1) | the app user | none, `no_new_privs` set | refused | no | work |

With fewer capabilities and no wrapper, the vassal does not start: the Emperor, still `hop3`, opens the log in the app-owned `log/` before a drop that never comes.

**Consequences for the launch path.**

- The wrapper derives the app user from the vassal file's name and refuses any other invocation. It is owned by root, since the Emperor runs it with the power to become any user.
- uWSGI reads the vassal file after the drop, as the app user, so the file is `hop3:hop3-app-<name>` `0640`. That also keeps one app from reading another's vassal file, which carries its environment.
- The deployer verifies after start that the app's processes run as `hop3-app-<name>`, and fails the deploy otherwise. uWSGI's silence on an ignored `uid` is how the original form of option 1 would have shipped unnoticed.
- The control plane loses two things it does today as `hop3`: it can no longer read an app process's `/proc/<pid>/cwd` or send it a signal. The reaper, which matches processes by command line and cwd and kills them itself, stops working for native apps. It is replaced by something simpler and exact: an app's processes are the processes running as `hop3-app-<name>`, which `/proc/<pid>/status` shows to any user, and killing them is a rootd operation (§7). The same uid match feeds `cgroup.attach_pids` for apps with resource limits.
- The Emperor still reloads and stops a vassal running as another user (measured), although it cannot signal it: uWSGI drives both through the pipe it shares with each vassal. A hung vassal that ignores the graceful stop cannot be killed by the Emperor across uids, which is the other reason the kill belongs to rootd.

Whichever mechanism is chosen, the vassal ends up as `hop3-app-<name>:hop3-app-<name>`, and that identity is what `SO_PEERCRED` sees at the rootd socket: exactly the identity rootd must refuse.

### 5. The rootd boundary, restored

Two changes enforce the separation at the daemon:

- App-runtime users are **not** in the `hop3` group, so the `0660 root:hop3` socket mode denies them at the OS layer before `SO_PEERCRED` is even consulted.
- rootd's allowed-UID set stays `{hop3, root}` (already the case; `server.py:_resolve_allowed_uids`). No app UID is ever added.

With apps outside both gates, rootd again has a single trusted non-root caller. Its documented model (structural validation, no per-op authorization, `app_name` taken on trust) is then correct, because the only party that can assert an `app_name` is the orchestrator that legitimately owns all of them. This ADR removes the untrusted callers that would have required per-op authorization.

### 6. Secret and environment isolation

Once app users are distinct, the control plane's secret store ([ADR 048](./048-server-config-and-secret-storage.md): the auth-token database and per-app `[env]`) is no longer readable by app processes: it is `hop3`-owned and no app shares that UID. The guarantee is: an app reads its own secrets and no others, and never the platform's.

**A secret never travels on a command line.** Any local user can read any process's `/proc/<pid>/cmdline`, whatever its owner; `/proc/<pid>/environ` is readable only by the owner. Separate users therefore protect an environment only if it is delivered as an environment. `attach-daemon` workers do not inherit the vassal's `env`, so the platform writes every variable as an `export` on the daemon's shell line, and uWSGI keeps that `/bin/sh -c` alive as the daemon's parent. A planted secret is readable by `nobody` for the app's whole life (measured). This holds on every native install whether or not this ADR lands: any local user, `www-data` included, reads every app's `[env]` with `ps`.

Delivery is therefore by file. The platform writes the app's environment to a file the app user alone can read (in the app's tree, `hop3:hop3-app-<name>` `0640`, like the vassal file), and the start line sources it by path (`set -a; . <file>; set +a; exec <command>`). In-process workers keep uWSGI's `env`, which lives in the `0640` vassal file and reaches only the vassal's own environment.

### 7. Teardown completeness

`hop3 app destroy` must leave no residue, per the platform's teardown discipline. For UID separation this adds: kill the app's processes, then delete the app user and its group. The kill is a rootd operation keyed by the app's name, which rootd maps to `hop3-app-<name>` and applies to every process of that uid. A uid cannot be shed by forking, so nothing escapes it, and it covers apps that have no cgroup (only apps with resource limits get one). A leftover user is both clutter and a latent UID-reuse hazard: a future app that reused the UID would inherit stale file ownership. Teardown removes the user only after its processes are confirmed gone and its tree removed, and verifies the user is absent (the same "verify, don't assume" stance rootd applies to mounts and cgroups). User deletion is privileged, so it is a rootd operation.

### 8. Migration

Existing installs run every app as `hop3`. The migration runs per app, on upgrade or next deploy:

1. Create `hop3-app-<name>`.
2. Re-`chown`/`chmod` the app tree to the §3 model.
3. Reconfigure the Emperor unit for the §4 mechanism and regenerate the vassal with the new `uid`/`gid`.
4. Restart the vassal under its new identity.

The window is per-app and each step is idempotent, so a partially migrated box is well-defined: un-migrated apps keep running as `hop3` (no worse than today) until their turn. The Emperor-unit privilege change (§4) is the one host-level step and lands once.

### 9. Non-goals

- **Full container-grade isolation** (per-app mount/network/PID namespaces) is out of scope. UID separation is the minimal change that closes the auth hole and the cross-app read/kill surface; namespace isolation is a separate, heavier decision (and Hop3 avoids Docker's complexity on the native path by design).
- **Changing rootd's protocol or authentication.** The operation set grows by the app-user lifecycle (create a user, delete it, kill its processes), each keyed by an app name rootd already validates. The wire protocol, the `SO_PEERCRED` model and the validation rules stay as they are.

## Consequences

### Positive

- **The rootd `SO_PEERCRED` boundary becomes real**, and [ADR 041](./041-privileged-operations-agent.md)'s "no per-op authorization" is sound. Untrusted app code can no longer reach root through rootd.
- **Least privilege is restored end to end**: an app is confined to its own user, matching [ADR 010](./010-security-and-resilience.md)'s original intent that a control-plane compromise (or here, hostile app) is bounded.
- **Apps cannot read or kill each other**, nor read the control plane's auth-token database and secrets: satisfying the platform's non-interference and secret-isolation requirements.
- **Cleaner mental model**: "the control plane may read down into an app; an app reads only itself."

### Negative

- **Per-app user lifecycle machinery** (create/delete/verify), with its teardown and UID-reuse edges, are new code and new failure modes.
- **A privileged process-launch surface reappears**: two capabilities on the Emperor unit (§4 option 1), or a root Emperor (option 2). Smaller than an unrestricted root control plane, but larger than today's fully-unprivileged Emperor.
- **The permission model is more intricate** (per-app groups or ACLs, addon-socket access), with more ways to misconfigure than a single shared UID.
- **Migration touches every app tree** (re-chown) and the Emperor unit once.

### Operational

- `hop3 app destroy` now also removes a system user; operators will see `hop3-app-*` users on the box and should not manage them by hand (the same "operator manages Hop3, Hop3 manages the server" contract as [ADR 041](./041-privileged-operations-agent.md) §6).
- Debugging shifts: `ps`/`journalctl` show per-app users, which aids attribution but changes muscle memory.
- Backups and any control-plane read of app `data` must go through the sanctioned path (group read-down or rootd). Shared ownership is not a valid assumption.

## Alternatives considered

### A. Single shared app user (`hop3-apps`) for all apps

The alternative is one non-`hop3` user shared by every app. Rejected as the end state, accepted as a valid first increment. It fixes the rootd hole (apps are no longer `hop3`) and the control-plane secret exposure, at a fraction of the lifecycle cost. It does not fix inter-app interference: every app still shares one UID, so app A can still read and kill app B. Given the finding was specifically cross-app compromise and the platform advertises multiple coexisting apps, per-app users are the target; a shared app user is an acceptable milestone on the way if per-app lifecycle needs to land later.

### B. Keep the shared UID, add a token/secret for `hop3-server` → rootd

Have `hop3-server` present a secret rootd checks, so rootd distinguishes it from apps. **Rejected.** A secret that `hop3-server` holds is readable by anything running as the same UID: the apps. There is no secret the orchestrator can keep from a process that shares its user. The boundary must be a UID boundary.

### C. Per-operation authorization / policy in rootd

Have rootd verify that a caller owns the `app_name` it acts on. **Rejected** (and already rejected in [ADR 041](./041-privileged-operations-agent.md) §G). It cannot work while callers share a UID (rootd cannot tell which same-UID process is which app). It is unnecessary once callers are separated: with apps out of the trust domain, `hop3-server` is again the sole caller and legitimately owns every app.

### D. Per-app namespaces / containers for native apps

`unshare` per-app mount/network/user namespaces, or run natives in containers. **Rejected as the mechanism here.** It is a far larger change that reintroduces most of the Docker complexity Hop3 avoids on the native path. It still needs a privileged step to set up. UID separation is the minimal, sufficient fix for the auth and interference problems; namespace isolation, if pursued, is a separate ADR building on this one.

### E. Route vassal spawning through rootd (`process.*` ops)

The alternative is a rootd op family that spawns vassals at a requested UID, preserving a single root boundary. **Deferred.** It is the purest fit with [ADR 041](./041-privileged-operations-agent.md)'s "one kernel boundary" but couples rootd to process lifecycle and adds a large new privileged surface; the capability-scoped Emperor (§4.1) achieves the same isolation with far less new code.

## Open questions

1. **UID/GID allocation.** Dynamic allocation from a reserved range, or deterministic derivation from the app id? Reuse safety after `destroy` (a new app must never inherit a deleted app's UID while any stale file remains). Range sizing for many apps on one host.
2. **Emperor privilege mechanism.** Settled in §4: `CAP_SETUID` and `CAP_SETGID` on the Emperor, with the drop performed by a `setpriv` wrapper. `CAP_CHOWN` and `CAP_DAC_OVERRIDE` are not needed once the app user owns its log directory and does its own opening. A replacement process runner may make the wrapper unnecessary; that is its own decision.
3. **Permission scheme for shared reads.** POSIX groups are enough for what is settled: `src` and `venv` through the app's own group, logs through a setgid `hop3` group (§3). Addons are reached over TCP on `127.0.0.1`, so no app needs an addon's Unix socket. Still open: how the control plane reads `data/` (`0700`, app-owned) for backups, through rootd or by a group arrangement that keeps the no-read-up property.
4. **Interaction with ADR 046 resources.** Finding an app's processes is settled by uid (§4), which also retires the `cwd` matching the [ADR 046](./046-declarative-app-resources.md) note describes. Still open: `[[volumes]]` `bind`/`tmpfs` mountpoint ownership must land under the app user.
5. **Secret delivery ([ADR 048](./048-server-config-and-secret-storage.md)).** Settled in §6: by file, sourced by path, never on a command line.
6. **Builds run recipe code as the control plane.** Git-push and the build run as `hop3`, and a build executes code the recipe controls: `before-build` hooks, package-manager install scripts, Nix builders' shell phases. Until builds drop to the app user too, a hostile recipe reaches rootd and the control plane's secrets at build time, which is the exact hole this ADR closes at runtime. `hop3 run`, which executes app commands through `build_app_env`, has the same shape. Nix does not isolate it either: Hop3 installs Nix single-user, owned by `hop3`, with `sandbox = relaxed`, so derivations build as `hop3`.

   **Proposed answer, in two layers.**

   - **Identity first.** Every step that executes recipe code (hooks, package-manager installs, toolchain builds, Nix builds, `hop3 run`) goes through the same `setpriv` drop as the runtime (§4), as `hop3-app-<name>`. Orchestration stays with `hop3`: it decides what runs, reads the result, and never executes recipe code itself. The build needs to write `src/` and `venv/`, while §3 requires that the app cannot modify its code at runtime. A rootd operation keyed by the app name closes the gap: after a successful build and before the app starts, it *seals* the build output to `hop3:hop3-app-<name>` `0750`. The build writes as the app user; the running app finds its code read-only.
   - **A sandbox second, as defence in depth.** A namespace sandbox around each build step hides everything but the app's own tree and the toolchains, with the network allowed. It narrows what a build can see; it does not replace the identity, because an escape from a sandbox run as `hop3` lands as `hop3`, while an escape from one run as the app user lands as the app user. It is also a larger piece of work: native builds need the network, system toolchains and package caches, and Ubuntu 24.04 restricts unprivileged user namespaces through AppArmor, so a bubblewrap-style sandbox needs a profile or a privileged helper. It belongs with alternative D.

   Adopting the first layer moves build steps from the control-plane row of §1's table to the app-runtime row.

7. **Non-uWSGI deployers.** Static-file and Docker-Compose deployers: static is served by nginx (no app process, no change); Docker is already isolated. Confirm no other native deployer runs app code as `hop3`.

## References

- [ADR 010](./010-security-and-resilience.md): security and resilience (the unprivileged-`hop3` model this ADR completes)
- [ADR 041](./041-privileged-operations-agent.md): privileged operations agent (the `SO_PEERCRED` boundary this ADR makes real; §1 threat model, §G rejected policy layer)
- [ADR 046](./046-declarative-app-resources.md): declarative app resources (cgroup/mount ops keyed by app, which must track the new UID)
- [ADR 048](./048-server-config-and-secret-storage.md): server config and secret storage (the secrets app users must no longer read)
- [ADR 017](./017-agent-based-architecture.md): agent-based architecture
- `packages/hop3-server/src/hop3/run/uwsgi/worker.py`: vassal `uid`/`gid` generation
- `packages/hop3-installer/src/hop3_installer/nginx_templates.py`: the `User=hop3` Emperor unit
