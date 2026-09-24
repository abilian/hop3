# Replacing uWSGI: existing process runners

Pre-ADR notes. [ADR 023](adrs/023-runtime-stack-replacement.md) proposes replacing uWSGI with Granian plus a purpose-built process manager. This note is the survey that should come before building one: what uWSGI actually does for Hop3, what a replacement must guarantee, and which existing runners already do it. Nothing here is decided.

## What uWSGI does for Hop3

This list comes from the options the platform generates (`run/uwsgi/worker.py`, `deployers/waf.py`). Two distinct jobs share one binary.

**Supervision (the Emperor and its vassals):**

- One config file per app process in a watched directory: adding a file starts the process, touching it reloads it, deleting it stops it.
- Respawn on crash, with throttling when a process keeps dying.
- `attach-daemon`: runs an arbitrary command next to the vassal. This is how most apps run today (Procfile and toolchain commands for every language), and how the php-fpm pool and the LeWAF proxy run.
- `cron`: scheduled commands per app.
- Per-process environment (`env`), working directory (`chdir`), and a `procname-prefix` the platform uses to find an app's processes.
- Logs: one file per process (`logto2`), size-based rotation (`log-maxsize`, `log-backupname`), ownership and mode (`logfile-chown`, `logfile-chmod`).
- Identity: `uid`/`gid` per vassal. Applied only when uWSGI runs as root (see below).

**An in-process application server:**

- Python WSGI apps with no start command run inside uWSGI (`module`, `virtualenv`, `processes`, `threads`, `async`, `max-requests`), including idle mode (`idle`, `cheap`), which stops an unused app and starts it on the next request.
- Rack (`rack` plugin) and JVM (`jvm`, `jwsgi`) workers exist on the same model.

The second job belongs to the toolchains, which would emit a real server command (Granian or gunicorn for WSGI, Puma for Rack) into the runtime contract, as they already do for every other language. Idle mode is the one feature without an obvious home.

## What a replacement must guarantee

Each of these is either a platform rule already or a lesson from an incident.

1. **Start, reload and stop an app on the platform's request, and report the real outcome.** A start that fails is visible as a failure, never as "started".
2. **Respawn with throttling**, and make a crash loop visible where the operator looks.
3. **Run each app as its own user, with no privilege reaching it** ([ADR 055](adrs/055-app-runtime-uid-separation.md)). The runner must not hold root or pass capabilities down. uWSGI shows how this goes wrong: it ignores `uid`/`gid` unless it is root, silently, and a capability-scoped Emperor hands its capabilities to every app. ADR 055 §4 closes this with a `setpriv` wrapper, which works in front of any runner that starts a command.
4. **Complete, verifiable teardown.** Stopping an app leaves no process behind, including grandchildren and processes that ignore a graceful stop.
5. **Per-process environment, working directory and logs**, with rotation, readable by the control plane.
6. **Scheduled commands** (today's `cron` workers).
7. **Runs on every target Hop3 supports**, including the Docker target the e2e suite uses, which has no systemd.

## Candidates

Each entry says what it buys, what it costs, and what would decide for it.

### systemd, driven through rootd

One unit per app process (a template such as `hop3-app@.service`, or generated units) with `User=hop3-app-<name>`. hop3-server asks rootd to install, start, reload and stop units, the way rootd already manages services.

- **Buys:** the identity drop is done by PID 1, so Hop3 needs neither the wrapper nor a capability on any of its processes, and runs no long-running root process of its own. Cgroups and resource limits come with every unit, which covers much of [ADR 046](adrs/046-declarative-app-resources.md). It adds sandboxing (`NoNewPrivileges`, `ProtectSystem`, `PrivateTmp`), journald logging with rotation, restart policies with rate limits, timers for scheduled commands, and socket activation, which is a candidate replacement for idle mode. Teardown kills the unit's whole cgroup.
- **Costs:** the Docker target runs supervisor, not systemd, so either the e2e container boots systemd or a second backend exists for it. Every lifecycle call goes through rootd, which grows by an op family. Logs move to journald, so `hop3 logs` reads from there. ADR 023 listed this as its alternative 4 and set it aside for being Linux-only and hard to integrate. Hop3 only deploys to Linux, and rootd is the integration point that did not exist when that was written.
- **Decides:** whether systemd can be required on real servers, and whether the e2e target can boot it.

### s6 (skarnet)

s6 keeps a supervision tree with one service directory per app process, managed with `s6-svc` and `s6-rc`.

- **Buys:** small and actively maintained. It runs the same way on a host and in a container, so one backend covers every target. Readiness notification and dependency ordering are built in, and teardown is reliable.
- **Costs:** switching each service to its app user needs either a root supervisor or ADR 055's `setpriv` wrapper. It has no cgroups or sandboxing of its own, so ADR 046 keeps its separate mechanism. Its tooling is unfamiliar to most operators.
- **Decides:** whether Hop3 must run where systemd is absent.

### supervisord

The supervisor already used on the Docker target.

- **Buys:** familiar, maintained, with per-program `user=` and an XML-RPC control API.
- **Costs:** `user=` needs supervisord to run as root. It has no cgroups. Reloading one program after a config change is coarse (`reread` and `update` across the whole config), and it does not follow grandchildren on stop.
- **Decides:** little in its favour beyond already being installed on one target.

### A purpose-built runner (ADR 023's proposal)

ADR 023 proposes a small asyncio daemon inside or beside hop3-server.

- **Buys:** exactly Hop3's lifecycle, with a direct API and no external dependency.
- **Costs:** everything in the list above is ours to write and keep correct: respawn and throttling, grandchild tracking, log rotation, timers, readiness. The identity drop still needs root or the wrapper. The first two candidates already provide most of this.
- **Decides:** a requirement none of the existing runners can meet. None has been identified yet.

### Considered briefly

- **runit:** very close to s6, with little development activity.
- **circus:** largely unmaintained.
- **process-compose, overmind, honcho:** development tools. They run everything as one user and are built for a workstation.
- **Nomad (`exec` driver):** a cluster scheduler, much heavier than a single-server PaaS needs.
- **pm2:** tied to the Node ecosystem.

## Measurements that would narrow it

1. Boot systemd inside the e2e image and run one app as a unit with `User=`. If that works, systemd costs one backend instead of two.
2. Map the feature list above onto systemd directives and s6 primitives, and mark each gap.
3. Decide what replaces idle mode, or whether it is dropped.
