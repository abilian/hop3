# ADR 008: Template-Based Nix Expression Generation

- **Status**: Final
- **Type**: Feature
- **Created**: 2024-07-17
- **Supersedes**: [ADR 007](./007-nix-builder.md)
- **Related-ADRs**: [006](./006-nix-integration.md), [009](./009-nix-runtime.md), [020](./020-pluggable-architecture.md), [022](./022-build-deploy-plugin-system.md), [030](./030-two-level-build-architecture.md), [031](./031-project-terminology.md), [035](./035-build-artifacts.md), [036](./036-cli-ergonomics.md)

## Context

### What We Have

The NixBuilder plugin ([ADR 006](./006-nix-integration.md)) builds applications from hand-crafted `hop3.nix` files. This works well but requires the developer to write a Nix derivation: a significant barrier given Nix's well-documented learning curve (see Fourné et al., "It's like flossing your teeth: On the importance and challenges of reproducible builds," IEEE S&P 2023). The production fleet of hand-crafted `hop3.nix` files demonstrates the model, but writing each one takes meaningful effort and Nix expertise.

### The Problem

The current situation creates a two-tier experience:

- **With `hop3.nix`**: Content-addressed dependency graph, bandwidth-efficient updates, and a path toward reproducible builds (see "Reproducibility Levels" below for the precise caveats). But requires Nix expertise.
- **Without `hop3.nix`**: Fast native builds via the LocalBuilder, but no reproducibility guarantees and no content-addressed closure. This is what most developers will use.

We want to close this gap: give developers the structural benefits of Nix (content-addressed closures, atomic upgrades, minimal update deltas) without requiring them to learn the Nix expression language.

### Reproducibility Levels

The term "reproducible builds" is often used loosely. In Hop3's context, the actual guarantee depends on the build type:

| Build type | Hermetic sandbox | Reproducible | Auditable | Example |
|---|---|---|---|---|
| **Pure Nix** (pinned nixpkgs, all deps from Nix store) | Yes | Yes (modulo build tool quirks like timestamps) | Yes (full closure graph to source) | Go apps via `buildGoModule` with vendored deps |
| **Nix with `__noChroot`** (pip, composer install at build time) | **No** (network access during build | **No**) depends on PyPI/Packagist state at build time | Partial: closure exists but sources aren't pinned | BookStack (composer), Isso (pip) |
| **Nix with `fetchurl` pre-built binary** (sha256-pinned) | Yes (fixed hash) | Yes (same bytes every time, as long as URL is live) | **No**: can't rebuild from source; trusting upstream binary | Gitea, Miniflux, Grafana |
| **Native builder (no Nix)** | No | No | No | Most apps today |

**Key nuances:**

1. **`__noChroot = true` breaks hermeticity.** Our `python-venv` and `php-app` (with composer) templates use this to allow network access during build. Two builds on different days can fetch different dependency versions from PyPI/Packagist. This is no better than `pip install` on the host: the Nix packaging is structural (content-addressed output, atomic rollback) but not hermetic.

2. **Pre-built binaries are reproducible but not auditable.** Fetching a Gitea binary with a pinned sha256 guarantees you always get the same bytes. But you can't verify what those bytes contain: you're trusting the upstream release process. This is the same trust model as pulling a Docker image from Docker Hub, just with a content hash instead of a mutable tag.

3. **Source availability is not guaranteed.** Even pure Nix builds depend on upstream sources being available. If PyPI deletes a package or a GitHub release disappears, the build fails. Nix doesn't mirror sources by default (though the Nix binary cache and NixOS Hydra CI provide some resilience).

4. **True hermeticity requires pure Nix builds with vendored or Nix-packaged dependencies.** This is achievable (e.g., `buildGoModule` with vendored deps, or all Python packages from nixpkgs rather than pip). But it's significantly more work to set up and maintain, which is why our current templates take the pragmatic `__noChroot` shortcut.

**What Nix DOES guarantee in all cases:**

- **Content-addressed outputs.** Every built package has a unique store path derived from all its inputs. If the inputs change, the output path changes. If inputs are identical, the path is identical: enabling cache reuse across machines.
- **Atomic upgrades and rollbacks.** Deployments are a symlink switch. Rolling back is instant and side-effect-free.
- **Minimal update deltas.** When updating an app, only changed store paths need to be transferred (Proposition 1 from the paper). This holds even for `__noChroot` builds: the delta is still smaller than a Docker image layer replacement.
- **Explicit dependency graph.** The full closure is inspectable via `nix-store -qR`. No hidden dependencies, unlike Docker's opaque layers or pip's global site-packages.

