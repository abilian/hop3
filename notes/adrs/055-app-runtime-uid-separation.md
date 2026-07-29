# ADR 055: App-Runtime UID Separation

- **Status**: Proposed
- **Type**: Architecture
- **Created**: 2026-07-08
- **Related-ADRs**: [010](./010-security-and-resilience.md) (security and resilience: the unprivileged-`hop3`-user model), [041](./041-privileged-operations-agent.md) (privileged operations agent: whose `SO_PEERCRED` boundary this ADR makes real), [046](./046-declarative-app-resources.md) (declarative app resources: cgroup/mount ops keyed by app), [048](./048-server-config-and-secret-storage.md) (server config and secret storage: the secrets this ADR stops apps from reading), [017](./017-agent-based-architecture.md) (agent-based architecture)

## Context

Hop3 runs its control plane (`hop3-server`, the uWSGI Emperor, the git-push hooks) as the unprivileged `hop3` system user. [ADR 010](./010-security-and-resilience.md) establishes this: `hop3-server` holds no elevated privileges, and every kernel-boundary action is routed through `hop3-rootd` ([ADR 041](./041-privileged-operations-agent.md)), whose entire authentication model is `SO_PEERCRED`: the daemon reads the connecting peer's UID from the socket and admits only `hop3` (and `root` for diagnostics). [ADR 041](./041-privileged-operations-agent.md) states its trust model plainly: *"hop3-server compromise = total compromise"*. It drops per-operation authorization on the grounds that the sole caller is the trusted orchestrator.

That reasoning holds only if `hop3-server` is the *only* thing running as the `hop3` user. It is not.

Native (non-Docker) apps run as `hop3`. The uWSGI Emperor is launched by a systemd unit as `User=hop3` (`ExecStart=…/uwsgi --emperor /home/hop3/uwsgi-enabled`), and each app vassal takes its `uid`/`gid` from the running process's own identity: `run/uwsgi/worker.py` sets `("uid", pwd.getpwuid(os.getuid()).pw_name)`. An unprivileged Emperor cannot setuid a vassal to any other user, so every native app process is `hop3:hop3`. Hop3 deliberately does not containerize native apps (no per-app namespace, no `PrivateTmp`), so `/run/hop3-rootd/socket` and the whole `hop3` home are visible to them.

The consequences are structural:

- **The rootd auth boundary is defeated.** Any native app can `connect("/run/hop3-rootd/socket")`. It passes both `SO_PEERCRED` (UID is `hop3`) and the `0660 root:hop3` socket mode (GID is `hop3`), and can invoke every privileged operation directly, bypassing `hop3-server`. This is an escalation from untrusted app code to root, worse than the "compromised orchestrator" case [ADR 041](./041-privileged-operations-agent.md) reasons about: an app need compromise nothing.
- **`app_name` is caller-asserted with no ownership binding.** rootd validates the *shape* of `app_name`, never that the caller owns it ([ADR 041](./041-privileged-operations-agent.md) §1 accepts this for a compromised server). So one app can act on another: `cgroup.remove(app_name="victim")` SIGKILLs a sibling's process tree; `cgroup.set_limits(app_name="victim", memory_max=1)` OOM-strangles it; `firewall.list_rules({app_name:"victim"})` then `firewall.remove_rule` closes its ports; `mount.unmount(app_name="victim", …)` detaches its volume; `postfix.configure(relay_host=…)` repoints all outbound mail. This breaks the platform invariant that apps must coexist without interference.
- **The control plane's secrets are readable by every app.** The auth-token database (`/home/hop3/hop3.db`), every app's injected `[env]`, and all addon credentials ([ADR 048](./048-server-config-and-secret-storage.md)) are owned by `hop3`. A process running *as* `hop3` reads them regardless of file mode. So a single hostile or compromised app reads every other app's secrets and the platform's own auth tokens.

The shared UID collapses two trust domains that must be distinct: the **control plane** (trusted; may call rootd; owns secrets) and the **app runtime** (untrusted; runs arbitrary user-supplied code). `SO_PEERCRED` is the right primitive; it has simply been pointed at a UID that both domains share.

