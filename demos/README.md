# Hop3 Demos

Scripted, end-to-end demonstrations of Hop3 **platform capabilities** — builders,
toolchains, addons, scaling, backups, the CLI surface — each deploying a small
sample app to a real Hop3 server and exercising a feature.

A demo is **three things at once**, and is never treated as dead code:

- **Teaching** — a readable, runnable walk-through of how a feature works.
- **Demonstration** — what you show in a screencast or to an evaluator.
- **Test** — run in CI (`make test-demos-*`) to catch regressions end-to-end.

> Demos showcase *capabilities*, not best-of-breed apps. Real third-party
> applications (WordPress, Gitea, Miniflux, …) live in the **real-apps catalog**
> (`apps/real-apps-*/`), packaged in multiple variants with content-checked
> validations. See *"Where demos fit"* below.

---

## The essential questions

If you're a Hop3 developer, tester, or test-writer, this is what you need:

1. **How do I run one?** → [Running demos](#running-demos)
2. **What does a run actually do?** → [What a run does](#what-a-run-does)
3. **How do I test my *local* hop3-server changes?** → `--local` (see below)
4. **How is this different from `hop3-test` / tutorials?** → [Where demos fit](#where-demos-fit)
5. **How do I write a new demo?** → [Writing a demo](#writing-a-demo)
6. **Where's the full option reference?** → `python demos/demo.py run --help` / `list --help`

---

## Running demos

Always run **from the repository root**. The entry point is `demos/demo.py`
(there is no `demos` package — call the file directly).

There are two subcommands — **`run`** and **`list`** — and two backends:

```bash
# Local Docker container — no remote server needed (easiest; what CI uses)
python demos/demo.py run --backend docker demo01

# Remote server over SSH (root@host with key auth)
python demos/demo.py run --host <server_ip> demo01
```

(A bare invocation like `python demos/demo.py --backend docker demo01` is treated
as `run …`, so old muscle memory keeps working.)

Common variants (the same on either backend):

```bash
python demos/demo.py list                                # names + titles of all demos
python demos/demo.py list -v                             # detailed inventory + feature tags
python demos/demo.py run --backend docker                # run ALL demos
python demos/demo.py run --backend docker demo01 demo04  # run a few
python demos/demo.py run --backend docker --local demo01 # test LOCAL hop3-server code (rsync)
python demos/demo.py run --backend docker --keep demo01  # leave the app running afterwards
python demos/demo.py run --host <ip> --pause 2 --keep    # screencast pace, keep apps up
python demos/demo.py run --backend docker ~/my-flask-app # run YOUR app (generic demo, no script)
```

### Selecting demos by feature

Every demo has **namespaced capability tags** computed from its `hop3.toml` and
the commands it runs — `builder:docker`, `toolchain:go`, `addon:postgres`,
`extra:backup`, … (a demo script can also declare extras via `FEATURES = {…}`).
See them with `list -v`, and filter with `--select` / `--skip` (on `run` or
`list`):

```bash
python demos/demo.py list --select toolchain:python              # only Python demos
python demos/demo.py run  --select addon:postgres --skip extra:backup
python demos/demo.py list --select toolchain:go,toolchain:ruby   # OR within one flag
```

`--select` is AND across repeated flags (OR within a comma-separated value);
`--skip` is OR; a bare namespace (`--skip addon`) matches any value in it.

Makefile shortcuts run the whole suite as tests:

```bash
make test-demos          # all demos on a local Docker container (--local --quiet)
python demos/demo.py run --host $HOP3_DEV_HOST --local   # all demos on an SSH target
```

For every flag, see `python demos/demo.py run --help` (and `list --help`).

---

## What a run does

The launcher runs four phases, then summarises pass/fail/skip with timings:

1. **Prerequisites** — reach the target (start the Docker container or SSH in),
   check the OS, install/update Hop3 (skip with `--skip-install`; sync local code
   with `--local`).
2. **Configure CLI** — create/log in an admin user and point an *isolated* CLI
   config at the target (so demos never touch your real `~/.config/hop3-cli`).
3. **Run the selected demos** — each `demo-script.py`'s `run(ctx)`; a failure in
   one doesn't stop the others.
4. **Summary** — results + durations; admin credentials are printed if `--keep`.

---

## Where demos fit

Hop3 has three complementary end-to-end harnesses — pick by intent:

| Use this | When you want to… | Lives in |
|----------|-------------------|----------|
| **demos** (`demos/demo.py`) | show/verify a *platform capability* with a tiny sample app | `demos/` |
| **`hop3-test`** | deploy the **real-apps catalog** and assert content-checked validations | `apps/real-apps-*/`, `packages/hop3-testing/` |
| **tutorials** (validoc) | prove the *documentation* is correct (literate, executable `.md`) | `docs/tutorials/` |

All three deploy to a real server; demos are the smallest and most didactic.

---

## Writing a demo

A demo is a directory under `demos/` containing a `demo-script.py` and an `app/`.
It's auto-discovered — no registration needed.

```python
# demos/demoXX/demo-script.py
from __future__ import annotations
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib import DemoContext

TITLE = "Demo XX: My Feature"
DESCRIPTION = "One paragraph: what this demonstrates."
APP_NAME = "demoXX"
APP_DIR = Path(__file__).parent / "app"
REQUIRES: list[str] = []   # e.g. ["docker"] — the demo is skipped if unmet
# Optional: capability tags that can't be auto-detected (e.g. an addon you
# provision through a helper). Merged with the computed builder/toolchain/
# addon/extra tags. Namespaced — see `list -v`.
FEATURES = {"extra:my-feature"}

def run(ctx: DemoContext) -> None:
    # IMPORTANT: import lib INSIDE run() — the launcher puts demos/ on sys.path
    # before loading this module, so a top-level `from lib ...` would fail.
    from lib import deploy_app, set_hostname, redeploy_app, test_app_via_curl, cleanup_app
    from lib.commands import run_hop3

    host = ctx.get_app_hostname(APP_NAME)
    deploy_app(ctx, APP_NAME, APP_DIR)            # packs APP_DIR, `hop3 deploy --app …`
    set_hostname(ctx, APP_NAME, host)
    redeploy_app(ctx, APP_NAME, APP_DIR)
    test_app_via_curl(ctx, f"https://{host}", expected_content="…")
    run_hop3(f"app status --app {APP_NAME}")      # any CLI command via run_hop3
    cleanup_app(ctx, APP_NAME, f"https://{host}") # honours --keep
```

Conventions that matter (learned the hard way):

- **Import `lib` inside `run()`**, not at module top level (see comment above).
- **App is always `--app <name>`**, never positional (ADR 036 D5). `run_hop3`
  takes the command without the `hop3` prefix.
- **Non-interactive**: the launcher runs without a TTY. For commands that prompt
  (deploy confirm, destroy), the helpers pass `-y`; if you call `run_hop3`
  directly for a prompting command, set `HOP3_NO_INPUT=1` in the demo's env.
- **Self-clean**: tear down whatever you create (`cleanup_app`, addon/backup
  destroys), so re-runs are reproducible and apps don't coexist by accident.
- See `demos/lib/__init__.py` for the full helper set, and existing demos
  (`demo01` simplest, `demo60` the broad CLI tour) as templates.

**No script needed?** Point the launcher at any Hop3-compatible app directory
(`python demos/demo.py run --backend docker ~/my-app`) and the **generic demo**
detects the app type (`hop3.toml`/`Dockerfile`/`requirements.txt`/`package.json`/
`Procfile`), deploys, hostnames, tests, and cleans up automatically.

---

## Layout

```
demos/
├── demo.py            # launcher (discovery, phases, summary)
├── lib/               # shared helpers — the demo API
│   ├── __init__.py    #   exported helpers (deploy_app, run_hop3, print_*, …)
│   ├── app.py         #   app lifecycle (deploy / hostname / status / cleanup)
│   ├── commands.py    #   run_hop3 / run_ssh / run_local + isolated CLI env
│   ├── context.py     #   DemoContext, DemoResult, OutputLevel
│   ├── phases.py      #   prerequisites → configure-CLI → run
│   ├── generic_demo.py#   deploy-any-app fallback
│   └── …              #   discovery, display, output, server setup
└── demoNN/            # one dir per demo (demo-script.py + app/), auto-discovered
```

---

## When something breaks

- `--verbose` for stack traces; `--keep` to leave the app up and inspect it
  (`hop3 app logs --app <name>`, `hop3 app debug --app <name>`).
- General platform gotchas (RPC session isolation, build-vs-runtime env, state
  transitions, 502s, proxy/HOST_NAME) live in
  [`notes/lessons-learned/`](../notes/lessons-learned/).

## Prerequisites

- **Local**: Python 3.10+, the `hop3` CLI on `PATH`, and (for `--backend docker`)
  a working Docker daemon.
- **SSH backend**: Ubuntu 22.04/24.04 target with `root` key-based SSH.
- First install takes 5–10 min; use `--skip-install` once Hop3 is installed.
