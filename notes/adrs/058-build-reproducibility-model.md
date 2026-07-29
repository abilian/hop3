# ADR 058: Build Reproducibility Model

- **Status**: Accepted
- **Type**: Architecture
- **Created**: 2026-07-22
- **Related-ADRs**: [008](./008-nix-builders-2.md) (template generation), [006](./006-nix-integration.md) (nix integration), [013](./013-supply-chain.md) (supply chain), [033](./033-docker-integration.md) (docker), [039](./039-python-deploy-strategies.md) (python deploy), [044](./044-nightly-test-lab.md) (nightly test lab)

## Context

Reproducibility is the platform's headline quality claim: the property that lets a third party rebuild a deployment from the same inputs and check they got what we say they get. A claim of that weight has to be stated precisely enough to be falsified, and stated in one place, because it constrains every path by which Hop3 builds an application (the three Nix tiers, the native toolchain, and Docker), including the paths that never touch the expression generator.

It is therefore specified here, at one remove from any single builder. [ADR 008](./008-nix-builders-2.md) describes how Nix expressions are generated and defers to this document for what their output must guarantee; [ADR 013](./013-supply-chain.md) builds its supply-chain argument on the tiers below; [ADR 044](./044-nightly-test-lab.md) owns running the checks on a schedule.

## Decision

"Reproducible build" is used loosely enough to be worthless as a claim, so Hop3 states a precise one, per build path.

### Sealed builds across every ecosystem

Every template builds inside the Nix sandbox against hash-pinned inputs: nixpkgs is pinned to a commit, the source archive is pinned by sha256, and the dependency set is pinned by a lockfile whose resolved contents are themselves fixed by a hash. Each ecosystem's package manager therefore runs **offline**, in a two-phase pattern generalised from `buildGoModule`'s `vendorHash`. A fixed-output derivation vendors the dependency set (the only step permitted to touch the network, and content-addressed so its result is fixed), and the application then builds in the sealed sandbox against that directory.

| Ecosystem | Lockfile | Vendoring derivation |
|---|---|---|
| Python | `requirements.txt` (hash-pinned) | wheels/sdists fetched into a FOD; install with `--no-index` |
| PHP | `composer.lock` | `composer install` in a FOD; offline `dump-autoload` |
| Node | `pnpm-lock.yaml` | `pnpm fetch` (reads only the lockfile); install `--frozen-lockfile --ignore-scripts` |
| Go | `go.sum` | `buildGoModule` `vendorHash` |
| Ruby | `Gemfile.lock` + `gemset.nix` (bundix) | `bundlerEnv` |
| Java | `deps.json` (Gradle `mitmCache`) | `gradle.fetchDeps` |

### The three tiers

Sandbox purity is therefore uniform. The tiers rank the axis that still varies, **the provenance of the running bytes**: whether they can be traced back to reviewable source, and who did the tracing.

| Tier | What it is | Sealed build | Bit-identical rebuild | Auditable to source | Packaged by | Multi-arch |
|---|---|---|---|---|---|---|
| **1. nixpkgs** | Wraps a package nixpkgs already builds from source | Yes | Yes | Yes | nixpkgs | Yes |
| **2. source** | Hop3 builds the app from source against a hash-pinned dependency set | Yes | Yes | Yes | Hop3 | One arch per lockfile |
| **3. prebuilt** | Fetches an upstream release binary or archive by sha256 | Yes (fixed-output) | Yes | **No** | upstream | Usually x86_64 only |

Tier 1 outranks Tier 2 despite both being auditable, because the difference is who carries the maintenance. A `nixpkgs-wrapper` app inherits nixpkgs' build, its multi-arch coverage and its security updates at no cost to us, while a Tier-2 app is packaging Hop3 owns, with lockfiles we must refresh. Tier 1 is unavailable whenever nixpkgs lacks the app, or carries it only at a version we cannot deploy. That is the common case for this corpus, which is why Tier 2 holds most of it.

### Where the native and Docker builders sit

Both sit below the tiers.

- **Native builder.** Dependency versions are pinned; a Python app is refused outright if its requirements float, per [ADR 039](./039-python-deploy-strategies.md). The build itself runs on the host, with network access and against whatever system libraries happen to be installed, so it has no seal. Repeatable in practice, guaranteed by nothing.
- **Docker builder.** Base images are digest-pinned and app versions are explicit, while `RUN` steps have unrestricted network access and image builds embed timestamps. Bit-identical rebuilds are not claimed, and Hop3 makes no attempt to seal Docker ([ADR 033](./033-docker-integration.md)).

