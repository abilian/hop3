---
date: 2026-06-19
template: blog_post.html
series: How Hop3 is Tested
series_order: 2
description: Why every Hop3 demo is three things at once — a tutorial, a screencast, and a regression test — and how the launcher runs them.
tags:
  - Testing
  - Demos
  - Engineering
---

# The Demos: One Artifact, Three Jobs

Most projects keep demos and tests in separate worlds. Demos are pretty, hand-curated, and rot quietly; tests are green and unreadable. Hop3 refuses the split. A demo here is **three things at once**, and is never treated as dead code:

- **Teaching**: a readable, runnable walk-through of how a feature works.
- **Demonstration**: what you show in a screencast or to an evaluator.
- **Test**: run in CI to catch regressions end-to-end.

That decision is recorded in [ADR 043](/developers/adrs/043-unified-testing-architecture/) (v0.3): *a demo is simultaneously an educational walkthrough, a live demonstration, and a test, so a broken demo is a first-class regression.* The demo engine is kept precisely because removing any one of those three jobs would make the others worse.

## Capabilities first

There's a clean division of labour with the [test runner](2026-06-testing-runner.md):

> Demos showcase **capabilities**: builders, toolchains, addons, scaling, backups, the CLI surface, each deploying a *tiny* sample app to exercise one feature. Real third-party applications (WordPress, Gitea, Miniflux) live in the **real-apps catalog**, packaged in multiple variants with content-checked validations.

A demo's app is deliberately small and boring. The point is the platform edge it pokes at.

## What a demo looks like

A demo is a directory under `demos/` containing a `demo-script.py` and a small `app/`. It is auto-discovered with no registration:

```python
# demos/demoXX/demo-script.py
TITLE = "Demo XX: My Feature"
DESCRIPTION = "One paragraph: what this demonstrates."
APP_NAME = "demoXX"
APP_DIR = Path(__file__).parent / "app"
REQUIRES: list[str] = []            # e.g. ["docker"] — the demo is skipped if unmet

def run(ctx: DemoContext) -> None:
    from lib import deploy_app, set_hostname, test_app_via_curl, cleanup_app
    host = ctx.get_app_hostname(APP_NAME)
    deploy_app(ctx, APP_NAME, APP_DIR)                  # packs APP_DIR, `hop3 deploy --app …`
    set_hostname(ctx, APP_NAME, host)
    test_app_via_curl(ctx, f"https://{host}", expected_content="…")
    cleanup_app(ctx, APP_NAME, f"https://{host}")       # honours --keep
```

The verification is **content-checked**. `test_app_via_curl` asserts that the *body* contains app-specific text; a `200` can be a placeholder, an error page, or, memorably, *another app's content* leaking through a misconfigured proxy. A green status code proves almost nothing on a PaaS.

## Running and inspecting them

The launcher is a single entry point, `demos/demo.py`, with two subcommands and two backends:

```bash
# Local Docker container — no remote server needed (what CI uses)
python demos/demo.py run --backend docker demo01

# Remote server over SSH
python demos/demo.py run --host <server_ip> demo01

# Test your LOCAL hop3-server changes (rsync the working tree before deploying)
python demos/demo.py run --backend docker --local demo01

# See what's available, with capability tags
python demos/demo.py list -v
```

### Capability tags and feature filters

Every demo carries **namespaced capability tags**, computed from its `hop3.toml` (builder, toolchain, addons) plus anything the script declares: `builder:docker`, `toolchain:go`, `addon:postgres`, `extra:backup`. You can slice the suite by them:

```bash
python demos/demo.py run --select toolchain:python --skip extra:backup
python demos/demo.py list --select addon:postgres
```

This makes the demos usable as a *targeted* probe: "run everything that touches Postgres", "skip the slow backup demos", "only the Go toolchain". `--select` is AND across flags (OR within a comma-separated value); `--skip` is OR.

## What a run actually does

The launcher runs four phases, then summarises pass/fail/skip with timings:

1. **Prerequisites**: reach the target (start the Docker container or SSH in), check the OS, install/update Hop3.
2. **Configure CLI**: create/log in an admin user and point an *isolated* CLI config at the target, so demos never touch your real `~/.config/hop3-cli`.
3. **Run the selected demos**: each `run(ctx)`; a failure in one doesn't stop the others.
4. **Summary**: results, durations, and (with `--keep`) the admin credentials so you can poke at the live app.

## Boring reliability

Because a demo is also a test, the launcher has to be *boringly reliable*. Getting there taught lessons that bite any harness that runs real deployments in a loop:

- **Non-interactive by construction.** The runner has no human to answer a prompt. Destructive commands (`addon destroy`, `app destroy`) pass `-y`, and every command runs with `stdin` closed; a command that *tries* to prompt gets EOF and fails loud. The alternative is a run wedged forever on an invisible "Are you sure?".
- **Bounded.** Every command has a timeout, so a hung RPC becomes a loud, actionable failure within seconds.
- **Serialized.** Demo runs share an isolated CLI config home *and* mutate a shared target server, so two runs at once would clobber each other's context and collide on server resources. The launcher takes a machine-wide lock and refuses to start a second run: a confound that otherwise produces baffling, "eventually-consistent" flakiness.
- **App-scoped commands take the target as a `--app` flag** (per [ADR 036](/developers/adrs/036-cli-ergonomics/)). The demos are also the first place CLI-ergonomics regressions get caught, because they exercise the command surface the way a user would.
- **Clean failure output.** In quiet mode each demo is one line (`demo10 (PostgreSQL Addon)... FAIL`) with the actionable cause and a log pointer underneath. The raw multi-line command dump stays out of the progress flow.

All of this exists because a test harness that deploys real apps to real servers has to fail *loudly and legibly* when the platform misbehaves. That is why the demos exist.

## How they run in CI

The [test runner](2026-06-testing-runner.md) exercises each demo *in place*: a meta-runner (`DemoTestRunner`) drives `demos/demo.py` and surfaces a non-zero exit as a failed test. So the same script you read to *learn* a feature is the one CI runs to *guard* it; `make test-demos-docker` runs the whole suite against a fresh local container.

## Writing a good one

If you add a demo, the conventions that matter (learned the hard way) are: import `lib` *inside* `run()` (the launcher sets up `sys.path` first); always `--app <name>`; tear down whatever you create so re-runs are reproducible and apps don't coexist by accident; and verify *content* (a `200` proves almost nothing). Existing demos make good templates: `demo01` is the simplest, and there's a broad "CLI surface tour" demo that exercises as much of the command surface as possible in one go.

---

*Part of a five-part series on [how Hop3 is tested](2026-06-how-hop3-is-tested.md). See also [the test runner](2026-06-testing-runner.md) that runs the demos in CI, and [testable docs with validoc](2026-06-testing-validoc.md) for the documentation-as-test counterpart. The demo strategy is decided in [ADR 043 §9](/developers/adrs/043-unified-testing-architecture/).*