Docker-deployed apps are unaffected: they run in their own mount and user namespaces and never see the host socket or home. The native path (Hop3's flagship production path) is the subject of this ADR.

## Decision

Native app processes run as a **dedicated app-runtime identity distinct from the `hop3` orchestrator user**, under a **per-app user**, and no app-runtime user is a member of the `hop3` group. The `hop3` user remains the sole member of rootd's trust domain.

This makes [ADR 041](./041-privileged-operations-agent.md)'s `SO_PEERCRED` model true as written: `hop3-server` is once again the only non-root peer that can reach rootd, so rootd's "no per-op authorization" decision is sound rather than a hole.

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
└── log/    hop3-app-<name>:hop3-app-<name> 0750  # app writes; hop3 reads (see below)
```

Principles:

- **Deploy-time artifacts (`src`, `venv`) are owned by `hop3`, group-readable by the app.** The control plane produces them; the app only consumes them. The app cannot modify its own code at runtime.
- **Runtime state (`data`) is owned by the app user.** The control plane does not need to read app data during normal operation; when it must (backups, teardown), it acts through rootd or membership arrangements rather than by sharing the app's UID.
- **Logs must remain readable by the control plane** so `hop3 app logs` works. Either `hop3` joins each `hop3-app-<name>` group (asymmetric: control plane reads app logs, app cannot read control-plane files), or logs are group-owned `hop3` and group-readable. The asymmetry (control plane may read down into an app, an app may never read up or sideways) is the invariant to preserve.

The precise scheme (POSIX groups vs ACLs, and how apps reach addon Unix sockets such as PostgreSQL/Redis) is an open question (§Open questions); the constraint it must satisfy is the read-down / no-read-up / no-read-sideways property above.

### 4. Process launch and the privilege to change UID

Switching a process to a *different* unprivileged UID requires `CAP_SETUID`/`CAP_SETGID`, which the `hop3` user does not hold. So the Emperor as currently configured (an unprivileged `hop3` process) cannot drop vassals to per-app users. The privilege has to come from somewhere. Three shapes, in order of preference:

1. **Capability-scoped Emperor.** Grant the Emperor unit exactly `AmbientCapabilities=CAP_SETUID CAP_SETGID` (plus `CAP_CHOWN`/`CAP_DAC_OVERRIDE` only if uWSGI's socket/log chowning needs them), `NoNewPrivileges` off for the priv-drop, and nothing else. The Emperor is a master that drops each vassal to its app user: the standard master/worker priv-drop pattern (as nginx's master does), scoped to just the identity-changing capabilities rather than full root.
2. **Root Emperor dropping per vassal.** `User=root` on the Emperor unit; uWSGI drops each vassal to the vassal's declared `uid`/`gid`. Battle-tested and simple, at the cost of a full-root master process: a larger surface than (1) and a partial step back from [ADR 010](./010-security-and-resilience.md)'s "no root control-plane process".
3. **rootd-mediated spawn.** A future `process.*` op family spawns vassals at the requested UID, keeping the single root boundary rootd already owns. Purest, but couples rootd to process lifecycle and is a materially larger rootd surface; deferred.

This ADR selects **(1)**: it changes the smallest amount, keeps the root surface to two capabilities on one unit, and leaves rootd's boundary as the only *general* privileged path. `run/uwsgi/worker.py` changes to set the vassal `uid`/`gid` to `hop3-app-<name>` rather than the deployer's own identity.

Whichever mechanism is chosen, the vassal ends up as `hop3-app-<name>:hop3-app-<name>`, and that identity is what `SO_PEERCRED` sees at the rootd socket: exactly the identity rootd must refuse.

### 5. The rootd boundary, restored

Two changes enforce the separation at the daemon:

- App-runtime users are **not** in the `hop3` group, so the `0660 root:hop3` socket mode denies them at the OS layer before `SO_PEERCRED` is even consulted.
- rootd's allowed-UID set stays `{hop3, root}` (already the case; `server.py:_resolve_allowed_uids`). No app UID is ever added.

With apps outside both gates, rootd again has a single trusted non-root caller. Its documented model (structural validation, no per-op authorization, `app_name` taken on trust) is then correct, because the only party that can assert an `app_name` is the orchestrator that legitimately owns all of them. This ADR removes the untrusted callers that would have required per-op authorization.

### 6. Secret and environment isolation

Once app users are distinct, the control plane's secret store ([ADR 048](./048-server-config-and-secret-storage.md): the auth-token database and per-app `[env]`) is no longer readable by app processes: it is `hop3`-owned and no app shares that UID. Per-app environment and addon credentials are delivered so that only the owning app user can read its own (injected into the vassal environment at drop-time, or written to an app-user-owned file mode `0600`), never into a location a sibling can read. The guarantee is: an app reads its own secrets and no others, and never the platform's.

### 7. Teardown completeness

`hop3 app destroy` must leave no residue, per the platform's teardown discipline. For UID separation this adds: kill the app's processes (rootd already does this via `cgroup.remove`), then delete the app user and its group. A leftover user is both clutter and a latent UID-reuse hazard: a future app that reused the UID would inherit stale file ownership. Teardown removes the user only after its processes are confirmed gone and its tree removed, and verifies the user is absent (the same "verify, don't assume" stance rootd applies to mounts and cgroups). User deletion is privileged, so it is a rootd operation.

### 8. Migration

Existing installs run every app as `hop3`. The migration, per app, on upgrade or next deploy:

1. Create `hop3-app-<name>`.
2. Re-`chown`/`chmod` the app tree to the §3 model.
3. Reconfigure the Emperor unit for the §4 mechanism and regenerate the vassal with the new `uid`/`gid`.
4. Restart the vassal under its new identity.

The window is per-app and each step is idempotent, so a partially migrated box is well-defined: un-migrated apps keep running as `hop3` (no worse than today) until their turn. The Emperor-unit privilege change (§4) is the one host-level step and lands once.

### 9. Non-goals

- **Full container-grade isolation** (per-app mount/network/PID namespaces) is out of scope. UID separation is the minimal change that closes the auth hole and the cross-app read/kill surface; namespace isolation is a separate, heavier decision (and Hop3 avoids Docker's complexity on the native path by design).
- **Changing rootd's operation set or protocol.** This ADR restores rootd's stated model while leaving its wire protocol, ops, and validation unchanged.

## Consequences

### Positive

- **The rootd `SO_PEERCRED` boundary becomes real**, and [ADR 041](./041-privileged-operations-agent.md)'s "no per-op authorization" is sound rather than a hole. Untrusted app code can no longer reach root through rootd.
- **Least privilege is restored end to end**: an app is confined to its own user, matching [ADR 010](./010-security-and-resilience.md)'s original intent that a control-plane compromise (or here, hostile app) is bounded.
- **Apps cannot read or kill each other**, nor read the control plane's auth-token database and secrets: satisfying the platform's non-interference and secret-isolation requirements.
- **Cleaner mental model**: "the control plane may read down into an app; an app reads only itself."

### Negative

- **Per-app user lifecycle machinery** (create/delete/verify), and its teardown and UID-reuse edges, are new code and new failure modes.
- **A privileged process-launch surface reappears**: two capabilities on the Emperor unit (§4 option 1), or a root Emperor (option 2). Smaller than an unrestricted root control plane, but larger than today's fully-unprivileged Emperor.
- **The permission model is more intricate** (per-app groups or ACLs, addon-socket access), with more ways to misconfigure than a single shared UID.
- **Migration touches every app tree** (re-chown) and the Emperor unit once.

### Operational

- `hop3 app destroy` now also removes a system user; operators will see `hop3-app-*` users on the box and should not manage them by hand (the same "operator manages Hop3, Hop3 manages the server" contract as [ADR 041](./041-privileged-operations-agent.md) §6).
- Debugging shifts: `ps`/`journalctl` show per-app users, which aids attribution but changes muscle memory.
- Backups and any control-plane read of app `data` must go through the sanctioned path (group read-down or rootd). Shared ownership is not a valid assumption.

## Alternatives considered

### A. Single shared app user (`hop3-apps`) for all apps

One non-`hop3` user shared by every app. **Rejected as the end state, accepted as a valid first increment.** It fixes the rootd hole (apps are no longer `hop3`) and the control-plane secret exposure, at a fraction of the lifecycle cost. It does not fix inter-app interference: every app still shares one UID, so app A can still read and kill app B. Given the finding was specifically cross-app compromise and the platform advertises multiple coexisting apps, per-app users are the target; a shared app user is an acceptable milestone on the way if per-app lifecycle needs to land later.

### B. Keep the shared UID, add a token/secret for `hop3-server` → rootd

Have `hop3-server` present a secret rootd checks, so rootd distinguishes it from apps. **Rejected.** A secret that `hop3-server` holds is readable by anything running as the same UID: the apps. There is no secret the orchestrator can keep from a process that shares its user. The boundary must be a UID boundary.

### C. Per-operation authorization / policy in rootd

Have rootd verify that a caller owns the `app_name` it acts on. **Rejected** (and already rejected in [ADR 041](./041-privileged-operations-agent.md) §G). It cannot work while callers share a UID (rootd cannot tell which same-UID process is which app), and it is unnecessary once callers are separated: with apps out of the trust domain, `hop3-server` is again the sole caller and legitimately owns every app.

### D. Per-app namespaces / containers for native apps

`unshare` per-app mount/network/user namespaces, or run natives in containers. **Rejected as the mechanism here.** It is a far larger change that reintroduces most of the Docker complexity Hop3 avoids on the native path, and it still needs a privileged step to set up. UID separation is the minimal, sufficient fix for the auth and interference problems; namespace isolation, if pursued, is a separate ADR building on this one.

### E. Route vassal spawning through rootd (`process.*` ops)

A rootd op family that spawns vassals at a requested UID, preserving a single root boundary. **Deferred.** It is the purest fit with [ADR 041](./041-privileged-operations-agent.md)'s "one kernel boundary" but couples rootd to process lifecycle and adds a large new privileged surface; the capability-scoped Emperor (§4.1) achieves the same isolation with far less new code.

## Open questions

1. **UID/GID allocation.** Dynamic allocation from a reserved range, or deterministic derivation from the app id? Reuse safety after `destroy` (a new app must never inherit a deleted app's UID while any stale file remains). Range sizing for many apps on one host.
2. **Emperor privilege mechanism.** Confirm the minimal capability set for §4.1 against uWSGI's actual needs (socket/log chown), or fall back to a root Emperor (§4.2). This interacts with [ADR 041](./041-privileged-operations-agent.md)'s stance on root processes and should be settled with a small experiment.
3. **Permission scheme for shared reads.** POSIX supplementary groups vs ACLs for `src`/`venv` read-down and for app access to addon Unix sockets (PostgreSQL/Redis run as their own users); which composes best with the read-down / no-read-up property.
4. **Interaction with ADR 046 resources.** cgroup `attach_pids`/`remove` must still find and reap the app's processes now that they run under a new UID (the [ADR 046](./046-declarative-app-resources.md) note about matching an `exec`'d binary's `cwd` still applies); `[[volumes]]` `bind`/`tmpfs` mountpoint ownership must land under the app user.
5. **Secret delivery ([ADR 048](./048-server-config-and-secret-storage.md)).** Exact mechanism for per-app env/addon-credential delivery such that only the owning app user can read it: environment injection at drop-time vs an app-user-owned `0600` file.
6. **Git-push and build steps.** These run as `hop3` (control plane); confirm nothing in the build needs the app-user identity, and that the checked-out `src` ends up with the §3 ownership before the vassal starts.
7. **Non-uWSGI deployers.** Static-file and Docker-Compose deployers: static is served by nginx (no app process, no change); Docker is already isolated. Confirm no other native deployer runs app code as `hop3`.

## References

- [ADR 010](./010-security-and-resilience.md): security and resilience (the unprivileged-`hop3` model this ADR completes)
- [ADR 041](./041-privileged-operations-agent.md): privileged operations agent (the `SO_PEERCRED` boundary this ADR makes real; §1 threat model, §G rejected policy layer)
- [ADR 046](./046-declarative-app-resources.md): declarative app resources (cgroup/mount ops keyed by app, which must track the new UID)
- [ADR 048](./048-server-config-and-secret-storage.md): server config and secret storage (the secrets app users must no longer read)
- [ADR 017](./017-agent-based-architecture.md): agent-based architecture
- `packages/hop3-server/src/hop3/run/uwsgi/worker.py`: vassal `uid`/`gid` generation
- `packages/hop3-installer/src/hop3_installer/nginx_templates.py`: the `User=hop3` Emperor unit
