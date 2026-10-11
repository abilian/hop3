# Plan: per-app users and build-time isolation (0.9)

**Created:** 2026-10-09 for 0.8; moved to 0.9 on 2026-10-11, with build-time isolation added to its scope. **Parent:** [`plan-0.9-plus.md`](plan-0.9-plus.md), under Security and identity. **Design record:** [ADR 055](../adrs/055-app-runtime-uid-separation.md). **Done in 0.8:** state out of `src/`, a per-app `HOME` and `TMPDIR`, and a stopgap for the worst consequence below: rootd refuses callers that run inside the app runtime ([`plan-0.8.md`](plan-0.8.md), headline 1).

## Why

Every native app runs as `hop3`, the control plane's own user. Three consequences follow:

- Any app can connect to hop3-rootd's socket and pass its only check (`SO_PEERCRED` uid is `hop3` or `root`). Untrusted application code reaches root with no exploit.
- Any app can read `hop3.db`, every app's `[env]` and every addon credential.
- Any app can signal its neighbours, or interfere with their files.

**Why build time belongs in the same plan.** Recipe code runs at build time too (`before-build`, package-manager install scripts, Nix shell phases), as `hop3`. Running only the runtime as the app's user would leave that path open and change every app's file ownership twice, once for each half. One plan settles the ownership model once.

**What 0.8 already did.** State lives outside `src/`, and each app has its own `HOME` and `TMPDIR`. rootd refuses any caller inside the app runtime (the `uwsgi-hop3` cgroup, or a descendant of the Emperor where there is no systemd), which closes app code reaching root without changing users. Apps still share `hop3`, so one app can read another's data and the control plane's: that is what this plan closes.

## Design

### One privilege path: hop3-rootd

`hop3` never becomes another user by itself. rootd (root) creates the users, sets ownership, kills processes, and starts every one-shot command as the app's user. **No sudo, in any form:** rootd exists so the platform does not depend on it.

The uWSGI Emperor is the one exception, as ADR 055 §4 settled by experiment. It holds `CAP_SETUID` and `CAP_SETGID`, and starts each vassal through a root-owned `setpriv` wrapper, because its vassals must stay its children. Both paths drop to the app's user with the same `setpriv` argument list, defined once in hop3-rootd and rendered into the wrapper by the installer.

Once app processes no longer run as `hop3`, rootd's existing peer check refuses them: the escalation closes without changing the check.

### Identity

- **Name.** User and group `hop3-app-<n>`, one per app, created with `useradd --system --user-group --no-create-home --shell /usr/sbin/nologin`. `<n>` is the app name lowercased. When the result exceeds 32 characters, it is a truncated name plus a 6-hex hash. App names allow uppercase and 63 characters (`APP_NAME_RE`), so the mapping is explicit and stored.
- **UID.** UIDs come from the system range, allocated by `useradd`. rootd's state records app → (user, uid).
- **Reuse safety.** Teardown kills the app's processes by uid and removes its tree *before* `userdel`, so no file of a deleted uid survives inside `apps/`.
- **Groups.** App users are in no group but their own, and never in `hop3`.

### Filesystem (ADR 055 §3)

A rootd "seal" applies this layout after each build and before start:

| Path | Owner | Mode | Why |
|---|---|---|---|
| `src/`, `venv/` | `hop3:<app>` | dirs 0750, files 0640 (+x kept) | Read-only to the app. Where nginx serves a tree (static, PHP document root), `src/` also gets `o+x`, traverse only; `grant_web_server_read` already makes the served tree `a+rX`. |
| `data/`, `volumes/`, `scratch/`, `home/`, `tmp/` | `<app>:<app>` | 0700 | The app's own state |
| `log/` | `<app>:hop3` | 2750 | setgid: files the app creates are group `hop3`, 0640 through `logfile-chmod`, so `hop3 app logs` still reads them |
| `worker-env/*.env`, the vassal `.ini` | `hop3:<app>` | 0640 | The app reads them after the drop; nobody else does |

