---
date: 2026-06-19
template: blog_post.html
series: How Hop3 is Tested
series_order: 3
description: How Hop3 keeps its tutorials correct — validoc runs the documentation's own commands against a real server and asserts the results.
tags:
  - Testing
  - Documentation
  - Engineering
---

# Testable Docs: Tutorials That Run Themselves

Documentation rots faster than code, and tutorials rot fastest of all. A tutorial is a *promise*: "type these commands in this order and you'll get this result." The moment a flag changes, an output format shifts, or a default moves, the promise breaks — silently, because nothing executes a tutorial except a frustrated newcomer.

Hop3's answer is **validoc**: tutorials are Markdown files whose code blocks are *executed and asserted* against a real Hop3 server. The document is the test. [ADR 043](/developers/adrs/043-unified-testing-architecture/) calls it a "literate-test substrate," and it's one of Hop3's three test runners — the one that **verifies the docs match reality**.

## The idea: literate tests

A validoc block runs against a real server. Three fence types do the work:

- **`bash exec`** — run a shell command (optionally in a working directory, with a timeout).
- **`output`** — assert that the preceding command's output matches.
- **`file`** — materialize a file as the reader is told to create it.

Here is a real slice of the Go/Fiber tutorial (`docs/tutorials/go/fiber.md`):

````markdown
Initialize the project:

```bash exec id=create-project
mkdir hop3-tuto-fiber && cd hop3-tuto-fiber go mod init hop3-tuto-fiber
```

Install Fiber:

```bash exec id=install-fiber dir=hop3-tuto-fiber timeout=60
go get github.com/gofiber/fiber/v2
```

...then deploy it:

```bash exec id=deploy dir=hop3-tuto-fiber timeout=120
hop3 deploy --app hop3-tuto-fiber
```
````

When validoc runs this file, it *actually* creates the project, *actually* installs Fiber, and *actually* deploys the app — against a freshly-provisioned Hop3 server. If `hop3 deploy --app …` ever stops working the way the tutorial says, the tutorial fails in CI, loudly, the same night. The reader's promise is now a regression test.

The `id`, `dir`, and `timeout` attributes are the only ceremony: they name the step (for diagnostics), pin a working directory across blocks, and bound a slow build.

## Source vs. rendered: two trees, one truth

There's a subtlety that, once understood, explains validoc's whole file layout. The executable markers (`exec`, `output`, `file`, the `id=`/`dir=` attributes) are great for a *test runner* and noise for a *human reader*. So there are two trees:

| Tree | Contents | Audience |
|------|----------|----------|
| `docs/tutorials/` | **source** — Markdown *with* the validoc markers | validoc (and authors) |
| `docs/src/tutorials/` | **rendered** — markers stripped, plain code blocks | the published docs site |

You **author in the source tree**; a convert step strips the markers and writes the rendered tree that ships on the website. The reader on the docs site sees a clean, ordinary tutorial; validoc sees the same words as an executable test plan.

This split has one sharp edge, worth stating because it bit us:

> A tutorial with **zero** executable blocks isn't being tested at all — validoc exits `0` with "0 passed", which looks like a (vacuous) pass. The usual cause is pointing the runner at the *rendered* tree (`docs/src/tutorials`), where the markers are already stripped, instead of the *source* (`docs/tutorials`).

So the tutorial runner *counts* the fences in each file and flags "scanned a file but found nothing executable" as suspicious. A passing test that ran nothing is the most dangerous kind of green.

## How it runs

validoc tutorials are driven through the same single deploy-and-verify path as everything else (one of the consolidations in [ADR 043](/developers/adrs/043-unified-testing-architecture/)). The `TutorialTestRunner` discovers tutorials, provisions a real Hop3 server via the `DeploymentTarget` abstraction, runs each tutorial's blocks in order, and — like every other runner that touches a real server — collects the shared diagnostic bundle on failure: nginx logs, the app's journal, the HTTP exchange, and the silent-502 proxy probe. A tutorial that deploys an app and then can't reach it produces exactly the same one-line classifier (`proxy-502`, `build-failure`, …) as a demo or a real-app test.

This replaced a one-off `scripts/run-all-tutorials.py` that stood up its own server and verified apps its own way — the fourth parallel copy of deploy-and-verify that the unification set out to delete. Tutorials are now first-class catalog entries, run nightly across multiple Linux distributions and reported by the [Test Lab](2026-06-testing-testlab.md).

## Beyond tutorials

The "literate test" substrate is more general than the docs it started with. A validoc file is really just *a CLI scenario with assertions, written as prose*. That makes it the natural home for long, narrative, end-to-end flows that would be unreadable as Python — "create an app, attach Postgres, set a secret, scale to two workers, take a backup, restore it, verify the data" reads beautifully as a Markdown walkthrough and runs beautifully as a test. The docs are simply where it started.

## Why this matters

The deepest reason is *trust*. A platform's documentation is part of its product surface. If a newcomer's very first experience is a tutorial whose third command errors out, no amount of clever architecture will win them back. validoc makes "the docs are correct" a thing CI can prove, every night, against real servers — so the promise the tutorial makes is one Hop3 actually keeps.

---

*Part of a five-part series on [how Hop3 is tested](2026-06-how-hop3-is-tested.md). validoc is the documentation-facing sibling of [the demos](2026-06-testing-demos.md) (capability-facing) and is run by [the test runner](2026-06-testing-runner.md). See [ADR 043: Unified Testing Architecture](/developers/adrs/043-unified-testing-architecture/) for where it sits in the whole.*
