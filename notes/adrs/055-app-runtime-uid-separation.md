# ADR 055: App-Runtime UID Separation

- **Status**: Proposed
- **Type**: Architecture
- **Created**: 2026-07-08
- **Related-ADRs**: [010](./010-security-and-resilience.md) (security and resilience: the unprivileged-`hop3`-user model), [041](./041-privileged-operations-agent.md) (privileged operations agent: whose `SO_PEERCRED` boundary this ADR makes real, and whose op set its §20 extends for this ADR), [046](./046-declarative-app-resources.md) (declarative app resources: cgroup/mount ops keyed by app), [048](./048-server-config-and-secret-storage.md) (server config and secret storage: the secrets this ADR stops apps from reading), [053](./053-nix-closure-lifetime.md) (Nix closure lifetime: the per-app GC roots a build registers), [024](./024-backup-restore-system.md) (backup and restore: which read and write an app's data as its user), [017](./017-agent-based-architecture.md) (agent-based architecture)

## Context

Hop3 runs its control plane (`hop3-server`, the uWSGI Emperor, the git-push hooks) as the unprivileged `hop3` system user. [ADR 010](./010-security-and-resilience.md) establishes this: `hop3-server` holds no elevated privileges, with every kernel-boundary action routed through `hop3-rootd` ([ADR 041](./041-privileged-operations-agent.md)). The daemon's entire authentication model is `SO_PEERCRED`: it reads the connecting peer's UID from the socket and admits only `hop3` (and `root` for diagnostics). [ADR 041](./041-privileged-operations-agent.md) states its trust model in one line: *"hop3-server compromise = total compromise"*. It drops per-operation authorization on the grounds that the sole caller is the trusted orchestrator.

That reasoning holds only if `hop3-server` is the *only* thing running as the `hop3` user. It is not.

Native (non-Docker) apps run as `hop3`. The uWSGI Emperor is launched by a systemd unit as `User=hop3` (`ExecStart=…/uwsgi --emperor /home/hop3/uwsgi-enabled`), and each app vassal takes its `uid`/`gid` from the running process's own identity: `run/uwsgi/worker.py` sets `("uid", pwd.getpwuid(os.getuid()).pw_name)`. An unprivileged Emperor cannot setuid a vassal to any other user, so every native app process is `hop3:hop3`. Hop3 deliberately does not containerize native apps (no per-app namespace, no `PrivateTmp`), so `/run/hop3-rootd/socket` and the whole `hop3` home are visible to them.

The consequences are structural:

- **The rootd auth boundary is defeated.** Any native app can `connect("/run/hop3-rootd/socket")`. It passes both `SO_PEERCRED` (UID is `hop3`) and the `0660 root:hop3` socket mode (GID is `hop3`), and can invoke every privileged operation directly, bypassing `hop3-server`. This is an escalation from untrusted app code to root, worse than the "compromised orchestrator" case [ADR 041](./041-privileged-operations-agent.md) reasons about: an app need compromise nothing.
- **`app_name` is caller-asserted with no ownership binding.** rootd validates the *shape* of `app_name`, never that the caller owns it ([ADR 041](./041-privileged-operations-agent.md) §1 accepts this for a compromised server). So one app can act on another: `cgroup.remove(app_name="victim")` SIGKILLs a sibling's process tree; `cgroup.set_limits(app_name="victim", memory_max=1)` OOM-strangles it; `firewall.list_rules({app_name:"victim"})` then `firewall.remove_rule` closes its ports; `mount.unmount(app_name="victim", …)` detaches its volume; `postfix.configure(relay_host=…)` repoints all outbound mail. This breaks the platform invariant that apps must coexist without interference.
- **The control plane's secrets are readable by every app.** The auth-token database (`/home/hop3/hop3.db`), every app's injected `[env]`, and all addon credentials ([ADR 048](./048-server-config-and-secret-storage.md)) are owned by `hop3`. A process running *as* `hop3` reads them regardless of file mode. So a single hostile or compromised app reads every other app's secrets and the platform's own auth tokens.
- **Builds run recipe code as the control plane.** Git-push and the build run as `hop3`, and a build executes code the recipe controls: `before-build` hooks, package-manager install scripts, the evaluation of a Nix expression. A hostile recipe reaches rootd and the control plane's secrets at build time, before its app ever starts. `hop3 run`, `hop3 app shell`, an app's `check.py` and its admin bootstrap command have the same shape: the control plane starts app code as itself.

The shared UID collapses two trust domains that must be distinct: the **control plane** (trusted; may call rootd; owns secrets) and the **app runtime** (untrusted; runs arbitrary user-supplied code). `SO_PEERCRED` is the right primitive; it has simply been pointed at a UID that both domains share.

Docker-deployed apps are unaffected: they run in their own mount and user namespaces and never see the host socket or home. The native path (Hop3's flagship production path) is the subject of this ADR.

## Decision

Every process that runs app or recipe code runs as a **per-app user**, distinct from the `hop3` orchestrator user: the app's vassals and everything they start, and every one-shot command the platform starts for the app, builds included. No app user is a member of the `hop3` group. The `hop3` user remains the sole member of rootd's trust domain.

This makes [ADR 041](./041-privileged-operations-agent.md)'s `SO_PEERCRED` model true as written: `hop3-server` is once again the only non-root peer that can reach rootd, so rootd's "no per-op authorization" decision is sound.

### 1. Two trust domains

| Domain | Identity | May call rootd? | Owns secrets? | Runs |
|---|---|---|---|---|
| Control plane | `hop3` user / group | yes (`SO_PEERCRED`) | yes (`hop3.db`, `[env]`, addon creds) | `hop3-server`, uWSGI Emperor, git hooks, the orchestration of builds |
| App runtime | per-app user `hop3-app-<name>` | no | only its own | uWSGI vassals and their children, build steps, `hop3 run`, `hop3 app shell`, the app's checks and admin bootstrap, backups of its data |

The boundary between them is a real UID/GID boundary enforced by the kernel. An app-runtime user can read only what it is explicitly granted, cannot open the rootd socket, and cannot read the control plane's database or another app's tree. The control plane decides what runs and reads what comes back; it never runs recipe code itself.

### 2. Per-app users

Each app gets its own user and primary group, `hop3-app-<name>`. Each app gets its own user because the finding above is squarely about *inter-app* interference. A single shared `hop3-apps` user would fix the rootd hole and the control-plane secret exposure, but would leave every app able to read and kill every other app. The platform's premise is several real apps on one box; isolation between them is the point.

**Name.** `hop3-app-<n>`, with `<n>` the app name lowercased. App names allow uppercase and 63 characters, and `useradd` accepts 32, so a longer result is truncated and suffixed with six hex digits of a hash of the full app name. rootd computes the mapping in one function; nothing else derives a user name.

**Allocation.** `useradd --system --user-group`, so the uid and gid come from the distribution's system range (100 to 999 on Debian and Ubuntu), shared with the distribution's packages. That leaves several hundred apps per server once the packages have taken theirs, more than one server holds. A range reserved for apps and allocated by rootd would buy a capacity of Hop3's choosing and uids recognisable on sight, at the price of an allocator and of a range kept clear of every range the distribution, systemd and subordinate ids (`/etc/subuid`) claim. The system range is enough. Its one hazard, a freed uid handed to a later user, is closed by teardown (§7): nothing a deleted app's uid could have written survives it.

**Lifecycle.** All through rootd ([ADR 041](./041-privileged-operations-agent.md) §20):

- **Create** on first deploy, before the first build (idempotent; a redeploy reuses the existing user).
- **Delete** on `hop3 app destroy`, as part of teardown (§7).

rootd records each user it creates and acts on no other. An existing `hop3-app-<n>` that rootd has no record of is a conflict it reports; it never adopts one.

### 3. Filesystem ownership and permission model

The control plane writes an app's tree as `hop3`; the app reads it, and writes its state, as `hop3-app-<name>`. The two coexist through ownership and the app's own group:

```
/home/hop3/apps/<name>/                hop3:hop3-app-<name>             0750
├── git/                               hop3:hop3                        0750  # bare repo: control plane only
├── src/, venv/                        hop3:hop3-app-<name>             0750  # read-only to the app; files 0640, executables 0750
├── data/, volumes/, scratch/,
│   home/, tmp/                        hop3-app-<name>:hop3-app-<name>  0700  # the app's state
├── log/                               hop3-app-<name>:hop3             2750  # app writes; hop3 reads via group (setgid)
└── worker-env/*.env                   hop3:hop3-app-<name>             0640  # read by the app after the drop
/home/hop3/uwsgi-enabled/<vassal>.ini  hop3:hop3-app-<name>             0640  # names the app's user (§4.1)
```

Principles:

- **Code is read-only to the app at run time.** The control plane produces `src` and `venv`; the running app only consumes them.
- **Runtime state (`data` and the volumes) is owned by the app user.** The control plane does not need to read app data during normal operation. When it must (backups, restores), it acts through the app's identity (below), never by sharing the app's UID or joining its group.
- **Logs stay readable by the control plane**, so `hop3 app logs` works, without `hop3` joining any app's group. `log/` belongs to the app user with group `hop3` and the setgid bit, so every file the app creates there inherits group `hop3` and is written `0640`. The vassal sets no `logfile-chown`, which would hand the group back to the app. The asymmetry holds: the control plane reads down into an app, and an app never reads up or sideways.

**Build, then seal.** A build writes `src/` and `venv/`, and its steps run as the app's user (§4.2). rootd hands the build tree to the app's user before the build and *seals* it after, applying the layout above, so the app starts on code it cannot modify. Every build ends with a seal, a failed one included, so the control plane can always replace or remove the tree. The tree the build wrote is hostile input to a root process: a followed link to `hop3.db`, or a setuid bit kept on a file that becomes `hop3`'s, would hand the app the control plane. The seal therefore walks by descriptor and never follows a symbolic link, sets every mode explicitly, clears setuid and setgid bits, removes POSIX ACLs, and runs only once the build's processes are gone.

**How the control plane reads `data/`.** Through the app's identity. A backup runs `tar` as the app's user and receives the archive on a descriptor; a restore unpacks as the app's user. The kernel then bounds what an archive can do to what the app can write: the numeric owners a cross-instance archive records do not apply, so restored files belong to the target app's user, and a link in the archive that points out of the tree reaches nothing the app could not already write.

**What nginx reads.** The files nginx sends itself (a static site, the assets under a PHP document root) are world-readable, and the directories above them traversable, so nginx's user needs no group. Files an interpreter executes are not: a PHP document root's `.php` files keep the app's `0640`, since the app's php-fpm reads them as the app. A world-readable `wp-config.php` would hand its database password to every local user.

**Reaching the tree.** `/home/hop3` is `0750` today, which stops `hop3-app-<name>` at the first directory. Traverse-only access (`o+x`) on `/home/hop3` and `/home/hop3/apps` is enough, since each app directory below carries its own mode.

**Shared reads need groups only.** Code is read through the app's own group, logs through the setgid `hop3` group. Addons are reached over TCP on `127.0.0.1`, so no app needs an addon's Unix socket.

**Volumes.** A `tmpfs` volume is mounted with the app's uid and gid and mode `0700`. A `bind` volume's source is operator data, possibly shared with other software on the host and large, so rootd does not re-own it. How the app's user is granted access to it is open (Open question 1); until it is settled, a native `bind` volume on a separated app fails its deploy with a diagnosis, rather than mounting a source its app cannot read.

### 4. Process launch and the privilege to change UID

Two kinds of process run app code: the long-running vassals, which the uWSGI Emperor starts and which must remain its children, and the one-shot commands the control plane starts for an app (build steps, `hop3 run`, `hop3 app shell`, checks, the admin bootstrap, backups). Switching a process to a *different* unprivileged UID requires `CAP_SETUID`/`CAP_SETGID`, which the `hop3` user does not hold. The two kinds get that privilege from different places.

#### 4.1 Vassals: a capability-scoped Emperor

The Emperor as currently configured (an unprivileged `hop3` process) cannot drop vassals to per-app users. Three shapes are possible, in order of preference:

1. **Capability-scoped Emperor, with the drop done by a wrapper.** The Emperor unit runs as `hop3` with exactly `AmbientCapabilities=CAP_SETUID CAP_SETGID` and nothing else. uWSGI's `emperor-wrapper` starts each vassal through a small root-owned script that calls `setpriv` to become `hop3-app-<name>`, clear the inheritable and ambient sets, and set `no_new_privs`, then `exec`s uWSGI. The Emperor keeps the two identity-changing capabilities; the app receives none.
2. **Root Emperor dropping per vassal.** `User=root` on the Emperor unit; uWSGI drops each vassal to the vassal's declared `uid`/`gid`. The standard uWSGI deployment, and simple, at the cost of a full-root master process: a larger surface than (1) and a partial step back from [ADR 010](./010-security-and-resilience.md)'s "no root control-plane process".
3. **rootd-mediated spawn.** rootd starts each vassal at the requested UID, keeping the single root boundary rootd already owns. It couples rootd to the lifecycle of every long-running process, and a vassal that is not the Emperor's child cannot be reloaded or stopped by it (alternative E).

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

- **The vassal file's group names the user.** The wrapper runs a vassal as the user whose primary group owns the vassal file. Only rootd's seal sets that group: the control plane belongs to no app group and holds no `CAP_CHOWN`. Sealing a vassal is therefore what authorizes it to run as its app, which is uWSGI's own tyrant-mode convention (the identity comes from the vassal file) applied outside uWSGI. The wrapper refuses a file outside `uwsgi-enabled`, not owned by `hop3`, writable by group or others, or whose group is neither `hop3` nor an app group (a `hop3-app-…` group that is the primary group of the user of the same name). A vassal of group `hop3` runs as `hop3` with every capability cleared. Those are the platform's own vassals (the WAF), and an app not yet migrated (§8), which the deploy's uid check then reports.
- **The Emperor's executable is out of `hop3`'s reach.** `CAP_SETUID` lets a process become root, so the Emperor is root-equivalent and the code it runs must be owned by root, as rootd's is. A uWSGI from `hop3`'s own venv would let the control plane rewrite the binary that holds the capability. The wrapper is owned by root for the same reason.
- uWSGI reads the vassal file after the drop, as the app user, so the file is `hop3:hop3-app-<name>` `0640`. That also keeps one app from reading another's vassal file, which carries its environment.
- The deployer verifies after start that the app's processes run as `hop3-app-<name>`, and fails the deploy otherwise. uWSGI's silence on an ignored `uid` is how the original form of option 1 would have shipped unnoticed.
- The control plane loses two things it does today as `hop3`: it can no longer read an app process's `/proc/<pid>/cwd` or send it a signal. The reaper, which matches processes by command line and cwd and kills them itself, stops working for native apps. It is replaced by something simpler and exact: an app's processes are the processes running as `hop3-app-<name>`, which `/proc/<pid>/status` shows to any user, and killing them is a rootd operation (§7). The same uid match feeds `cgroup.attach_pids` for apps with resource limits.
- The Emperor still reloads and stops a vassal running as another user (measured), although it cannot signal it: uWSGI drives both through the pipe it shares with each vassal. A hung vassal that ignores the graceful stop cannot be killed by the Emperor across uids, which is the other reason the kill belongs to rootd.

Whichever mechanism is chosen, the vassal ends up as `hop3-app-<name>:hop3-app-<name>`, and that identity is what `SO_PEERCRED` sees at the rootd socket: exactly the identity rootd must refuse.

#### 4.2 One-shot commands: started by rootd

The Emperor's arrangement does not carry over to the control plane. `hop3-server` holding `CAP_SETUID` would make the process that parses every RPC and every `git push` root-equivalent (alternative F). sudo, the other conventional route, is the dependency rootd exists to retire ([ADR 041](./041-privileged-operations-agent.md) §12). A one-shot command is therefore started by rootd (`app_exec.spawn`, [ADR 041](./041-privileged-operations-agent.md) §20):

- rootd forks, drops to the app's user with the same `setpriv` argument list the vassal wrapper uses (defined once, in rootd, and rendered into the wrapper by the installer), and execs the command. Everything that touches an app path (the working directory, the program) happens after the drop, so a link planted in the tree reaches only what the app's user could reach anyway.
- The command's standard streams, or a pseudo-terminal for `hop3 app shell`, come back to the caller as descriptors, with a control socket that yields the exit code. The environment travels in the request, never on a command line, and rootd does not log it.
- rootd never waits for a command. A small monitor per command waits and reports its status, so a restart of rootd neither kills a running build nor loses its outcome. A caller whose control socket closes without a status reports the command as failed.
- Each command runs in a cgroup of its own under `hop3.slice`, outside rootd's unit. That bounds what killing it reaches: when the caller closes the control socket (a timeout, a dropped connection), the monitor kills that command and its descendants, never the app's other processes. Without systemd (the Docker target, under supervisor) there are no per-service cgroups and the command's process group stands in, which a process that starts a session of its own leaves. Production servers run systemd.

**Builds.** Every step that runs recipe code goes through this path: the toolchains' package installs, the `before-build`, `build` and `after-build` hooks, and Nix evaluation. A build's environment is `build_app_env`'s, as for the run-time commands, never `hop3-server`'s own, which holds `HOP3_SECRET_KEY`. Toolchain caches live in the app's `home/`, so one app's build cannot poison another's.

**Nix.** Hop3 installs Nix multi-user, so a derivation builds as a `nixbld` user inside the daemon's sandbox, isolated from both `hop3` and the app. Under `sandbox = relaxed` a `__noChroot` derivation sees the host's filesystem, but as `nixbld`: it reads what any local user can, never the control plane's files. What the app's identity must cover is the client. `nix-build` evaluates the recipe's expression in its own process, and an expression can read any file its user can (`builtins.readFile`), so the client runs as the app's user, through the path above. It registers the per-app GC roots ([ADR 053](./053-nix-closure-lifetime.md)), which therefore live where the build may write. On hosts without systemd the installer runs `nix-daemon` under the process manager (alternative G).

### 5. The rootd boundary, restored

Two changes enforce the separation at the daemon:

- App-runtime users are **not** in the `hop3` group, so the `0660 root:hop3` socket mode denies them at the OS layer before `SO_PEERCRED` is even consulted.
- rootd's allowed-UID set stays `{hop3, root}` (already the case; `server.py:_resolve_allowed_uids`). No app UID is ever added.

rootd also keeps its check of the caller's place: a caller in the Emperor's unit or in `hop3.slice`, or a descendant of the Emperor where there is no systemd, is refused whatever its uid (`caller.py`). The platform's own vassals still run as `hop3` (§4.1), and the place check is what refuses them.

With apps outside both gates, rootd again has a single trusted non-root caller. Its documented model (structural validation, no per-op authorization, `app_name` taken on trust) is then correct, because the only party that can assert an `app_name` is the orchestrator that legitimately owns all of them. This ADR removes the untrusted callers that would have required per-op authorization.

### 6. Secret and environment isolation

Once app users are distinct, the control plane's secret store ([ADR 048](./048-server-config-and-secret-storage.md): the auth-token database and per-app `[env]`) is no longer readable by app processes: it is `hop3`-owned and no app shares that UID. The guarantee is: an app reads its own secrets and no others, and never the platform's.

**A secret never travels on a command line.** Any local user can read any process's `/proc/<pid>/cmdline`, whatever its owner; `/proc/<pid>/environ` is readable only by the owner. Separate users therefore protect an environment only if it is delivered as an environment. `attach-daemon` workers do not inherit the vassal's `env`, so the platform writes every variable as an `export` on the daemon's shell line, and uWSGI keeps that `/bin/sh -c` alive as the daemon's parent. A planted secret is readable by `nobody` for the app's whole life (measured). This holds on every native install whether or not this ADR lands: any local user, `www-data` included, reads every app's `[env]` with `ps`.

Delivery is therefore by file. The platform writes the app's environment to a file the app user alone can read (in the app's tree, `hop3:hop3-app-<name>` `0640`, like the vassal file), and the start line sources it by path (`set -a; . <file>; set +a; exec <command>`). In-process workers keep uWSGI's `env`, which lives in the `0640` vassal file and reaches only the vassal's own environment. A one-shot command receives its environment in the request to rootd (§4.2).

### 7. Teardown completeness

`hop3 app destroy` must leave no residue, per the platform's teardown discipline. For UID separation this adds: kill the app's processes, then delete the app user and its group. The kill is a rootd operation keyed by the app's name, which rootd maps to `hop3-app-<name>` and applies to every process of that uid. A uid cannot be shed by forking, so nothing escapes it, and it covers apps that have no cgroup (only apps with resource limits get one).

A leftover user is both clutter and a latent UID-reuse hazard: a later user that reused the UID would inherit stale file ownership. Teardown removes the user only after removing everything else the uid owns: its processes, its tree, its files in the directories every user may write (`/tmp`, `/var/tmp`, `/dev/shm`) and the System V IPC objects it created. The app's user can write nowhere else, so this is what makes a freed system uid safe to reuse (§2). Teardown then verifies that the user is absent, the same "verify, don't assume" stance rootd applies to mounts and cgroups, and reports anything it could not remove. User deletion is privileged, so it is a rootd operation.

### 8. Migration

Existing installs run every app as `hop3`. The update migrates them all: its reconcile runs `hop3-server apps:separate`, which for each app creates the user, applies the §3 layout, rewrites the vassal and restarts it, once. The Emperor's unit gains its capabilities and the wrapper once, before any app is migrated; behind the wrapper an unmigrated vassal, of group `hop3`, runs as `hop3` exactly as before.

Each step is idempotent, so a second run finishes a migration the first left halfway, and a server restored from a backup taken on either side of the migration converges the same way. An app whose migration fails keeps running as `hop3`, no worse than before. The update exits non-zero and names it, and `hop3 system status` lists every app still running as `hop3`.

### 9. Non-goals

- **Full container-grade isolation** (per-app mount/network/PID namespaces) is out of scope. UID separation is the minimal change that closes the auth hole and the cross-app read/kill surface; namespace isolation is a separate, heavier decision (and Hop3 avoids Docker's complexity on the native path by design).
- **Changing rootd's protocol or authentication.** The operation set grows by the app-user lifecycle, process control and command start ([ADR 041](./041-privileged-operations-agent.md) §20), each keyed by an app name rootd already validates. The JSON framing, the `SO_PEERCRED` model and the validation rules stay as they are; `app_exec.spawn` adds descriptors to its response.
- **Docker builds.** Dockerfile `RUN` steps run under dockerd, in the image's own user namespace.
- **Shrinking the control plane.** Wherever Docker is installed, `hop3` is in the `docker` group, which already makes a control-plane compromise root on that host ([ADR 041](./041-privileged-operations-agent.md): "hop3-server compromise = total compromise"). This ADR keeps app code out of the control plane; what the control plane itself may do is unchanged.

## Consequences

### Positive

- **The rootd `SO_PEERCRED` boundary becomes real**, and [ADR 041](./041-privileged-operations-agent.md)'s "no per-op authorization" is sound. Untrusted app code can no longer reach root through rootd.
- **Least privilege is restored end to end**: an app is confined to its own user, matching [ADR 010](./010-security-and-resilience.md)'s original intent that a control-plane compromise (or here, hostile app) is bounded.
- **Apps cannot read or kill each other**, nor read the control plane's auth-token database and secrets: satisfying the platform's non-interference and secret-isolation requirements.
- **A hostile recipe is contained at build time as at run time**: its hooks, its package installs and its Nix expression run as its app's user.
- **Cleaner mental model**: "the control plane may read down into an app; an app reads only itself."

### Negative

- **Per-app user lifecycle machinery** (create/delete/verify), with its teardown and UID-reuse edges, are new code and new failure modes.
- **A privileged launch surface reappears.** Two capabilities on the Emperor unit make the Emperor root-equivalent, so its executable moves out of `hop3`'s reach. rootd gains an operation that starts a command its caller chose, as an app's user only ([ADR 041](./041-privileged-operations-agent.md) §20).
- **The permission model is more intricate** (per-app groups, a seal that must treat the build's output as hostile), with more ways to misconfigure than a single shared UID.
- **An app still reaches its own next build.** The build runs as the app's user, so a compromised app can write the caches its next build reads (`home/`) and, while it still runs, the tree being rebuilt. Read-only code stops a running app from changing the code it runs now; it does not stop a compromised app from persisting itself into its next version. Other apps and the control plane stay out of its reach (Open question 2).
- **The seal's cost grows with the tree.** rootd handles one request at a time, and a `node_modules` of a hundred thousand files takes seconds to walk, during which other operations wait.
- **Migration touches every app tree** (re-chown) and the Emperor unit once, and restarts every app once.

### Operational

- `hop3 app destroy` now also removes a system user; operators will see `hop3-app-*` users on the box and should not manage them by hand (the same "operator manages Hop3, Hop3 manages the server" contract as [ADR 041](./041-privileged-operations-agent.md) §6).
- Debugging shifts: `ps`/`journalctl` show per-app users, which aids attribution but changes muscle memory.
- Backups and restores of app `data` run as the app's user (§3). Shared ownership is not a valid assumption.

## Alternatives considered

### A. Single shared app user (`hop3-apps`) for all apps

The alternative is one non-`hop3` user shared by every app. Rejected as the end state, accepted as a valid first increment. It fixes the rootd hole (apps are no longer `hop3`) and the control-plane secret exposure, at a fraction of the lifecycle cost. It does not fix inter-app interference: every app still shares one UID, so app A can still read and kill app B. Given the finding was specifically cross-app compromise and the platform advertises multiple coexisting apps, per-app users are the target; a shared app user is an acceptable milestone on the way if per-app lifecycle needs to land later.

### B. Keep the shared UID, add a token/secret for `hop3-server` → rootd

Have `hop3-server` present a secret rootd checks, so rootd distinguishes it from apps. **Rejected.** A secret that `hop3-server` holds is readable by anything running as the same UID: the apps. There is no secret the orchestrator can keep from a process that shares its user. The boundary must be a UID boundary.

### C. Per-operation authorization / policy in rootd

Have rootd verify that a caller owns the `app_name` it acts on. **Rejected** (and already rejected in [ADR 041](./041-privileged-operations-agent.md) §G). It cannot work while callers share a UID (rootd cannot tell which same-UID process is which app). It is unnecessary once callers are separated: with apps out of the trust domain, `hop3-server` is again the sole caller and legitimately owns every app.

### D. Per-app namespaces / containers for native apps

`unshare` per-app mount/network/user namespaces, or run natives in containers. **Rejected as the mechanism here.** It is a far larger change that reintroduces most of the Docker complexity Hop3 avoids on the native path. It still needs a privileged step to set up. UID separation is the minimal, sufficient fix for the auth and interference problems; namespace isolation, if pursued, is a separate ADR building on this one.

### E. Route vassal spawning through rootd

The alternative is for rootd to start each vassal at its app's UID, preserving a single root boundary. **Not taken for vassals.** A vassal must stay the Emperor's child for the Emperor to reload and stop it, and rootd would take on the lifecycle of every long-running process; the capability-scoped Emperor (§4.1) achieves the same isolation with far less new code. One-shot commands do go through rootd (§4.2): nothing supervises them once they have started, and rootd starting them keeps their privilege where the platform's privilege already is.

### F. Capabilities on `hop3-server` for one-shot commands

`hop3-server` would hold `CAP_SETUID` and `CAP_SETGID` and drop each command itself, as the Emperor's wrapper does for vassals. **Rejected.** `hop3-server` parses every RPC and every `git push`; with `CAP_SETUID`, a bug in any of them is root. The Emperor parses nothing but its own command line.

### G. Single-user Nix where systemd is absent

The installer used to fall back to a single-user store on hosts without systemd. **Rejected.** A single-user store belongs to `hop3`, so every Nix build on such a host would run as the control plane, and the Docker target, which has no systemd, would test a different model from the servers.

## Open questions

1. **Access to a `bind` volume's source.** rootd could grant the app's user a POSIX ACL on the source, recorded in its state and revoked at release. Or it could mount the source idmapped, mapping the source's owner to the app's uid without touching the source, which needs a `mount(8)` that supports it (util-linux 2.39, newer than Debian 12's). What decides: the distributions Hop3 supports, and whether the source must remain unchanged on disk.
2. **A build identity of its own.** A second user per app, running the build and owning its caches, would keep a compromised app away from its next build. It costs a second user per app, which halves the capacity of the system range, and a second home for the caches. What decides: whether "the app cannot change its code" must hold against a compromised app, or only against an app that writes where it should not.
3. **The platform's own vassals.** The WAF runs as `hop3` and parses untrusted traffic. rootd's place check refuses it, but it reads what `hop3` reads. A user of its own would take it out of the control plane.
4. **Non-uWSGI deployers.** Static-file and Docker-Compose deployers: static is served by nginx (no app process, no change); Docker is already isolated. Confirm no other native deployer runs app code as `hop3`.

## References

- [ADR 010](./010-security-and-resilience.md): security and resilience (the unprivileged-`hop3` model this ADR completes)
- [ADR 041](./041-privileged-operations-agent.md): privileged operations agent (the `SO_PEERCRED` boundary this ADR makes real; §1 threat model, §G rejected policy layer, §20 the operations this ADR needs)
- [ADR 046](./046-declarative-app-resources.md): declarative app resources (cgroup/mount ops keyed by app, which must track the new UID)
- [ADR 048](./048-server-config-and-secret-storage.md): server config and secret storage (the secrets app users must no longer read)
- [ADR 053](./053-nix-closure-lifetime.md): Nix closure lifetime (the per-app GC roots, now registered by the app's user)
- [ADR 024](./024-backup-restore-system.md): backup and restore (run as the app's user)
- [ADR 017](./017-agent-based-architecture.md): agent-based architecture
- `scripts/emperor-caps-probe.py`: the measurement behind §4.1
- `packages/hop3-rootd/src/hop3_rootd/caller.py`: the place check rootd keeps (§5)
- `packages/hop3-server/src/hop3/run/uwsgi/worker.py`: vassal `uid`/`gid` generation
- `packages/hop3-installer/src/hop3_installer/nginx_templates.py`: the `User=hop3` Emperor unit
- `packages/hop3-installer/src/hop3_installer/server_installer/nix.py`: the Nix install mode
