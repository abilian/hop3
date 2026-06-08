# ADR 008: Template-Based Nix Expression Generation

**Status**: Final
**Type**: Feature
**Created**: 2024-07-17
**Updated**: 2026-04-22
**Related-ADRs**: 006, 007 (superseded), 009, 020, 022, 030, 031, 035, 036
**Depends-On**: ADR 006 Phase 1 (completed)

## Revisions

- v0.1: Initial draft (2024-07-17)
- v0.4: Reframed from "lockfile conversion" to "on-the-fly generation at build time," initially proposing ecosystem tools (poetry2nix, dream2nix, node2nix) (2026-04-04).
- v0.5: Major rewrite. Ecosystem-tools approach abandoned in favour of a template-based approach that systematises the manual conversion patterns (2026-04-05).
- v0.6: Promoted to Final. ADR 007 (the originally-planned separate nixpkgs-mode builder) marked Superseded since `nixpkgs-wrapper` covers that case (2026-04-14).

## Context

### What We Have (Phase 1 — Done)

The NixBuilder plugin (ADR 006, implemented Q1 2026) builds applications from hand-crafted `hop3.nix` files. This works well but requires the developer to write a Nix derivation — a significant barrier given Nix's well-documented learning curve (see Fourné et al., "It's like flossing your teeth: On the importance and challenges of reproducible builds," IEEE S&P 2023). We have 22 production-grade apps with hand-crafted `hop3.nix` files; writing each one took meaningful effort and Nix expertise.

### The Problem

The current situation creates a two-tier experience:

- **With `hop3.nix`**: Content-addressed dependency graph, bandwidth-efficient updates, and a path toward reproducible builds (see "Reproducibility Levels" below for honest caveats). But requires Nix expertise.
- **Without `hop3.nix`**: Fast native builds via the LocalBuilder, but no reproducibility guarantees and no content-addressed closure. This is what most developers will use.

We want to close this gap: give developers the structural benefits of Nix (content-addressed closures, atomic upgrades, minimal update deltas) without requiring them to learn the Nix expression language.

### Reproducibility Levels: Honest Assessment

The term "reproducible builds" is often used loosely. In Hop3's context, the actual guarantee depends on the build type:

| Build type | Hermetic sandbox | Reproducible | Auditable | Example |
|---|---|---|---|---|
| **Pure Nix** (pinned nixpkgs, all deps from Nix store) | Yes | Yes (modulo build tool quirks like timestamps) | Yes (full closure graph to source) | Go apps via `buildGoModule` with vendored deps |
| **Nix with `__noChroot`** (pip, composer install at build time) | **No** — network access during build | **No** — depends on PyPI/Packagist state at build time | Partial — closure exists but sources aren't pinned | BookStack (composer), Isso (pip) |
| **Nix with `fetchurl` pre-built binary** (sha256-pinned) | Yes (fixed hash) | Yes (same bytes every time, as long as URL is live) | **No** — can't rebuild from source; trusting upstream binary | Gitea, Miniflux, Grafana |
| **Native builder (no Nix)** | No | No | No | Most apps today |

**Key nuances:**

1. **`__noChroot = true` breaks hermeticity.** Our `python-venv` and `php-app` (with composer) templates use this to allow network access during build. Two builds on different days can fetch different dependency versions from PyPI/Packagist. This is no better than `pip install` on the host — the Nix packaging is structural (content-addressed output, atomic rollback) but not hermetic.

2. **Pre-built binaries are reproducible but not auditable.** Fetching a Gitea binary with a pinned sha256 guarantees you always get the same bytes. But you can't verify what those bytes contain — you're trusting the upstream release process. This is the same trust model as pulling a Docker image from Docker Hub, just with a content hash instead of a mutable tag.

3. **Source availability is not guaranteed.** Even pure Nix builds depend on upstream sources being available. If PyPI deletes a package or a GitHub release disappears, the build fails. Nix doesn't mirror sources by default (though the Nix binary cache and NixOS Hydra CI provide some resilience).

4. **True hermeticity requires pure Nix builds with vendored or Nix-packaged dependencies.** This is achievable (e.g., `buildGoModule` with vendored deps, or all Python packages from nixpkgs rather than pip). But it's significantly more work to set up and maintain, which is why our current templates take the pragmatic `__noChroot` shortcut.