**Vassal install:**
1. hop3 writes the `.ini` to `uwsgi-available`.
2. rootd seals it.
3. hop3 renames it into `uwsgi-enabled`. A rename keeps owner and mode, so the Emperor never sees an unsealed file.

### New rootd ops

All are default-deny, and each validates `app_name` and path containment.

- **`app_user.ensure(app)` → `{user, uid}`.** Idempotent. Adds `useradd` to the binary allow-list.
- **`app_user.seal(app, paths?)`.** Applies the layout above with `os.chown`/`os.chmod`, so no new binary. Realpath containment under `apps/<app>/` and the two uWSGI directories.
- **`app_user.release(app)`.** In order:
  1. kill the app's processes by uid;
  2. return the tree to `hop3:hop3` so hop3-server can remove it;
  3. `userdel` and `groupdel`;
  4. verify the user is gone.
- **`app_process.list` / `app_process.kill(app)`.** Matches processes by uid, from `/proc/<pid>/status`. This replaces the reaper's cwd matching and `os.kill`, which fail across uids, and feeds `cgroup.attach_pids`.
- **`app_exec.spawn(app, argv, env, cwd, pty?)`.** Forks the command under the `setpriv` drop: `--reuid/--regid/--clear-groups --inh-caps=-all --ambient-caps=-all --no-new-privs`.
  - **What comes back:** the command's stdin, stdout and stderr (or a pty) over the socket with `SCM_RIGHTS`, plus a status descriptor that yields the exit code.
  - **Never waits:** it returns at once, so the single-threaded daemon is unaffected, and rootd reaps the children on `SIGCHLD`.
  - **Inputs:** `env` travels in the request, never on argv. `cwd` must lie inside the app's tree.

### hop3-server

**One module,** `hop3/run/as_app.py`, over `app_exec.spawn`, with three entry points:
- `run()`: captured output, with a timeout;
- `stream()`: for `hop3 run`;
- `interactive()`: the pty, for `hop3 app shell`.

**Every place that runs app code calls it:**
- `[run].before-run` (`run/spawn.py`);
- `[admin]` and `[probe]` create (`deployers/deployer.py`);
- `check.py` (`server/checks/runner.py`);
- `hop3 run` (`commands/misc.py`);
- `hop3 app shell` (`server/cli/shell.py`, `run/app_env.py` `shell_session`);
- backups and restores of `data/` and volumes (`core/backup.py`): tar runs as the app.

`build_app_env` keeps building the environment; `USER` becomes the app's user.

**Other changes:**
- **Vassals** (`run/uwsgi/worker.py`): the `uid`, `gid` and `logfile-chown` settings go, since the wrapper does the drop (and uWSGI ignores them unless it runs as root). Installed through seal and rename.
- **Process control** (`run/reaper.py`, `plugins/deploy/uwsgi/deployer.py`, `deployers/native_limits.py`): through `app_process`.
- **Deploy:**
  - `app_user.ensure` before the first build;
  - `app_user.seal` after the build and before spawn;
  - after start, a check that the app's processes run as its uid, failing the deploy otherwise (ADR 055 §4).
- **Destroy** (`commands/app.py`, `orm/app.py` `App.destroy`): `app_user.release` before the tree is removed.
- **php-fpm:** no change. It is an `attach-daemon` of the `web` vassal, so it inherits the drop.
- **The WAF vassal** (`deployers/waf.py`) is platform code. The wrapper runs vassals with the reserved platform prefix as `hop3`, capabilities cleared.

### Emperor and installer

