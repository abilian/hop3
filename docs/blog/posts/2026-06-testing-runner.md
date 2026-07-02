---
date: 2026-06-19
template: blog_post.html
series: How Hop3 is Tested
series_order: 4
description: Why Hop3 needed a bespoke test runner beyond pytest, what it takes to run it, and the one deploy-and-verify path it owns.
tags:
  - Testing
  - Engineering
  - CI
---

# The Test Runner: Why `hop3-test` Exists

pytest is a wonderful tool for testing *code*. Testing *a catalog of seventy real applications — each deployed to a real server across several Linux distributions, and checked for what they actually serve over HTTPS* — is a different job, and the one `hop3-test` exists to do. The story of why it had to be built is also the story of a mistake the project had to dig itself out of.

## Why a dedicated runner

Two reasons, one structural and one historical.

**The structural reason: the tests are data.** A platform test says "take *this app directory*, deploy it to *this target*, and assert the homepage contains *this text* and returns *this status*." Multiply that over a catalog of apps (Flask, Django, Rails, Go, Node, PHP, static sites…), each often packaged in several variants (native, Docker, Nix), across several targets (Docker, SSH, cloud) and distros. The result is a *data-driven* matrix discovered from configuration — a shape pytest's collection model handles awkwardly. Each app declares its own test contract right in its `hop3.toml`:

```toml
[test]
priority = "P0"                 # P0 | P1 | P2 — selects the fast subset
tier = "fast"
targets = ["docker", "remote"]
covers = ["python", "flask", "nix"]

[[test.validations]]
path = "/"
status = 200
```

Everything else is *derived*: the test's name from `[metadata].id`, its category from `[build].builder`, its backing services from `[[addons]]`, its base healthcheck from `[healthcheck]`. Apps without a `hop3.toml` (Procfile-only fixtures, demos, tutorials, negative-test cases) carry the same contract in a standalone `test.toml`. The runner *scans* this catalog and turns it into a test plan you can filter by priority, tier, and capability tag on the fly.

**The historical reason: deploy-and-verify had been written four times.** This is the finding that triggered the whole testing rework ([ADR 043](/developers/adrs/043-unified-testing-architecture/)). Four separate code paths — the runner, the pytest Docker fixtures, the demo harness, and a tutorial script — *each* stood up a server and verified an app *independently*, all over the one real `hop3-deploy` primitive. Four copies meant four places for a bug to hide, four diagnostic stories (with inverted coverage — the richest collector was wired only to the cloud path), and no single source of truth for "is this app reachable?".

The fix was to make `hop3-test` own the **one** deploy-and-verify path, behind a single abstraction.

## One primitive: the `DeploymentTarget`

At the centre is the `DeploymentTarget` abstraction — a clean interface over the three places Hop3 can be deployed:

| Target | Flag | When | In routine CI? |
|--------|------|------|----------------|
| Docker container | `--docker` | the default; dev + CI | ✅ the only one wired into routine CI |
| Remote server (SSH) | `--host <ip>` | systemd-specific paths (rootd, nginx reload, `www-data` perms) Docker can't fully exercise | nightly / manual |
| Hetzner Cloud | via `hop3-test matrix` | multi-distro, real-server release validation | release gate |

Every runner that touches a real server — the app tests, the demos, the validoc tutorials, even the pytest `c_e2e` fixtures — now goes through this same primitive. Fix a deploy bug once, and every surface benefits. Collect diagnostics once, and every failure looks the same.

## The command surface

The real, registered surface is small and consistent:

```bash
# What's in the catalog?
hop3-test list

# Deploy Hop3 to a target, then deploy + verify the apps
hop3-test run --docker --clean --with all        # fresh Docker, all addons
hop3-test run --docker --reuse apps/real-apps-native/edrix   # one app, skip redeploy
hop3-test run --host $HOP3_DEV_HOST --with all

# Drive a matrix of cloud OS images (Hetzner)
hop3-test matrix --images ubuntu-24.04,debian-13

# Explain a failure from its saved diagnostic bundle
hop3-test why <run-id> --section nginx|journal|build|http|proxy
```

The lifecycle behind `run` is a small state machine — initialise the target, reset it to a blank slate, deploy Hop3, deploy and verify each app in the plan, then report — with a diagnostic bundle captured for every app *before* teardown, since the logs vanish with the server.

The Makefile wraps the common cases: `make test-apps` (the catalog on Docker), `make test-app APP=<path>` (one app), `make test-list`, `make test-nightly` (the full matrix with an HTML report).

## What you need to run it

The prerequisites follow directly from "it deploys real apps to real machines":

- **For `--docker` (the default):** a working Docker daemon. The runner deploys Hop3 into a container and treats it as the target. This is the path CI uses and the one a developer should reach for first — it needs nothing but Docker and is fast with `--reuse` against a cached image.
- **For `--host`:** a reachable target (Ubuntu 24.04/26.04) with **root, key-based SSH**. This is for the system-level behaviour Docker can't fully reproduce — systemd units, the privileged-operations agent ([ADR 041](/developers/adrs/041-privileged-operations-agent/)), nginx reloads, real file permissions.
- **For cloud targets:** a `HETZNER_API_TOKEN` and an SSH key registered with the provider. The runner provisions throwaway servers, deploys to them, and tears them down for cost control.
- **The catalog itself:** the test apps live under `apps/` (`real-apps-native/`, `real-apps-nix/`, `real-apps-nix-gen/`, `test-apps-procfile/`, `test-apps-nix/`) and the demos under `demos/`. Adding an app to the catalog is as simple as giving it a `[test]` section.

The guiding principle for prerequisites is the same one that governs the whole platform: **Hop3 is responsible for making things work.** When a test fails because a service is misconfigured, that's a Hop3 bug to fix in the platform. The runner's job is to make the gap *visible*; the platform's job is to close it.

## Beyond pass/fail

Because every app routes through one path, every failure produces one shared diagnostic bundle — and crucially, a **proxy probe** that captures the silent-502 class (a healthy app behind a 502 because nginx points at the wrong port). A classifier turns the bundle into a one-line verdict — `proxy-502 / build-failure / addon-unreachable / app-crash / timeout` — and `hop3-test why <run-id>` replays any section. Nothing is dumped inline by default; the full bundle is written to `~/.hop3/test-runs/` and uploaded by CI. This is the difference between "edrix failed" and "edrix is up on :41051 but nginx is proxying :41050 — here's the one-line diff."

## The runner is also a library

One last design choice that pays off at the top of the pyramid: `hop3-test` is a thin CLI over a reusable *engine* (the orchestrator, the catalog scanner, the targets, the diagnostic collector). That same engine is imported as a library by the nightly [Test Lab](2026-06-testing-testlab.md), so a manual `hop3-test` run and a scheduled web-driven run produce identical, comparable results in one shared store. The CLI and the dashboard are two front-ends over one engine. That's how you keep "what the developer runs" and "what the nightly reports" from ever drifting into two truths.

---

*Part of a five-part series on [how Hop3 is tested](2026-06-how-hop3-is-tested.md). The runner executes [the demos](2026-06-testing-demos.md) and [validoc tutorials](2026-06-testing-validoc.md) through one path, and is driven nightly by [the Test Lab](2026-06-testing-testlab.md). Its rationale is [ADR 043: Unified Testing Architecture](/developers/adrs/043-unified-testing-architecture/).*
