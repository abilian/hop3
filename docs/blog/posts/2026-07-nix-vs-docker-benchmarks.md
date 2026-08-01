---
date: 2026-07-17
template: blog_post.html
description: A first, single-sample benchmark of four build strategies across twenty applications. The Nix paths deploy 1.4× faster than Docker and land within 12–18% of a native build; thirty of thirty generated recipes rebuild bit-for-bit.
tags:
  - Engineering
  - Testing
  - NGI
---

# A Preliminary Benchmark: Nix Deploys Faster Than Docker

The received wisdom about Nix is that you adopt it for reproducibility and pay for it in speed. Long builds, a cold store, an afternoon lost to a `.drv` you did not write.

Across twenty applications and four build strategies, the median deploy came out:

| Build strategy | Median deploy |
|---|---|
| Native toolchain | 98 s |
| **Nix (hand-written expression)** | **110 s** |
| **Nix (generated from `hop3.toml`)** | **116 s** |
| Docker | 163 s |

The Nix paths land within 12–18% of a native build and are roughly **1.4–1.5× faster than Docker**. That is the opposite of what most people expect, including us.

These are **preliminary** figures. The matrix has been run twice, a week apart, each time on a host rebuilt from a blank operating system, so the medians above are replicated; but each individual cell is still a single sample, and there are no confidence intervals. That is enough to establish an ordering and not enough to make a claim about any one application. The harness, the protocol and the raw data are in the repository, so the fastest way to disagree with any of this is to re-run it.

The second run put the numbers at 106 s native, 101 s nix, 122 s nix-gen and 166 s docker. Everything moved by 4–8%, in both directions, and the ordering held.

## What was measured

An 80-cell matrix: twenty applications (the ones in Hop3's catalog: real software with databases and background workers) each deployed under four strategies.

The corpus was read from a `protocol.yaml` committed before the run, so the app set could not be quietly adjusted afterwards to make a number look better. The target was a dedicated box, blank-slated by a full OS rebuild. A `docker system prune` leaves the cache warm, and a warm cache is exactly the thing that makes a benchmark like this meaningless. Everything runs through a `hop3-bench` harness and lands as JSONL in the repository; the tables in this post are regenerated from that data by a script, and no figure here was typed by hand.

71 of 80 cells completed. Of the nine that did not, six were applications with no recipe for that strategy and three were genuine failures, all app-level rather than runtime-level. Docker was the only strategy with all twenty.

## Why Nix comes out ahead

Two mechanisms, and neither is subtle once you look.

**Docker rebuilds; Nix substitutes.** A Docker deploy pulls a base image and executes the build steps in the Dockerfile. Layer caching helps on a second deploy of the same app, but the first deploy on a fresh box does the whole thing. A Nix build resolves a derivation graph and fetches whatever it can from a binary cache. For a Python or Node app, that means most of the closure (the interpreter, the compiler toolchain, the system libraries) arrives pre-built instead of being installed.

**The store is shared; images are not.** Deploy a second Django app and Docker builds a second image with its own copy of Python. Nix realises the second app's closure against a store that already contains that Python, and pays only for what differs. On a box running several apps on similar stacks (which is the whole premise of a single-server PaaS) the difference compounds.

## The result that actually matters

Speed is a nice headline. Reproducibility is why Nix is in Hop3 at all, and it is the claim we can now measure instead of assert.

**Thirty of thirty template-generated recipes rebuild bit-for-bit identical.** Build twice, compare store paths, they match.

Getting there took most of a year and three distinct fixes:

- **Pinning.** Every generated and hand-written expression now imports a specific nixpkgs commit through `fetchTarball` with its hash. `<nixpkgs>` and `NIX_PATH` are never consulted, so two builds on different days on different hosts resolve the same package set. An app that needs something newer than the global pin can override it for itself, and the override is rejected loudly on templates that cannot honour it; never silently ignored.
- **Sandbox purity.** The Python, pnpm and Composer paths used to set `__noChroot`, which is Nix's escape hatch for "this build needs the network". They do not any more: each vendors its dependency set into a fixed-output derivation from a committed lockfile, then builds offline in the sandbox.
- **No floating dependencies.** The old `pip-packages` key let a recipe name unversioned dependencies. It was retired, and a recipe that still carries it is now rejected by name: a build that resolves "whatever PyPI has today" is not reproducible no matter how pure the sandbox is.

The claim is **scoped to x86_64** deliberately. A vendored dependency set is resolved per platform; supporting a second architecture means vendoring a second set. We state one architecture plainly instead of implying two. [ADR 058](/developers/adrs/058-build-reproducibility-model/) sets out the tiers, and each template declares which one it is in, in code.

## The control plane

What the platform costs you when it is doing nothing: Hop3's control plane sits at **185 MB**. A K3s control plane measured like-for-like on the same box sits at **1441 MB**, or **7.8× heavier**. For a single server running a handful of apps, that difference is a meaningful fraction of a small VPS.

## How we nearly got that wrong

The first way we measured control-plane memory was the cgroup's `memory.current`, which is the obvious thing to read and what most tooling reports. It gave a number that moved by roughly **8×** depending on when we looked, because `memory.current` includes page cache. Run a deploy, read the file, and the "control plane" appears to have grown by a gigabyte. That gigabyte is page cache: the kernel caching files it will drop the moment anything needs the memory.

Proportional set size does not have that problem. So the figures here are PSS, taken on a freshly rebuilt box before anything warmed the cache, and the cgroup readings are kept as a separate series rather than mixed in.

A benchmark whose value depends on how warm the machine was is not a benchmark.

## What would make this final

**Per-cell repeats.** The matrix has been repeated, but at the level of whole runs: each cell within a run is still a single sample, so we can say the *ordering* replicates and not what any one application's deploy time is. The next pass is N≥3 per cell.

**Isolating the ordering effect.** All four strategies ran sequentially on one machine, so later strategies inherited a warmer page cache. Here that works against Nix, since Docker ran last. It is a confound, and rotating the order removes it; arguing about it does not.

**Pre-registration that is real.** The corpus was committed before the run; the result skeletons were not. Committing those too, ahead of the repeat runs, is what would let us call the protocol pre-registered without stretching the word.

Until those land, every figure here is labelled preliminary wherever it appears, including in the project's technical report.

---

*Data and harness: `notes/benchmarks/` and the `hop3-bench` tooling in the [Hop3 repository](https://github.com/abilian/hop3). Reproducibility model: [ADR 058](/developers/adrs/058-build-reproducibility-model/). Nix integration: [ADR 006](/developers/adrs/006-nix-integration/) and [ADR 008](/developers/adrs/008-nix-builders-2/).*