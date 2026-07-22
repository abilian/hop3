# Plan: Replace Pre-Built Binaries with Source Builds

**Status:** ✅ DONE (Phases 1–3 complete). 6 of 7 apps converted via `nixpkgs-wrapper`:
Miniflux, Gitea, Grafana, Mattermost, Vikunja, Wiki.js. Phases 4–5 (custom
`go-module` / `node-package` templates) never needed — `nixpkgs-wrapper`
covered every case. Focalboard remaining (upstream archived 2023; recommend
drop, covered by Vikunja). The document below is preserved as a record of the
design and decision trail.

**Created:** 2026-04-09
**Closed:** 2026-04-18
**Goal:** Eliminate pre-built binary reliance for 7 Nix-packaged apps
**Ref:** ADR 008, `notes/experience-reports/00-aggregate.md`

---

**Reproducibility status (2026-06-22, for the NGI 0.7 review).** This plan delivered *source builds* — converting opaque `prebuilt-binary` apps to `nixpkgs-wrapper`, removing the x86_64-only, trust-the-vendor-binary problem. It did **not** deliver *reproducible* builds in the full Nix sense, and the "reproducible, multi-arch" phrasing in Approach A below overreaches on its own:

- **nixpkgs is now pinned (shipped in 0.6.1, M1/M2).** Every generated and hand-crafted expression imports a specific nixpkgs commit (nixos-24.11) via `import (fetchTarball { url; sha256; }) {}` — no moving channel, and `<nixpkgs>`/`NIX_PATH` is never consulted — so two builds on different dates/hosts resolve the same nixpkgs. (When this plan closed in 2026-04, expressions still used the ambient `import <nixpkgs> {}` against the moving channel; that gap is now closed.)
- **A per-app pin override exists (2026-07).** The single global pin can be too old for a package added to nixpkgs later — etherpad-lite entered nixpkgs only in nixos-25.05, while the default is 24.11 — so the `nixpkgs-wrapper` template accepts an optional `[nix].nixpkgs-rev` / `nixpkgs-sha256` that overrides the global pin for one app (rejected loudly on templates that can't honour it, so it never silently no-ops). This softens Approach A's "pinned to one nixpkgs version" disadvantage without giving up reproducibility.
- ~~**Some builds are not hermetic.**~~ **Closed (2026-07).** The `python-venv` / `pnpm` / `composer` paths no longer set `__noChroot`; each vendors its dependency set into a fixed-output derivation from a committed lockfile and then builds offline in the sandbox. The floating-dependency escape went with it — `pip-packages` was retired, and a recipe that still carries the key is now rejected by name rather than silently ignored.
- Of the two Definition-of-Done items below, the **ADR 008 reproducibility-tier update is done** (2026-07: the tiers were rewritten to rank provenance now that sandbox purity is uniform, and each template declares its tier in code). **aarch64 remains open by decision, not omission**: a vendored dependency set is resolved per platform, so supporting a second architecture means vendoring a second set, and the reproducibility claim is scoped to x86_64 explicitly.

The accurate baseline is **ADR 008's reproducibility-tiers table**, which names these gaps explicitly (it does not overclaim). The remaining levers — hermetic fixed-output dependency derivations, lock-pinned deps, and a reproducibility CI gate — are the **Nix-reproducibility workstream tracked in `release-plan-0.7.md` (M1/M2)**: pinning nixpkgs landed in the 0.7 cut, and the hermetic-build work is 0.7.x. Treat this file as the source-build decision trail; treat 0.7/0.7.x as where "full Nix philosophy / reproducible builds" is actually delivered.

---

## Context

7 of 20 Nix-packaged apps use `prebuilt-binary`, `prebuilt-archive`,
or `node-prebuilt` templates that download upstream release binaries.
This is not reproducible, not portable (x86_64 only), and carries
supply chain risk.

## Two Approaches

### Approach A: `nixpkgs-wrapper` (preferred where possible)

Many of these apps are **already packaged in nixpkgs** with proper
source builds. The `nixpkgs-wrapper` template (already working for
Radicale) wraps an existing nixpkgs package with Hop3's runtime
metadata (env vars, config files, workers). Zero custom build logic.

**Advantages:**
- Zero Nix packaging effort per app
- Inherits nixpkgs' source builds (reproducible, multi-arch)
- Maintained by the Nix community (security updates)
- Already proven (Radicale works)

**Disadvantages:**
- Pinned to the nixpkgs version in the Nix channel
- Can't easily patch or use a specific upstream version
- Some apps may have different defaults than what we need

### Approach B: Custom source-build templates

For apps not in nixpkgs, or where we need version control, write new
templates: `go-module` (using `buildGoModule`) and `node-package`
(using `buildNpmPackage`).

**Advantages:**
- Full control over version, patches, build flags
- Can pin exact upstream commit/tag
- Not dependent on nixpkgs update cycle

**Disadvantages:**
- Significant effort per template + per app
- Need to compute and maintain `vendorHash` / `npmDepsHash`
- Hash changes on every dependency update

## Per-App Recommendation

| App | In nixpkgs? | Recommended approach | Effort |
|-----|-------------|---------------------|--------|
| Miniflux | Yes (`pkgs.miniflux`) | nixpkgs-wrapper | 30 min |
| Gitea | Yes (`pkgs.gitea`) | nixpkgs-wrapper | 1 hour |
| Grafana | Yes (`pkgs.grafana`) | nixpkgs-wrapper | 1 hour |
| Mattermost | Yes (`pkgs.mattermost`) | nixpkgs-wrapper | 1 hour |
| Vikunja | Maybe (`pkgs.vikunja`) | nixpkgs-wrapper or go-module | 1-2 hours |
| Wiki.js | Yes (`pkgs.wiki-js`) | nixpkgs-wrapper | 1 hour |
| Focalboard | Unlikely | go-module (if maintained) or defer | 4+ hours |

**Total estimated effort:** 6-10 hours (if nixpkgs-wrapper works
for most apps) vs 30-40 hours (if custom source builds needed).

## Implementation Plan

### Phase 1: Validate nixpkgs-wrapper for Go apps (1 day)

Start with Miniflux (simplest Go app, single binary, env-var config).

**Steps:**
1. Check that `pkgs.miniflux` exists and builds on current nixpkgs
2. Create `apps/real-apps-nix-gen/miniflux/hop3.toml` with
   `template = "nixpkgs-wrapper"` and `nixpkgs-package = "miniflux"`
3. Keep the existing env vars, config, and `[[addons]]` — only the
   build method changes
4. Test with `hop3-test system --ssh --with nix,postgres`
5. Verify the binary works, connects to PostgreSQL, serves HTTP

**What stays the same:**
- `[env]`, `[env.computed]`, `[[addons]]`, `[healthcheck]`
- `[nix.conditional-env]` for DATABASE_URL
- The test.toml validation

**What changes:**
- `template = "prebuilt-binary"` → `template = "nixpkgs-wrapper"`
- Remove `url`, `sha256`, `binary-name` fields
- Add `nixpkgs-package = "miniflux"`
- Remove `exec` (wrapper uses the package's default binary)

**Success criteria:** Miniflux deploys, connects to PostgreSQL,
serves HTTP 200 on /healthcheck — same as before, but now built
from source by Nix.

### Phase 2: Roll out to remaining nixpkgs apps (1 day)

Apply the same pattern to Gitea, Grafana, Mattermost, Wiki.js.

For each app:
1. Verify `pkgs.<name>` exists and builds
2. Switch hop3.toml to `nixpkgs-wrapper`
3. Adapt wrapper config (exec target may differ from prebuilt)
4. Test end-to-end
5. Compare: does the nixpkgs build produce the same functionality?

**Potential issues:**
- **Gitea**: nixpkgs version may differ from our pinned version.
  The `app.ini` config generation must still work.
- **Grafana**: nixpkgs `grafana` may bundle frontend differently.
  Check that `custom.ini` and `GF_PATHS_*` env vars still apply.
- **Mattermost**: nixpkgs build may not include all plugins.
  The asset symlinking pattern in pre-exec may need adjustment.
- **Wiki.js**: nixpkgs `wiki-js` may have a different directory
  layout than the upstream release archive. Symlink patterns may
  break.

### Phase 3: Handle apps not in nixpkgs (2-3 days)

**Vikunja:** Check if `pkgs.vikunja` exists. If yes, use
nixpkgs-wrapper. If no, this is the first candidate for a
`go-module` template.

**Focalboard:** Mattermost archived this project in 2023. Consider:
- If still in nixpkgs: use nixpkgs-wrapper
- If not: keep pre-built with documented limitation, or drop from
  the supported app set (it's unmaintained upstream)

### Phase 4: New `go-module` template (if needed) (2-3 days)

Only needed if some apps aren't in nixpkgs. Creates a new template
that generates a `buildGoModule` derivation.

**Template inputs (new AppSpec fields):**
```toml
[nix]
template = "go-module"
go-version = "1.22"       # optional, defaults to latest
vendor-hash = "sha256-..."  # from go.sum, required
tags = ["sqlite"]          # Go build tags
ldflags = "-s -w -X main.Version=${version}"  # optional
subpackages = ["cmd/server"]  # which Go packages to build
```

**Template output:**
```nix
pkgs.buildGoModule {
  pname = "...";
  version = "...";
  src = pkgs.fetchFromGitHub { ... };
  vendorHash = "...";
  tags = [ ... ];
  ldflags = [ ... ];
  subPackages = [ ... ];
  postInstall = '' ... runtime.json ... '';
}
```

**Challenge:** Computing `vendorHash`. Options:
- `nix-prefetch` tooling (manual, per-app)
- Set to `lib.fakeHash`, build, read error, paste real hash
- Document the workflow in a playbook

### Phase 5: New `node-package` template (if needed) (2-3 days)

Only needed if Wiki.js can't use nixpkgs-wrapper. Template for
`buildNpmPackage`.

**Template inputs:**
```toml
[nix]
template = "node-package"
node-version = "22"
npm-deps-hash = "sha256-..."
npm-build-script = "build"  # optional
```

## Nixpkgs-wrapper Template: What Needs to Change

The current `nixpkgs-wrapper` template already works for Radicale.
Let me check if it needs enhancements for Go apps.

**Current `nixpkgs-wrapper` capabilities:**
- Wraps `pkgs.<name>` with a shell script
- Generates `runtime.json` with worker entry
- Supports env vars, config files, pre-exec commands

**Likely needed enhancements:**
- The exec target for Go apps is typically `$out/bin/<name>` but
  the wrapper needs to know the binary name (it may differ from
  the package name — e.g., `pkgs.vikunja` binary is `vikunja`)
- Some apps need `$out/share/<name>/` in PATH or as working dir
- Config file generation (INI, YAML, JSON) already supported

**May need a new field:**
```toml
[nix]
template = "nixpkgs-wrapper"
nixpkgs-package = "gitea"
binary-name = "gitea"       # if different from package name
data-dir = "$out/share/gitea"  # if app needs it
```

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| nixpkgs version too old/new | Medium | App features differ | Pin nixpkgs channel; test thoroughly |
| nixpkgs package layout differs from release | Medium | Wrapper script breaks | Compare `nix build` output with release archive; adjust paths |
| `vendorHash` changes on updates | High (for go-module) | Builds break | Document hash update workflow; prefer nixpkgs-wrapper |
| Some apps removed from nixpkgs | Low | Must fall back to go-module | Monitor nixpkgs; keep pre-built as fallback |
| Build time significantly longer | Medium | Slower deployments | Cache Nix store; first build is slow, rebuilds are fast |

## Definition of Done

For each app:
- [ ] `hop3-test` passes (HTTP validation, correct status)
- [ ] `nix-build` succeeds on both x86_64 and aarch64 (if possible)
- [ ] No `fetchurl` of pre-built binaries in the derivation
- [ ] Experience report updated
- [ ] ADR 008 reproducibility tier updated (Tier 3 → Tier 1 or 2)

## Timeline

| Phase | Duration | Apps |
|-------|----------|------|
| Phase 1: Miniflux validation | 0.5 day | Miniflux |
| Phase 2: nixpkgs-wrapper rollout | 1 day | Gitea, Grafana, Mattermost, Wiki.js |
| Phase 3: Remaining apps | 1 day | Vikunja, Focalboard (evaluate) |
| Phase 4: go-module template | 2-3 days | Only if needed |
| Phase 5: node-package template | 2-3 days | Only if needed |
| **Total (optimistic)** | **2.5 days** | nixpkgs-wrapper works for all |
| **Total (pessimistic)** | **8 days** | Custom templates needed |
