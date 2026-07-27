# ADR 008: Template-Based Nix Expression Generation

- **Status**: Final
- **Type**: Feature
- **Created**: 2024-07-17
- **Supersedes**: [ADR 007](./007-nix-builder.md)
- **Related-ADRs**: [006](./006-nix-integration.md), [009](./009-nix-runtime.md), [020](./020-pluggable-architecture.md), [022](./022-build-deploy-plugin-system.md), [030](./030-two-level-build-architecture.md), [031](./031-project-terminology.md), [035](./035-build-artifacts.md), [036](./036-cli-ergonomics.md), [058](./058-build-reproducibility-model.md) (reproducibility model)

## Context

### What We Have

The NixBuilder plugin ([ADR 006](./006-nix-integration.md)) builds applications from hand-crafted `hop3.nix` files. This works well but requires the developer to write a Nix derivation: a significant barrier given Nix's well-documented learning curve (see Fourné et al., "It's like flossing your teeth: On the importance and challenges of reproducible builds," IEEE S&P 2023). The production fleet of hand-crafted `hop3.nix` files demonstrates the model, but writing each one takes meaningful effort and Nix expertise.

### The Problem

The current situation creates a two-tier experience:

- **With `hop3.nix`**: Content-addressed dependency graph, bandwidth-efficient updates, and a path toward reproducible builds (see [ADR 058](./058-build-reproducibility-model.md) for the precise claim). But requires Nix expertise.
- **Without `hop3.nix`**: Fast native builds via the LocalBuilder, but no reproducibility guarantees and no content-addressed closure. This is what most developers will use.

We want to close this gap: give developers the structural benefits of Nix (content-addressed closures, atomic upgrades, minimal update deltas) without requiring them to learn the Nix expression language.

### Reproducibility

The generator's output must satisfy the platform's reproducibility model, specified in [ADR 058](./058-build-reproducibility-model.md): the tier taxonomy, the two-phase vendoring pattern each ecosystem uses, how the claim is checked, and what it is scoped to. It is stated there rather than here because it also governs the native and Docker builders, which have nothing to do with generating Nix expressions.

Two consequences bind this ADR. A template must vendor its ecosystem's dependency set into a fixed-output derivation and then build offline, or it does not qualify as a source build. And a template declares its tier in code, so the per-application label is derived rather than maintained by hand.

### Fetched Software and Your Own

A template either fetches the application or builds what is already there, and almost all of them fetch: a release tarball, an npm package, a nixpkgs attribute, an upstream binary. That is the right default for the corpus, which is third-party software, but it leaves the case a PaaS exists for, an operator pushing their own code, with no route through the generator at all. Such an app can reach Nix only by hand-writing `hop3.nix`, which is the barrier this ADR set out to remove.

The fix is a **local-source mode**: with no `[nix].url`, the recipe directory *is* the application (`src = ./.`), and the template's dependency-pinning machinery applies unchanged. `ruby-bundler` has always worked this way, and `go-source` now does too. Extending it to `php-app`, `python-venv` and `node-pnpm-install` is the remaining work; each needs the same shape, plus a way to express "install this tree" rather than "install this published package".

A dependency-free module is the one case where an absent hash is correct rather than an oversight, so it is spelled explicitly: `go-vendor-hash = "none"` emits `vendorHash = null`. Omitting the key is still refused.

### Why Not Ecosystem Tools

An obvious alternative is to build the generator on ecosystem-specific *third-party* Nix tools: `poetry2nix`, `dream2nix`, `node2nix`, `crane`, and so on. This is the wrong approach for three concrete reasons.

The distinction that matters is between third-party generators and nixpkgs' own builders. The templates use the latter freely (`buildGoModule`, `bundlerEnv`, `gradle.fetchDeps`, `php.withExtensions`), because they ship with the pinned nixpkgs, share its release cadence, and are the mechanism by which each ecosystem's dependency set gets a `vendorHash`. The templates avoid depending on a *separate project* to translate a lockfile into Nix.

1. **The hand-written `hop3.nix` files don't use them.** The files in `apps/real-apps-nix/` contain no references to `poetry2nix`, `dream2nix`, or `node2nix`; they use nixpkgs builtins and plain `stdenv.mkDerivation` with `fetchurl` and a custom `installPhase`. The generator's job is to reproduce what a developer writes by hand, so it inherits that choice.

2. **The ecosystem tools don't cover the stack.** `poetry2nix` handles Python-with-poetry only. `dream2nix` is in flux. `node2nix` is effectively deprecated. There's no equivalent for PHP (the largest ecosystem in the fleet) nor for Java or pre-built binaries. Building on tools that don't cover half the fleet is a losing proposition. The two-phase FOD pattern, by contrast, is uniform across all six ecosystems: each supplies a lockfile and a way to install from a directory.

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

When a generated template cannot express an app's needs, the developer runs `hop3 nix eject <app>` to materialize the generated `hop3.nix` as a real file in the source tree. After ejection, the committed `hop3.nix` takes precedence and can be customized freely. This mirrors Create React App's eject pattern: auto-generation follows progressive disclosure: you can always eject.

## Templates

Each template captures one recurring packaging pattern observed in `apps/real-apps-nix/`. The set spans the production stacks:

| Template | Tier | Apps covered | Key patterns |
|----------|------|-------------|-------------|
| `nixpkgs-wrapper` | 1 | grafana, mattermost, listmonk, keycloak, searxng, etherpad | Wraps an existing nixpkgs package (no source fetch, no build); writable-home prelude for apps that write beside themselves |
| `php-app` | 2 | adminer, bookstack, dolibarr, easy-appointments, invoice-ninja, kanboard, limesurvey, matomo, nextcloud, paheko, wordpress | Composer FOD from `composer.lock` + offline `dump-autoload`; single file (adminer), Laravel artisan serve, custom web root (dolibarr), zip with wrapper dir (limesurvey), tar.bz2 (nextcloud), `--ignore-platform-reqs` (invoice-ninja), extra nativeBuildInputs (nodejs for invoice-ninja) |
| `python-venv` | 2 | isso, bugsink, radicale | Wheel-set FOD from a hash-pinned lockfile, offline `--no-index` install, runtime INI config |
| `go-source` | 2 | miniflux, gitea, forgejo, gatus, owncast, vikunja | `buildGoModule` with a `vendorHash`; frontend derivation and `go-static-dirs` for apps resolving assets under a static root; builds the recipe directory itself when no `url` is given |
| `node-pnpm-install` | 2 | directus | `pnpm fetch` FOD, offline `--frozen-lockfile --ignore-scripts` install, opt-in offline `node-gyp` rebuild for named native addons |
| `ruby-bundler` | 2 | redmine | `bundlerEnv` from a committed `Gemfile.lock` + bundix `gemset.nix`, `force_ruby_platform` so gems build from source |
| `java-gradle` | 2 | stirling-pdf | Gradle build against a committed `deps.json` (`gradle.fetchDeps` / `mitmCache`) |
| `node-prebuilt` | 3 | wiki-js | Tarball without top-level dir, read-only store symlink loop, YAML config |
| `java-war` | 3 | jenkins | Single WAR file, JDK runtime, `$JAVA_OPTS` |
| `prebuilt-binary` | 3 | *(none)* | Single pre-compiled binary, exec args, INI config generation, runtime secret generation |
| `prebuilt-archive` | 3 | *(none)* | tar.gz/zip archives, file mappings, store-to-cwd symlink loops, JSON/YAML/INI configs |

Tier 3 is a floor for an app that could be built from source; the templates that serve it are working as intended. The corpus has largely walked off it. `prebuilt-binary` and `prebuilt-archive` currently have no consumers: gitea and miniflux moved to `go-source`, grafana and mattermost to `nixpkgs-wrapper`, and isso from a network-enabled pip install to a vendored wheel set. Each move was a one-line template change in `hop3.toml`, which is the property the declarative spec exists to provide.

The two now-unused templates stay, for reasons that outlive their current consumer count:

- **Quick-and-dirty packaging.** Getting an app running should not require producing a lockfile first. Pointing `prebuilt-archive` at a release tarball is the shortest path from "I want this app" to a deployment, and it is a reasonable place to stop for an internal tool nobody audits.
- **Proprietary software.** An app distributed only as a binary cannot be source-built by anyone, at any tier. Tier 3 is not a compromise there; it is the entire available ceiling, and a PaaS that refused to express it would simply be unable to deploy that class of software.
- **The upstream ships no buildable source for the packaged version**, which is why jenkins and wiki-js remain Tier 3; nixpkgs packages both from the upstream artefact too.

The tier exists to make that trade-off legible. It must never stay implicit: a Tier-3 app is deployed on trust in its publisher, and the operator is entitled to know that before deciding.

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

- **nixpacks** (Railway): Validates the template-based approach at production scale. Uses nixpkgs primitives (rather than dream2nix/poetry2nix), confirming our direction. https://nixpacks.com/
- **dream2nix / poetry2nix / node2nix**: Third-party Nix generators we explicitly don't build on. They aim for pure-Nix dependency resolution but each covers one ecosystem and has known stability issues. The templates reach the same result through nixpkgs' own builders and a uniform two-phase FOD: see [ADR 058](./058-build-reproducibility-model.md).
- **Create React App eject**: The precedent for the "auto-generate then customize" pattern.
- **Heroku buildpacks**: Same UX goal (auto-detect and build without user config), different technology.

## References

- E. Dolstra, "The Purely Functional Software Deployment Model," Ph.D. thesis, Utrecht University, 2006. https://edolstra.github.io/pubs/phd-thesis.pdf: The theoretical foundation for content-addressed package management and the guarantees Nix does (and doesn't) provide.
- M. Fourné, D. Wermke, W. Enck, S. Fahl, and Y. Acar, "It's like flossing your teeth: On the importance and challenges of reproducible builds for software supply chain security," IEEE S&P 2023. https://doi.org/10.1109/SP46215.2023.10179320: Documents the learning curve barrier as the #1 obstacle to reproducible build adoption.
- C. Lamb and S. Zacchiroli, "Reproducible Builds: Increasing the Integrity of Software Supply Chains," IEEE Software, vol. 39, no. 2, pp. 62–70, 2022. https://doi.org/10.1109/MS.2021.3073045: Defines what "reproducible builds" means precisely (bit-for-bit identical outputs from identical inputs) vs the weaker guarantees most tools actually provide.
- NixOS Wiki, "Nix Pills," https://nixos.org/guides/nix-pills/: Practical guide to Nix expression language, relevant for understanding what the templates generate.
- Railway, "How Nixpacks Works," https://nixpacks.com/docs/how-it-works: Documents Railway's template-based approach which we validated independently.
