# Plan: per-app users and build-time isolation (0.9)

**Created:** 2026-10-09 for 0.8; moved to 0.9 on 2026-10-11, with build-time isolation added to its scope. **Parent:** [`plan-0.9.md`](plan-0.9.md), whose headline this is; its [decisions 2 to 4](plan-0.9.md#decisions-needed-before-code) (Nix single- or multi-user, UID allocation, reading `data/`) come before the code here, and [the work the headline brings with it](plan-0.9.md#work-the-headline-brings-with-it) rides along with the steps below. **Design record:** [ADR 055](../adrs/055-app-runtime-uid-separation.md). **Done in 0.8:** state out of `src/`, a per-app `HOME` and `TMPDIR`, and a stopgap for the worst consequence below: rootd refuses callers that run inside the app runtime ([`plan-0.8.md`](plan-0.8.md), headline 1).

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
- **UID.** UIDs come from the system range, allocated by `useradd` (plan-0.9 decision 3). rootd's state records the users it created, and rootd acts on no other: an unrecorded `hop3-app-*` user is a `state_conflict`.
- **Reuse safety.** Teardown kills the app's processes by uid, removes its tree and its files in `/tmp`, `/var/tmp` and `/dev/shm` and its System V IPC objects *before* `userdel`, so nothing the deleted uid could have written survives (ADR 055 §7).
- **Groups.** App users are in no group but their own, and never in `hop3`.

### Filesystem (ADR 055 §3)

A rootd "seal" applies this layout after each build, a failed one included, and before start. An "unseal" hands `src/` and `venv/` to the app's user before the build.

| Path | Owner | Mode | Why |
|---|---|---|---|
| `apps/<app>/` | `hop3:<app>` | 0750 | The app traverses to its tree; `git/` below stays `hop3:hop3` 0750 |
| `src/`, `venv/` | `hop3:<app>` | dirs 0750, files 0640 (+x kept) | Read-only to the app. Where nginx serves files (a static site, the assets under a PHP document root), those files are world-readable and the directories above them `o+x`; files an interpreter executes (`.php`) keep 0640 (ADR 055 §3). |
| `data/`, `volumes/`, `scratch/`, `home/`, `tmp/` | `<app>:<app>` | 0700 | The app's own state |
| `log/` | `<app>:hop3` | 2750 | setgid: files the app creates are group `hop3`, 0640 through `logfile-chmod`, so `hop3 app logs` still reads them |
| `worker-env/*.env`, the vassal `.ini` | `hop3:<app>` | 0640 | The app reads them after the drop; nobody else does |

**The seal treats the tree as hostile** (ADR 041 §20): a descriptor walk that follows no symbolic link, explicit modes, setuid and setgid cleared, POSIX ACLs removed, and only once the build's processes are gone.

**Vassal install:**
1. hop3 writes the `.ini` to `uwsgi-available`.
2. rootd seals it.
3. hop3 renames it into `uwsgi-enabled`. A rename keeps owner and mode, so the Emperor never sees an unsealed file.

### New rootd ops

All are default-deny, and each validates `app_name` and path containment.

The full specification is ADR 041 §20; this is the summary.

- **`app_user.ensure(app)` → `{user, uid, gid}`.** Idempotent. Adds `useradd` to the binary allow-list.
- **`app_user.unseal(app)` / `app_user.seal(app, paths?)`.** Hand the build tree to the app's user, then apply the layout above with `os.chown`/`os.chmod` relative to directory descriptors, so no new binary. Containment under `apps/<app>/` and the two uWSGI directories.
- **`app_user.release(app)`.** In order:
  1. kill the app's processes by uid, and wait until they are gone;
  2. remove the uid's files in the world-writable directories and its System V IPC objects;
  3. return the tree to `hop3:hop3` so hop3-server can remove it;
  4. `userdel` and `groupdel`;
  5. verify the user is gone, and return anything not removed.
- **`app_process.list` / `app_process.kill(app)`.** Matches processes by uid, from `/proc/<pid>/status`. This replaces the reaper's cwd matching and `os.kill`, which fail across uids, and feeds `cgroup.attach_pids`.
- **`app_exec.spawn(app, argv, env, cwd, pty?)`.** Forks the command under the `setpriv` drop: `--reuid/--regid/--clear-groups --inh-caps=-all --ambient-caps=-all --no-new-privs`.
  - **What comes back:** the command's stdin, stdout and stderr (or a pty) over the socket with `SCM_RIGHTS`, plus a control socket that yields the exit code. Closing the control socket kills the command, which is how a timeout and a dropped caller stop it.
  - **Never waits:** it returns at once, so the single-threaded daemon is unaffected. A monitor per command, in a cgroup leaf of its own under `hop3.slice`, waits for it and writes its status, so a restart of rootd neither kills the command nor loses its status. rootd reaps only the intermediate fork.
  - **Not logged:** the audit entry records the environment's names, never its values. `setpriv` joins the allow-list.
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
  - `app_user.unseal` before the build, `app_user.seal` after it, failed or not, and before spawn;
  - after start, a check that the app's processes run as its uid, failing the deploy otherwise (ADR 055 §4).
- **Destroy** (`commands/app.py`, `orm/app.py` `App.destroy`): `app_user.release` before the tree is removed.
- **php-fpm:** no change. It is an `attach-daemon` of the `web` vassal, so it inherits the drop.
- **The WAF vassal** (`deployers/waf.py`) is platform code. Its vassal file is of group `hop3`, so the wrapper runs it as `hop3`, capabilities cleared, and rootd's place check refuses it. A user of its own is ADR 055 open question 3.

### Emperor and installer

- **systemd:** `uwsgi-hop3.service` gets `AmbientCapabilities=CAP_SETUID CAP_SETGID`, a matching `CapabilityBoundingSet=`, and `--emperor-wrapper /usr/local/libexec/hop3-vassal-wrapper`.
- **supervisor** (the Docker target): the program runs `setpriv --reuid=hop3 --regid=hop3 --init-groups --inh-caps=+setuid,+setgid --ambient-caps=+setuid,+setgid -- uwsgi --emperor … --emperor-wrapper …`. This is the argument list `scripts/emperor-caps-probe.py` tested.
- **The Emperor's uWSGI** is root-owned, outside `hop3`'s venv (today `/home/hop3/venv/bin/uwsgi` in both the unit and the supervisor program). With `CAP_SETUID` the Emperor is root-equivalent, and a binary `hop3` can rewrite would make it a path from `hop3` to root (ADR 055 §4.1).
- **The wrapper** is root-owned, 0755.
  - **Finding the user:** the vassal file's group (ADR 055 §4.1). Only rootd's seal sets it, so no map is needed and no parsing of vassal names, which may contain `_`. It then execs `setpriv … uwsgi "$@"`.
  - **What it refuses, loudly:** a file outside `uwsgi-enabled`, not owned by `hop3`, writable by group or others, or of a group that is neither `hop3` nor an app group. A file of group `hop3` runs as `hop3`, capabilities cleared: the WAF, and an app not yet migrated, which the deploy's uid check reports.
- **Nix:** on hosts without systemd the installer runs `nix-daemon` under supervisor and converts an existing single-user store; the single-user branch of `server_installer/nix.py` goes (plan-0.9 decision 2).
- **Migration:** the installer's reconcile migrates every app on upgrade, through `hop3-server apps:separate` (ensure, seal, regenerate vassals).
  - **What it costs:** each app restarts once, which the upgrade's output and `CHANGES.md` say.
  - **Visible either way:** no app keeps running as `hop3` unnoticed, since `hop3 system status` lists any that does.

## Builds as the app's user

Every step that runs recipe code moves to the app's user: the toolchains' installs (`pip`, `npm`, `bundle`, `composer`, `cargo`, `go`, `mvn`/`gradle`, `mix`, `dotnet`), and `before-build`, `build` and `after-build`. They go through `as_app.run`, with:

- **A build tree the app may write.** The unseal gives `src/` and `venv/` to the app's user while the build runs, and the seal hands them back to `hop3:<app>` read-only before start. A failed build is sealed too, or the control plane could not replace the tree on the next deploy.
- **Its own caches.** Toolchain caches (`~/.npm`, `~/.cargo`, `~/.m2`, the pip cache) live in the app's `home/`, which also stops one app's build poisoning another's.
- **The build hooks' environment.** They currently inherit hop3-server's whole environment, `HOP3_SECRET_KEY` included; they get `build_app_env` instead, as the run-time commands already do.

**Nix.** Derivations build as `nixbld` inside the daemon's sandbox, on every install once the single-user branch goes (plan-0.9 decision 2). The client, `nix-build`, evaluates the recipe's expression and can read whatever its user can, so it runs as the app's user through `as_app.run`. Its GC roots (`.nix-result`, `.nix-result-prev`, ADR 053 §1) move under a directory the unseal hands to the build, since the app's user cannot write `apps/<app>/` itself.

**Docker.** Dockerfile `RUN` steps run under dockerd and are out of scope.

## Not in this plan

- **rootd's own code**, which lived in `/home/hop3/venv` where `hop3` could write it: fixed in 0.8.1, which runs it from a root-owned venv in `/opt/hop3-rootd`.
- **Namespace isolation** (bubblewrap, nspawn) as defence in depth: the isolation ADR in [`plan-0.9-plus.md`](plan-0.9-plus.md) comes first.

## Order of work

Each step is tested before the next.

1. **rootd ops:** `app_user.ensure/seal/release`, `app_process.list/kill`. Unit tests with `FakeExec` and a temporary tree.
2. **rootd `app_exec.spawn`:** descriptor passing and exit status. Unit tests with real descriptors against a test socket.
3. **Installer:** the wrapper, a root-owned uWSGI for the Emperor, the Emperor's systemd and supervisor changes, `nix-daemon` under supervisor, and `hop3-server apps:separate`.
4. **hop3-server:** `as_app`, then each run-time call site; the vassal install, the reaper, the deploy check, and destroy.
5. **Builds:** the toolchains and build hooks through `as_app.run`, caches in the app's `home/`, the seal after the build.
6. **Go or no-go** on Docker (below), in a branch that can be dropped whole.

## Verification

- **Static and unit checks:** `make lint`, `make test-fast`, and the rootd and installer suites.
- **A fixture** deployed beside a second app. The name `200-flask-isolation` collides with the existing `200-flask-rootd-refused`: extend that fixture with the read checks, or take a free number. Its page reports:
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