**What Nix DOES guarantee in all cases:**

- **Content-addressed outputs.** Every built package has a unique store path derived from all its inputs. If the inputs change, the output path changes. If inputs are identical, the path is identical — enabling cache reuse across machines.
- **Atomic upgrades and rollbacks.** Deployments are a symlink switch. Rolling back is instant and side-effect-free.
- **Minimal update deltas.** When updating an app, only changed store paths need to be transferred (Proposition 1 from the paper). This holds even for `__noChroot` builds — the delta is still smaller than a Docker image layer replacement.
- **Explicit dependency graph.** The full closure is inspectable via `nix-store -qR`. No hidden dependencies, unlike Docker's opaque layers or pip's global site-packages.

**Implication for the template approach:** The generated `hop3.nix` expressions provide the structural benefits of Nix (content-addressing, atomic upgrades, closure inspection) but do NOT automatically provide full hermeticity for ecosystems that use `__noChroot`. Moving from `__noChroot` pip/composer to fully-pinned Nix-native dependency resolution is a future evolution (Phase 4), not a template concern. The templates faithfully generate what a human would write today.

### Why Not Ecosystem Tools (Revised Position)

The v0.4 of this ADR proposed using ecosystem-specific Nix tools: `poetry2nix`, `dream2nix`, `node2nix`, `buildGoModule`, `crane`, etc. This turned out to be the wrong approach for three concrete reasons discovered during the spike:

1. **None of our 22 existing `hop3.nix` files use them.** Grep across `apps/real-apps-nix/` finds zero references to `poetry2nix`, `dream2nix`, `node2nix`, or `buildGoModule`. The Ruby test apps use `bundlerEnv` (a built-in nixpkgs function), and everything else uses plain `stdenv.mkDerivation` with `fetchurl` and custom `installPhase`.

2. **The ecosystem tools don't cover half our stack.** `poetry2nix` handles Python-with-poetry only. `dream2nix` is in flux. `node2nix` is effectively deprecated. There's no equivalent for **PHP** (our largest ecosystem, 10 apps), Java, or pre-built binaries. Building on tools that don't cover half the fleet is a losing proposition.

3. **The manual conversion pattern is highly regular.** Analysing all 22 hand-written files showed ~60% boilerplate and ~40% per-app logic. The per-app logic is expressible declaratively (paths, env vars, config file contents, exec commands). A template system is a better fit than composing external tools.

## Decision

When the operator selects the Nix builder and no `hop3.nix` file exists, Hop3 will **generate one at build time from a declarative template specification** stored in `hop3.toml`. The generated Nix expression is equivalent to what a developer would write by hand following the patterns observed in `apps/real-apps-nix/`.

The generator is **plugin-based**: each template is a registered plugin implementing a simple `Template` protocol. Adding a new ecosystem means adding a new template — not modifying existing ones.

### Fallback Hierarchy

```
hop3.nix exists in source?
  → Yes: Use it directly (ADR 006 Phase 1, current behavior)
  → No:  hop3.toml has [nix] section with template name?
    → Yes: Generate hop3.nix from template at build time
    → No:  Fall back to LocalBuilder with native toolchains
```

### Ejection

When a generated template cannot express an app's needs, the developer runs `hop3 nix eject <app>` to materialize the generated `hop3.nix` as a real file in the source tree. After ejection, the committed `hop3.nix` takes precedence and can be customized freely. This mirrors Create React App's eject pattern: auto-generation is progressive disclosure, not lock-in.

## Validated Templates

Seven templates cover **20 of 22 apps** in `apps/real-apps-nix/`, each verified to build via `nix-build`.