### What a tier does not tell you

A tier describes the *build*. It says nothing about the *running application*. An app can rebuild bit-for-bit and still fail to boot: a native addon that was never compiled, a locale directory absent from the static root, or a process manager scoped to a test-only dependency group are all invisible to a hash comparison. Advertising an app therefore requires both halves, the rebuild check and a clean deploy.

Nix guarantees the following at every tier:

- **Content-addressed outputs.** A package's store path derives from all its inputs. Identical inputs yield an identical path, so the cache can be shared across machines.
- **Atomic upgrades and rollbacks.** A deployment is a symlink switch; rollback is instant and side-effect-free.
- **Minimal update deltas.** An update transfers only the changed store paths. Docker replaces whole layers.
- **Explicit dependency graph.** The full closure is inspectable with `nix-store -qR`: no hidden dependencies, unlike Docker's opaque layers or pip's global `site-packages`.

No tier guarantees upstream source availability. If PyPI yanks a package or a GitHub release disappears, the build fails at every tier; a hash pins *which* bytes are required, and whether anyone still serves them is a separate question. The binary cache and Hydra provide partial resilience, and mirroring the vendored FODs is the real answer.

**Architectural scope.** x86_64 is the platform for which reproducibility is claimed. Vendored dependency sets are resolved per platform (a Linux wheel set differs from a macOS one, and an aarch64 wheel set from an x86_64 one), so the committed lockfiles fix one architecture. Supporting a second means vendoring a second set; no hash is relaxed.

### Per-app labels

The tier is declared on the *template*, since the template determines how the artefact is obtained, and an app inherits it by choosing a template. Nothing maintains a per-app list by hand, because a hand-maintained table drifts out of truth while continuing to look authoritative.

```
hop3-tools nix tiers apps/real-apps-nix-gen
```

reads each recipe's `[nix].template` and prints its tier. It needs neither Nix nor a server, so an auditor can run it against a checkout. A template that changes how it obtains its artefact must move tier, and the registry tests fail if it does not.

### Checking the claim

A reproducibility claim that nothing exercises decays into a marketing sentence. Two checks exercise it, and the advertised gate is their conjunction:

- `hop3-tools nix check-reproducible` builds each recipe, then rebuilds it with `nix build --rebuild`, which compares the second output against the first. Output drift is reported as a *result* (the app is not reproducible) and distinguished from a build that failed for some other reason, which must never be read as a pass. An empty selection fails the gate.
- The deploy check (`make test-nix`) deploys the same corpus and exercises it over HTTP.

`make gate-nix` runs both, in that order. An app is advertise-ready only when it rebuilds identically **and** runs.

### Classifying a failure

A gate that answers only pass/fail throws away the information that decides who acts. The same red result can mean three unrelated things, and conflating them costs real time: a fixed-output hash mismatch reported as *"output is not deterministic"* sends someone hunting a reproducibility bug that does not exist, when the true remedy is one command.

Outcomes are therefore classified, and the classification is part of the contract:

| Outcome | What happened | Who acts |
|---|---|---|
| **reproducible** | The rebuild matched the first build | nobody |
| **stale hash** | A *pinned* fixed-output hash no longer matches | mechanical: re-derive it |
| **eval error** | An attribute was renamed or removed upstream | a human picks a replacement |
| **not deterministic** | Two builds of one derivation disagree | the defect the gate exists to catch |
| **build failed** | Anything else | read the log |

The ordering matters. A fixed-output mismatch is checked before the determinism patterns, because it names a pin that has gone stale, while the determinism patterns describe a build that varies under fixed inputs. Moving the nixpkgs pin makes *stale hash* the ordinary, expected outcome across much of the corpus; a model that could not say so would report a routine maintenance operation as a fleet-wide reproducibility failure.

### Moving the pin

Every generated expression pins nixpkgs to a commit, and an application may override that pin for itself when it needs a package the default predates. The override is per-application, validated where it is parsed (a malformed revision is refused at parse time, before it can reach an expression that fails opaquely at deploy), and honoured by every template, so the corpus can be evaluated wholesale against a candidate pin without editing each recipe.