- **systemd:** `uwsgi-hop3.service` gets `AmbientCapabilities=CAP_SETUID CAP_SETGID`, a matching `CapabilityBoundingSet=`, and `--emperor-wrapper /usr/local/libexec/hop3-vassal-wrapper`.
- **supervisor** (the Docker target): the program runs `setpriv --reuid=hop3 --regid=hop3 --init-groups --inh-caps=+setuid,+setgid --ambient-caps=+setuid,+setgid -- uwsgi --emperor … --emperor-wrapper …`. This is the argument list `scripts/emperor-caps-probe.py` tested.
- **The wrapper** is root-owned, 0755.
  - **Finding the user:** it maps a vassal file to its app through a root-owned map that rootd maintains (`/etc/hop3/app-users/<app>`), by longest-prefix match on the vassal name, since app names may contain `_`. It then execs `setpriv … uwsgi "$@"`.
  - **Unregistered vassals:** refused loudly, except the platform prefix.
- **Migration:** the installer's reconcile migrates every app on upgrade, through `hop3-server apps:separate` (ensure, seal, regenerate vassals).
  - **What it costs:** each app restarts once, which the upgrade's output and `CHANGES.md` say.
  - **Visible either way:** no app keeps running as `hop3` unnoticed, since `hop3 system status` lists any that does.

## Builds as the app's user

Every step that runs recipe code moves to the app's user: the toolchains' installs (`pip`, `npm`, `bundle`, `composer`, `cargo`, `go`, `mvn`/`gradle`, `mix`, `dotnet`), and `before-build`, `build` and `after-build`. They go through `as_app.run`, with:

- **A build tree the app may write.** `src/` and `venv/` belong to the app's user while the build runs, and the seal hands them back to `hop3:<app>` read-only before start.
- **Its own caches.** Toolchain caches (`~/.npm`, `~/.cargo`, `~/.m2`, the pip cache) live in the app's `home/`, which also stops one app's build poisoning another's.
- **The build hooks' environment.** They currently inherit hop3-server's whole environment, `HOP3_SECRET_KEY` included; they get `build_app_env` instead, as the run-time commands already do.

**Nix.** On a multi-user install the derivation already runs as a `nixbld` user inside the sandbox. On a single-user install it runs as `hop3`, and so does `sandbox = relaxed`. Which installs Hop3 supports, and whether the single-user case is moved to multi-user, is decided in this plan before its code.

**Docker.** Dockerfile `RUN` steps run under dockerd and are out of scope.

## Not in this plan

- **rootd's own code lives in `/home/hop3/venv`, which `hop3` can write.** That is a control-plane-to-root path, separate from app isolation ([`../todo.md`](../todo.md)).
- **Namespace isolation** (bubblewrap, nspawn) as defence in depth: the isolation ADR in [`plan-0.9-plus.md`](plan-0.9-plus.md) comes first.

## Order of work

Each step is tested before the next.

1. **rootd ops:** `app_user.ensure/seal/release`, `app_process.list/kill`. Unit tests with `FakeExec` and a temporary tree.
2. **rootd `app_exec.spawn`:** descriptor passing and exit status. Unit tests with real descriptors against a test socket.
3. **Installer:** the wrapper, the Emperor's systemd and supervisor changes, the map directory, and `hop3-server apps:separate`.
4. **hop3-server:** `as_app`, then each run-time call site; the vassal install, the reaper, the deploy check, and destroy.
5. **Builds:** the toolchains and build hooks through `as_app.run`, caches in the app's `home/`, the seal after the build.
6. **Go or no-go** on Docker (below), in a branch that can be dropped whole.

## Verification

- **Static and unit checks:** `make lint`, `make test-fast`, and the rootd and installer suites.
- **A fixture,** `apps/test-apps-procfile/200-flask-isolation`, deployed beside a second app. Its page reports:
  - its uid;
  - whether `/run/hop3-rootd/socket` accepts it;
  - whether it can read `/home/hop3/hop3.db`;
  - whether it can read a sibling app's `worker-env/*.env`.

  The validations assert its own uid, rootd refused, and both reads refused.
- **On Docker,** `hop3-test run --docker --clean --from local`, redeploy included, on:
  - the Procfile, PHP and nix-gen fixtures;
  - the golden set.
- **Then:**
  - `apps:separate` on a server deployed from `devel`, the migration path;
  - destroy, then check that the users are gone and no process survives.
- **A remote run**, once Docker holds.