| Template | Apps covered | Count | Key patterns |
|----------|-------------|-------|-------------|
| `prebuilt-binary` | miniflux, gitea | 2 | Single pre-compiled binary, exec args, INI config generation, runtime secret generation |
| `prebuilt-archive` | focalboard, grafana, mattermost, vikunja | 4 | tar.gz/zip archives, file mappings, store-to-cwd symlink loops (mattermost), JSON/YAML/INI configs |
| `php-app` | adminer, bookstack, dolibarr, easy-appointments, invoice-ninja, kanboard, limesurvey, matomo, nextcloud, wordpress | 10 | Single file (adminer), composer build, Laravel artisan serve, custom web root (dolibarr), zip with wrapper dir (limesurvey), tar.bz2 (nextcloud), `--ignore-platform-reqs` (invoice-ninja), extra nativeBuildInputs (nodejs for invoice-ninja) |
| `node-prebuilt` | wiki-js | 1 | Tarball without top-level dir, read-only store symlink loop, YAML config |
| `java-war` | jenkins | 1 | Single WAR file, JDK runtime, `$JAVA_OPTS` |
| `python-venv` | isso | 1 | `__noChroot`, pip install inside nix build, runtime INI config |
| `nixpkgs-wrapper` | radicale | 1 | Wraps existing nixpkgs package (no source fetch, no build) |
| **Total** | | **20/22** | |

Remaining: `sinatra-hello`, `rack-hello` (Ruby test apps using `bundlerEnv`) — would be covered by an 8th `ruby-bundler` template.

## Design Overview

### AppSpec Data Model

A declarative spec with fields grouped by concern:

- **Identity**: `pname`, `version`, `description`, `template`
- **Source**: `url`, `sha256`, `archive` (None/tar-gz/tar-bz2/tar-xz/zip), `executable`
- **Extraction**: `source_root` (for archives with wrapper dirs), `strip_components`
- **Runtime setup**: `runtime_package` (e.g., `jdk17`, `nodejs_22`), `php_version`, `php_extensions`, `nixpkgs_package`
- **Build phase**: `needs_composer`, `composer_extra_flags`, `extra_native_build_inputs`, `pip_packages`
- **Serving**: `exec_target`, `exec_args`, `serve_mode` (`builtin`/`artisan`/`custom`), `web_root`
- **Wrapper script**: `local_vars`, `env_exports`, `conditional_env_exports`, `pre_exec_commands`, `config_files`
- **Runtime metadata**: `runtime_env`, `extra_paths`

### Placeholder Pattern

Each template uses sed-replaced placeholders for Nix variables that need to be resolved to absolute store paths at build time:

| Placeholder | Template | Resolves to |
|------------|----------|-------------|
| `BINDIR` | all | `$out/bin` |
| `SHAREDIR` | prebuilt-archive | `$out/share/<pname>` |
| `APPDIR` | php-app, node-prebuilt | `$out/app` |
| `PHPBIN` | php-app | `${php}/bin` (the withExtensions php) |
| `NODEBIN` | node-prebuilt | `${nodejs}/bin` |
| `JAVABIN`, `WARPATH` | java-war | `${jdk}/bin`, `$out/app/<file>.war` |
| `VENVBIN` | python-venv | `$out/venv/bin` |
| `PKGBIN` | nixpkgs-wrapper | `${package}/bin` |

The placeholder pattern is simpler than trying to interleave Nix interpolation with shell escaping inside a multi-line Nix string. Nix evaluates the store paths first; sed then replaces the placeholders in the wrapper script at install time.

### Nix Escaping

Inside a Nix `''...''` multi-line string, only `${VAR}` needs escaping (becomes `''${VAR}`). Bare `$VAR`, `$(cmd)`, and `$PWD` pass through literally. A small `nix_escape()` regex function handles all cases.

## Implementation Status

Shipped: the generator is productionized in the `NixBuilder` plugin tree (`plugins/build/nix/gen/`). `hop3.toml` carries a `[nix]` section; `NixBuilder.accept()` builds apps that declare `[nix].template`, generating the `.nix` at build time (and refusing when both a hand-written `hop3.nix` and a `[nix].template` are present). The template set covers the documented stacks, including `ruby-bundler`.

## Consequences

### Benefits

- **Lowers Nix barrier to near-zero.** Operators describe their app declaratively in `hop3.toml`; the generator handles everything else.
- **Progressive disclosure via eject.** Developers can drop to hand-crafted `hop3.nix` when needed without changing their workflow.
- **Same BuildArtifact output.** The rest of the pipeline (deployer, proxy, etc.) is unchanged. The generator is purely a build-time source transformation.
- **Extensible.** New templates are pure plugins — third parties can publish ecosystem-specific templates as separate packages.
- **Validated end-to-end.** 20 real apps across 7 templates build correctly on a real system, not just in theory.