That last property turns a pin bump into a *measurement*. A bump can invalidate an unbounded number of vendored dependency hashes at once, and it can remove attributes an application depends on. Both outcomes are expected, both are distinguishable by the classification above, and the resulting per-application disposition is the artefact: it says what the pin costs before anyone commits to paying it.

Measuring it first matters because the pin is a shared resource and a bump is close to all-or-nothing. The corpus builds against one revision, so the revision cannot move until every recipe builds against the candidate, and a single blocked application withholds the security updates of all the others. The per-application override is the pressure valve, and it relieves pressure by fragmenting: an application parked on its own revision is an application whose nixpkgs must be maintained separately from the rest. Used deliberately for a package the default predates, that is a reasonable exception. Used to route around a bump, it converts one revision to maintain into several.

This is the trade the Nix path makes. Integration work that a distribution performs once on behalf of all its users moves to whoever owns the pin. Tier 1 hands that work back to nixpkgs, which is the substantive reason it outranks Tier 2 despite both being auditable.

### What the seal covers

The sandbox fixes a build's *inputs*: the source archive, the dependency set, the toolchain, each by hash. It does not fix how the tools consuming those inputs behave. One recipe in the corpus makes the distinction concrete. Its vendored dependency set hashed identically under two nixpkgs revisions, and its package manager was the same version in both, yet the installed tree differed, because the surrounding standard environment had changed. The newer environment also carried a check that declined to ship the result, so the difference surfaced at build time instead of at runtime.

Identical inputs are necessary for a reproducible build without being sufficient. Determinism is therefore established by rebuilding and comparing rather than by reasoning over input hashes. A pin bump can change a build's output while changing none of its pinned inputs, so its cost is measured per application rather than inferred.

A newer standard environment can introduce a check no recipe previously had to satisfy. Such a failure resembles neither a stale hash nor a missing attribute, and routing it to "read the log" is the correct disposition: the remedy is specific to whatever the new check found.

## Alternatives considered

**A single flat claim ("Hop3 builds are reproducible").** Shorter, and unfalsifiable. It would also have to be withdrawn the first time someone examined a Tier-3 wrapper and found an upstream binary nobody can audit. A claim that cannot survive its own audit is worth less than a narrower one that can.

**Ranking the tiers by sandbox purity.** The original taxonomy did this, when `__noChroot` builds still existed and the axis carried real information. Once every template vendors its dependencies and builds offline, purity is uniform and a ranking along it distinguishes nothing. Keeping the old axis would have implied that Tier-2 and Tier-3 builds are less deterministic than Tier-1, which measurement contradicts.

**One pass/fail outcome per app.** Simpler to report and to store. It also conceals who has to act: a stale hash is a mechanical re-derivation, and genuine non-determinism is a defect hunt, and a single red square cannot tell an operator which one arrived.

**Committed golden hashes of each generated expression.** This would catch a generator change that silently alters output. The vendored dependency hashes already serve that purpose where it matters: a template change that alters what enters a fixed-output derivation makes the committed hash wrong, and the build fails loudly at deploy. A second set of golden values would add maintenance and catch only cosmetic drift.

**Per-app tier labels maintained by hand.** Tried, in the form of a table in [ADR 008](./008-nix-builders-2.md). It drifted: apps moved between templates while the table kept its original wording and continued to read as authoritative. Deriving the label from the template removes the opportunity.

## Consequences

- **The claim is checkable by a third party**, from a checkout and a Nix installation, without access to our infrastructure. Precision is the point of stating it at all.
- **The tiers rank provenance, and only provenance.** All three rebuild identically, so determinism separates none of them; reporting it as though it did would overstate what the top tier buys.
- **A tier is not a promise the application runs.** The gate's second half exists because bit-identical rebuilds have repeatedly coexisted with broken boots.
- **Reproducibility is relative to a pin, an architecture, and upstream still serving the bytes.** Each is stated explicitly, because each has failed in practice. The pin carries a recurring cost as well as a caveat: moving it is a fleet-wide operation gated on the slowest recipe, and it recurs on the upstream release cadence.
- **The model constrains the templates.** A new template must vendor its ecosystem's dependency set into a fixed-output derivation and build offline; otherwise it does not qualify for Tier 2 and must say so.