**Implication for the template approach:** The generated `hop3.nix` expressions provide the structural benefits of Nix (content-addressing, atomic upgrades, closure inspection) but do NOT automatically provide full hermeticity for ecosystems that use `__noChroot`. Moving from `__noChroot` pip/composer to fully-pinned Nix-native dependency resolution is a future evolution. The templates faithfully generate what a developer would write by hand.

### Why Not Ecosystem Tools

An obvious alternative is to use ecosystem-specific Nix tools: `poetry2nix`, `dream2nix`, `node2nix`, `buildGoModule`, `crane`, etc. This is the wrong approach for three concrete reasons:

1. **The hand-written `hop3.nix` files don't use them.** The existing files in `apps/real-apps-nix/` contain no references to `poetry2nix`, `dream2nix`, `node2nix`, or `buildGoModule`. The Ruby apps use `bundlerEnv` (a built-in nixpkgs function), and everything else uses plain `stdenv.mkDerivation` with `fetchurl` and a custom `installPhase`.

2. **The ecosystem tools don't cover the stack.** `poetry2nix` handles Python-with-poetry only. `dream2nix` is in flux. `node2nix` is effectively deprecated. There's no equivalent for PHP (the largest ecosystem in the fleet) nor for Java or pre-built binaries. Building on tools that don't cover half the fleet is a losing proposition.

3. **The manual conversion pattern is highly regular.** The hand-written files are roughly 60% boilerplate and 40% per-app logic. The per-app logic is expressible declaratively (paths, env vars, config file contents, exec commands). A template system is a better fit than composing external tools.

## Decision

When the operator selects the Nix builder and no `hop3.nix` file exists, Hop3 will **generate one at build time from a declarative template specification** stored in `hop3.toml`. The generated Nix expression is equivalent to what a developer would write by hand following the patterns observed in `apps/real-apps-nix/`.

The generator is **plugin-based**: each template is a registered plugin implementing a simple `Template` protocol. Adding a new ecosystem means adding a new template: not modifying existing ones.

### Fallback Hierarchy

```
hop3.nix exists in source?
  → Yes: Use it directly (ADR 006)
  → No:  hop3.toml has [nix] section with template name?
    → Yes: Generate hop3.nix from template at build time
    → No:  Fall back to LocalBuilder with native toolchains
```

`NixBuilder.accept()` builds an app when it declares `[nix].template`. A hand-written `hop3.nix` and a `[nix].template` are mutually exclusive inputs: when both are present the builder refuses rather than silently choosing one, since the two sources can diverge.

### Ejection

When a generated template cannot express an app's needs, the developer runs `hop3 nix eject <app>` to materialize the generated `hop3.nix` as a real file in the source tree. After ejection, the committed `hop3.nix` takes precedence and can be customized freely. This mirrors Create React App's eject pattern: auto-generation is progressive disclosure, not lock-in.

## Templates

Each template captures one recurring packaging pattern observed in `apps/real-apps-nix/`. The set spans the production stacks:

| Template | Apps covered | Key patterns |
|----------|-------------|-------------|
| `prebuilt-binary` | miniflux, gitea | Single pre-compiled binary, exec args, INI config generation, runtime secret generation |
| `prebuilt-archive` | focalboard, grafana, mattermost, vikunja | tar.gz/zip archives, file mappings, store-to-cwd symlink loops (mattermost), JSON/YAML/INI configs |
| `php-app` | adminer, bookstack, dolibarr, easy-appointments, invoice-ninja, kanboard, limesurvey, matomo, nextcloud, wordpress | Single file (adminer), composer build, Laravel artisan serve, custom web root (dolibarr), zip with wrapper dir (limesurvey), tar.bz2 (nextcloud), `--ignore-platform-reqs` (invoice-ninja), extra nativeBuildInputs (nodejs for invoice-ninja) |
| `node-prebuilt` | wiki-js | Tarball without top-level dir, read-only store symlink loop, YAML config |
| `java-war` | jenkins | Single WAR file, JDK runtime, `$JAVA_OPTS` |
| `python-venv` | isso | `__noChroot`, pip install inside nix build, runtime INI config |
| `nixpkgs-wrapper` | radicale | Wraps existing nixpkgs package (no source fetch, no build) |
| `ruby-bundler` | sinatra-hello, rack-hello | `bundlerEnv` from a Gemfile, rack-based serving |

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

## Consequences

### Benefits

