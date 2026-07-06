# ADR 053: Nix Closure Lifetime — keeping a running app's store paths alive across garbage collection

- **Status**: Accepted
- **Type**: Architecture
- **Created**: 2026-07-06
- **Related-ADRs**: 035 (build-artifacts), 008 (nix-builders-2), 006 (nix-integration)

## Context

A Nix-packaged app runs from its build output in `/nix/store`. Its runtime wrapper execs **hardcoded store paths** — for example, a `nixpkgs-wrapper` app's generated wrapper execs `${pkg}/bin/<name>`, a second store path baked into the wrapper at build time. The app's runtime closure (that output plus everything it references) must therefore stay on disk for as long as the app runs.

Nothing about `nix-build` guarantees that. `nix-store --gc` reclaims any store path that no live **GC root** protects, and a garbage collect can fire for two reasons Hop3 does not control:

1. **Disk pressure** — Nix auto-collects when free space drops below `min-free`.
2. **A scheduled sweep** — a host or channel image may ship a periodic `nix-gc.timer`.

When a GC reclaims a path inside a *running* app's closure, the worker dies with `No such file or directory`. This is a **heisenbug**: it depends on whether — and exactly when — a collect happened relative to the deploy, so it passes in isolation and fails intermittently under load or after another app churns the store. Worse, the only symptom is a slow health-check timeout, minutes after the real event, with no pointer to the reclaimed path.

There are also **windows where Hop3's own rooting is ineffective** even when a GC root exists:

- `nix-build --no-out-link` roots nothing.
- A naïve "keep the previous build rooted" rotation that moves the out-link with a filesystem rename does **not** carry the root: Nix registers an *indirect* root as `gcroots/auto/<hash-of-abspath> → <link>`, keyed on the link's path; renaming the link leaves that auto-entry pointing at a name that no longer exists, so the renamed symlink is a plain dangling link, not a root.
- Rotating the root *before* the new build has produced its own root leaves the still-running previous closure unrooted for the whole multi-minute rebuild.

## Decision

Keep every running app's Nix runtime closure alive with **three complementary mechanisms**, each closing a different surface of the same class.

### 1. Per-app indirect GC roots, registered before rotation

Each build registers the current runtime closure as an indirect GC root at `<app>/.nix-result` (`nix-build --out-link`). Across a rebuild, **before** the new build starts, the immediately-prior closure is re-rooted at `<app>/.nix-result-prev` via `nix-store --realise <old-path> --add-root <app>/.nix-result-prev --indirect`.

- A root is **registered, never renamed** — only `nix-store --add-root … --indirect` produces a valid `gcroots/auto` entry; a `rename` cannot move a root.
- Registration happens **before** the build, so the old closure a still-running worker execs is never unrooted during the rebuild.
- Both roots live in the **app directory**, so destroying the app removes them and lets Nix reclaim the closure — teardown stays symmetric, roots do not leak.

### 2. Auto-GC pinned off on the server

The server install writes `min-free = 0` to `nix.conf` and disables `nix-gc.timer`. Neither disk-pressure nor scheduled collection fires between deploys. Reclaiming the store becomes a **deliberate operator action** run at a safe time, not a background event that can delete a live closure.

### 3. Deploy-time closure-integrity pre-flight

Before a Nix app's workers start, the run phase verifies that every path in each worker's runtime closure (`nix-store -q --requisites` on the worker's store-path root) still exists on disk, and **aborts with a named, actionable error** if one was reclaimed — rather than letting the worker crash-loop into a health-check timeout.

- The check is **deploy-time, not build-time**: at build time the closure exists by construction (it was just realised), so the reclaim it guards against can only appear later.
- It is **best-effort**: if `nix-store` cannot answer (absent from PATH, times out) it logs and continues — a guard that cannot run must never block an otherwise-working deploy.

## Rationale

**Why all three, not one.** They address different failure surfaces and reinforce each other:

- Roots protect the closures Hop3 knows about, but cannot cover a transient unrooted window or a path outside a rooted set.
- Pinning GC off removes the *trigger* — the external collect that turns any residual window lethal — and is the single change that most directly ends the intermittency.
- The pre-flight assumes the first two can still fail (a misconfigured host, a manual `nix-collect-garbage`) and makes the failure **loud and early** instead of a silent slow timeout.

Defense-in-depth is warranted because the failure is non-deterministic: a robust fix must *remove the non-determinism*, not merely retry into it.

**Why fail loud (mechanism 3).** A reclaimed closure is an unrecoverable state for that worker — it cannot exec a deleted binary. Surfacing it as an early, named error with the reclaimed path (and "redeploy to rebuild") is aligned with Hop3's principle that errors are never silent; a 180-second health-check timeout is the opposite.

**Why per-app roots in the app directory.** The app is the unit Hop3 creates and destroys. Rooting in the app dir ties the closure's lifetime to the app's lifetime automatically, so no separate reaping step is needed and roots cannot accumulate.

## Consequences

### Positive

- A running Nix app survives a garbage collect; the outcome is deterministic across runs.
- A genuinely broken closure fails **fast and loud**, with the reclaimed path and a remedy, instead of a delayed timeout.
- Per-app roots are freed on teardown — no leaked roots, no unbounded root set.

### Negative

- The run phase now assumes `nix-store` is reachable on the server for the pre-flight; where it is not, that layer degrades to a no-op and only the first two mechanisms protect the app.
- Pinning auto-GC off trades **disk for predictability**: the store grows until an operator reclaims it deliberately. This is the intended trade — a background collector that can kill a live app is not acceptable on a single-server PaaS — but it makes store housekeeping an explicit operational task.

### Neutral

- One `nix-store -q --requisites` query per Nix worker at spawn.
- Applies only to `kind == "nix"` artifacts; non-Nix apps are unaffected.

## Alternatives Considered

### `keep-outputs` / `keep-derivations` in nix.conf

Keeps build-time dependencies rooted through their derivations. **Rejected:** it does not root the *runtime* closure of an already-realised output against a collect, and it is a coarse global toggle — it does not target the running-app closure this ADR is about.

### A per-app Nix profile (`nix-env -p <app-profile>`)

A profile generation is itself a GC root. **Rejected:** Hop3's apps are built with `nix-build`, not installed into a profile; adopting profiles adds a management layer (generations, rollbacks) for no protection an out-link does not already give.

### A single global GC root over all app closures

Protects everything at once. **Rejected:** it never frees on teardown (roots leak, the store grows without bound) and cannot express per-app lifetime — destroying one app must not keep another's closure pinned.

### Just raise the health-check timeout

**Rejected:** it masks the symptom without fixing it — the worker still cannot exec a deleted path — and it hides a real, actionable failure behind a longer wait.

### Copy the runtime closure out of the store into the app directory

Sidesteps GC entirely. **Rejected:** it discards Nix's deduplication and store integrity and multiplies disk usage; it defeats the reason for using Nix.

## References

- ADR 035: Build Artifacts as Runtime Contract — the wrapper/worker commands the pre-flight inspects, and the `runtime.json` contract the run phase consumes.
- ADR 006 / ADR 008: Nix integration and template generation — the builders that produce these closures.
- [Nix Manual: Garbage Collector Roots](https://nixos.org/manual/nix/stable/package-management/garbage-collector-roots).