### Drawbacks

- **Per-template maintenance.** Each template has to be kept in sync with nixpkgs conventions and upstream app changes. Mitigated by the fact that each template is small (~150 lines Python + tests) and the patterns are stable (we're not chasing moving targets like poetry2nix releases).
- **Edge cases escape through `nix:eject`.** Apps that don't fit templates still require hand-crafted files. The 91% coverage (20/22) validates that this is manageable, not catastrophic.
- **Duplication during migration.** While migrating, an app can have both a hand-crafted `hop3.nix` *and* a `[nix]` section in `hop3.toml`; they're migrated one at a time, verifying each step.

## Lessons

Concrete findings that shaped the design:

1. **Roughly 60% boilerplate, not 90%.** Apps like Mattermost (60-line wrapper with symlink loops, JSON config, runtime secret generation) and Invoice Ninja (composer with `--ignore-platform-reqs` + nodejs in build inputs) have real per-app logic that can't be fully abstracted. The template system must be parametric enough to accommodate this.

2. **Placeholder sed-replacement beats in-place Nix interpolation.** Putting `${nodejs}/bin` directly inside the wrapper heredoc conflicts with shell variable escaping (`${PORT:-8080}` also needs special handling). Using placeholders (`NODEBIN`, `PHPBIN`, etc.) that get sed-replaced after Nix interpolation is simpler and composes cleanly.

3. **Unquoted heredocs are the right default for runtime config files.** Apps need `${PORT}` and `$(head -c 32 /dev/urandom | base64)` to be evaluated at container startup, not at build time. The `cat > config << EOF` (unquoted) pattern handles both.

4. **Some apps always need hand-crafting.** Apps with known upstream issues (complex build systems, deprecated dependencies) aren't magically fixed by templates. The template approach scales the easy cases so developers spend hand-crafting effort only where it matters.

5. **Validating with actual `nix-build` catches bugs pattern-matching can't.** Real builds surfaced two bugs that passed both unit tests and `nix-instantiate --parse` (exec-line escaping, and a generated-config indentation bug). End-to-end validation via real builds is essential.

## Prior Art

- **nixpacks** (Railway): Validates the template-based approach at production scale. Uses nixpkgs primitives, not dream2nix/poetry2nix, confirming our direction. https://nixpacks.com/
- **dream2nix / poetry2nix / node2nix**: Ecosystem-specific Nix tools we explicitly don't use. They aim for pure-Nix dependency resolution but each covers only one ecosystem and has known stability issues. Our template approach uses `__noChroot` as a pragmatic shortcut — see "Reproducibility Levels" for the trade-off.
- **Create React App eject**: The precedent for the "auto-generate then customize" pattern.
- **Heroku buildpacks**: Same UX goal (auto-detect and build without user config), different technology.

## References

- E. Dolstra, "The Purely Functional Software Deployment Model," Ph.D. thesis, Utrecht University, 2006. https://edolstra.github.io/pubs/phd-thesis.pdf — The theoretical foundation for content-addressed package management and the guarantees Nix does (and doesn't) provide.
- M. Fourné, D. Wermke, W. Enck, S. Fahl, and Y. Acar, "It's like flossing your teeth: On the importance and challenges of reproducible builds for software supply chain security," IEEE S&P 2023. https://doi.org/10.1109/SP46215.2023.10179320 — Documents the learning curve barrier as the #1 obstacle to reproducible build adoption.
- C. Lamb and S. Zacchiroli, "Reproducible Builds: Increasing the Integrity of Software Supply Chains," IEEE Software, vol. 39, no. 2, pp. 62–70, 2022. https://doi.org/10.1109/MS.2021.3073045 — Defines what "reproducible builds" means precisely (bit-for-bit identical outputs from identical inputs) vs the weaker guarantees most tools actually provide.
- NixOS Wiki, "Nix Pills," https://nixos.org/guides/nix-pills/ — Practical guide to Nix expression language, relevant for understanding what the templates generate.
- Railway, "How Nixpacks Works," https://nixpacks.com/docs/how-it-works — Documents Railway's template-based approach which we validated independently.