- **Lowers Nix barrier to near-zero.** Operators describe their app declaratively in `hop3.toml`; the generator handles everything else.
- **Progressive disclosure via eject.** Developers can drop to hand-crafted `hop3.nix` when needed without changing their workflow.
- **Same BuildArtifact output.** The rest of the pipeline (deployer, proxy, etc.) is unchanged. The generator is purely a build-time source transformation.
- **Extensible.** New templates are pure plugins: third parties can publish ecosystem-specific templates as separate packages.
- **Validated end-to-end.** Templates are exercised against real apps that build on a real system via `nix-build`.

### Drawbacks

- **Per-template maintenance.** Each template has to be kept in sync with nixpkgs conventions and upstream app changes. This is mitigated by keeping each template small and by the stability of the patterns: there is no moving target like poetry2nix releases to chase.
- **Edge cases escape through `nix:eject`.** Apps that don't fit any template still require hand-crafted files. This is manageable rather than catastrophic: the template set covers the bulk of the fleet, and ejection handles the rest.
- **Duplication during migration.** While migrating, an app can have both a hand-crafted `hop3.nix` *and* a `[nix]` section in `hop3.toml`; they are migrated one at a time, verifying each step.

## Design Findings

Concrete observations that shape the design:

1. **Boilerplate dominates but does not exhaust.** The bulk of a hand-written file is boilerplate, but a substantial fraction is real per-app logic. Apps like Mattermost (wrapper with symlink loops, JSON config, runtime secret generation) and Invoice Ninja (composer with `--ignore-platform-reqs` plus nodejs in build inputs) cannot be fully abstracted. The template system must be parametric enough to accommodate this rather than assuming the per-app remainder is negligible.

2. **Placeholder sed-replacement beats in-place Nix interpolation.** Putting `${nodejs}/bin` directly inside the wrapper heredoc conflicts with shell variable escaping (`${PORT:-8080}` also needs special handling). Using placeholders (`NODEBIN`, `PHPBIN`, etc.) that get sed-replaced after Nix interpolation is simpler and composes cleanly.

3. **Unquoted heredocs are the right default for runtime config files.** Apps need `${PORT}` and `$(head -c 32 /dev/urandom | base64)` to be evaluated at container startup. The `cat > config << EOF` (unquoted) pattern handles both.

4. **Some apps always need hand-crafting.** Apps with known upstream issues (complex build systems, deprecated dependencies) aren't magically fixed by templates. The template approach scales the easy cases so developers spend hand-crafting effort only where it matters.

5. **Validating with actual `nix-build` catches bugs pattern-matching can't.** Real builds surface bugs that pass both unit tests and `nix-instantiate --parse`: exec-line escaping and generated-config indentation being the classes that slip through static checks. End-to-end validation via real builds is therefore part of the design.

## Prior Art

- **nixpacks** (Railway): Validates the template-based approach at production scale. Uses nixpkgs primitives, not dream2nix/poetry2nix, confirming our direction. https://nixpacks.com/
- **dream2nix / poetry2nix / node2nix**: Ecosystem-specific Nix tools we explicitly don't use. They aim for pure-Nix dependency resolution but each covers only one ecosystem and has known stability issues. Our template approach uses `__noChroot` as a pragmatic shortcut: see "Reproducibility Levels" for the trade-off.
- **Create React App eject**: The precedent for the "auto-generate then customize" pattern.
- **Heroku buildpacks**: Same UX goal (auto-detect and build without user config), different technology.

## References

- E. Dolstra, "The Purely Functional Software Deployment Model," Ph.D. thesis, Utrecht University, 2006. https://edolstra.github.io/pubs/phd-thesis.pdf: The theoretical foundation for content-addressed package management and the guarantees Nix does (and doesn't) provide.
- M. Fourné, D. Wermke, W. Enck, S. Fahl, and Y. Acar, "It's like flossing your teeth: On the importance and challenges of reproducible builds for software supply chain security," IEEE S&P 2023. https://doi.org/10.1109/SP46215.2023.10179320: Documents the learning curve barrier as the #1 obstacle to reproducible build adoption.
- C. Lamb and S. Zacchiroli, "Reproducible Builds: Increasing the Integrity of Software Supply Chains," IEEE Software, vol. 39, no. 2, pp. 62–70, 2022. https://doi.org/10.1109/MS.2021.3073045: Defines what "reproducible builds" means precisely (bit-for-bit identical outputs from identical inputs) vs the weaker guarantees most tools actually provide.
- NixOS Wiki, "Nix Pills," https://nixos.org/guides/nix-pills/: Practical guide to Nix expression language, relevant for understanding what the templates generate.
- Railway, "How Nixpacks Works," https://nixpacks.com/docs/how-it-works: Documents Railway's template-based approach which we validated independently.
