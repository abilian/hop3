# Aggregate Experience Report: Packaging 20 Applications for Hop3

**Status:** Draft (0.5)
**Last Updated:** 2026-04-09

## Overview

We packaged 20 open-source applications across four deployment methods
on Hop3: native (local builder), hand-crafted Nix, template-generated
Nix, and Docker. This report aggregates observations, patterns, and
lessons learned.

## Application Coverage

| App | Language | Database | Native | Nix | Nix-gen | Docker |
|-----|----------|----------|--------|-----|---------|--------|
| Adminer | PHP | None | Yes | Yes | Yes | — |
| BookStack | PHP | MySQL | Yes | Yes | Yes | Yes |
| Dolibarr | PHP | PostgreSQL | Yes | Yes | Yes | Yes |
| Easy!Appointments | PHP | MySQL | Yes | Yes | Yes | Yes |
| Focalboard | Go | PostgreSQL | Yes | Yes | Yes | Yes |
| Gitea | Go | PostgreSQL | Yes | Yes | Yes | Yes |
| Grafana | Go | None | Yes | Yes | Yes | Yes |
| Invoice Ninja | PHP | MySQL | Yes | Yes | Yes | Yes |
| Isso | Python | None | Yes | Yes | Yes | Yes |
| Jenkins | Java | None | Yes | Yes | Yes | Yes |
| Kanboard | PHP | MySQL | Yes | Yes | Yes | Yes |
| LimeSurvey | PHP | PostgreSQL | Yes | Yes | Yes | Yes |
| Matomo | PHP | MySQL | Yes | Yes | Yes | Yes |
| Mattermost | Go | PostgreSQL | Yes | Yes | Yes | Yes |
| Miniflux | Go | PostgreSQL | Yes | Yes | Yes | Yes |
| NextCloud | PHP | MySQL | Yes | Yes | Yes | Yes |
| Radicale | Python | None | Yes | Yes | Yes | Yes |
| Vikunja | Go | PostgreSQL | Yes | Yes | Yes | Yes |
| Wiki.js | Node.js | PostgreSQL | Yes | Yes | Yes | Yes |
| WordPress | PHP | MySQL | Yes | Yes | Yes | Yes |

**Languages:** PHP (10), Go (6), Python (2), Node.js (1), Java (1)
**Databases:** PostgreSQL (8), MySQL (7), None/SQLite (5)

## Patterns Observed

### What Works Well

1. **The `[nix]` template system eliminates Nix expertise.** App
   maintainers write TOML; Hop3 generates the Nix expression. The
   `php-app`, `python-venv`, `java-war`, and `nixpkgs-wrapper`
   templates build from source with full reproducibility.

2. **PHP apps follow a consistent pattern.** The `php-app` template
   handles Composer install, PHP extensions, writable directories, and
   config file generation. Once the template was debugged, all 10 PHP
   apps worked with it. These are true source builds.

3. **`hop3.toml` is expressive enough.** Every app could be configured
   declaratively. No app required escaping to a custom script (though
   `before-run` commands handle migrations and initialization).

4. **Apps already in nixpkgs are trivial.** The `nixpkgs-wrapper`
   template (used by Radicale) wraps existing nixpkgs packages with
   zero custom build logic — the ideal case for reproducibility.

### The Pre-Built Binary Problem

**7 of 20 apps currently rely on pre-built binaries** (Gitea, Miniflux,
Grafana, Mattermost, Vikunja, Focalboard, Wiki.js). This is a pragmatic
shortcut but conflicts with Hop3's stated goals:

1. **Not reproducible.** We download a binary from an upstream release
   page. We can verify the hash, but we cannot audit or rebuild it.
   The build is opaque — we trust the upstream CI.

2. **Not portable across architectures.** Pre-built binaries are
   typically x86_64-linux only. ARM (aarch64), RISC-V, and other
   architectures are not supported unless the upstream project also
   publishes those binaries. This is a blocker for edge/IoT deployment.

3. **Supply chain risk.** A compromised upstream release pipeline could
   distribute malicious binaries. With source builds, Nix's content-
   addressed store provides an independent verification path.

**Mitigation plan:** These apps should eventually be built from source
using Nix. For Go apps (6 of the 7), this means writing a `buildGoModule`
derivation. For Wiki.js (Node.js), a `buildNpmPackage` or equivalent.
This is significant Nix packaging work per app but is the right long-term
approach. In the meantime, the pre-built templates are upfront about their
limitations and should be documented as a "Tier 2" deployment — functional
but not fully reproducible.

**Affected apps and their source-build feasibility:**

| App | Pre-built template | Source build path | Difficulty |
|-----|-------------------|-------------------|------------|
| Gitea | prebuilt-binary | `buildGoModule` | Medium (large Go project) |
| Miniflux | prebuilt-binary | `buildGoModule` | Easy (small, no CGO) |
| Grafana | prebuilt-archive | `buildGoModule` + frontend | Hard (Go + Node + Webpack) |
| Mattermost | prebuilt-archive | `buildGoModule` + frontend | Hard (Go + React) |
| Focalboard | prebuilt-archive | `buildGoModule` + frontend | Hard (Go + Node) |
| Vikunja | prebuilt-archive | `buildGoModule` + frontend | Medium (Go + Vue) |
| Wiki.js | node-prebuilt | `buildNpmPackage` | Medium (Node.js + build) |

### Multi-Component Applications

Several apps in the set consist of multiple components that should
ideally run as separate processes:

| App | Components | Current Approach | Ideal Approach |
|-----|-----------|------------------|----------------|
| Mattermost | API server + web frontend | Single binary serves both | Acceptable (monolith by design) |
| NextCloud | PHP app + background cron | Single PHP process | Needs cron worker (`[run.workers]`) |
| Focalboard | Go API + Node frontend | Pre-built archive bundles both | Separate build, single binary OK |
| Invoice Ninja | PHP app + queue worker | Single PHP process | Needs queue worker (`[run.workers]`) |
| Mastodon* | Rails + Sidekiq + Streaming | Not yet supported | Needs multi-service ADR |

(*Mastodon is in Docker only, not in the 20-app set, but illustrates
the problem.)

**Current limitation:** Hop3's `[run.workers]` section supports
multiple named processes (web, worker, scheduler), and uWSGI can
manage them. But there is no declarative way to express that a
single app needs multiple containers or processes with different
runtime configs (different env vars, different ports, different
resource limits).

**Needed:** An ADR for multi-service application support. This would
define how `hop3.toml` expresses sidecar processes, shared storage
volumes, and inter-process networking. The `[[addons]]` mechanism
is a starting point (it already provisions databases as separate
services), but the pattern needs to generalise to arbitrary app
components.

### Recurring Technical Challenges

1. **PHP `__DIR__` resolves symlinks.** Nix store paths are symlinked
   into the working directory. PHP's `__DIR__` resolves the symlink,
   pointing to the read-only Nix store instead of the writable cwd.
   Fix: `cp -a` instead of symlinks (`needs-writable-dir` in nix-gen).

2. **Laravel APP_KEY must be exactly 32 bytes, base64-encoded.** Several
   PHP apps (BookStack, Invoice Ninja) failed silently with invalid keys.
   Fix: generate proper keys in `start.sh` or `[env]`.

3. **Database addons need wait loops in Docker.** Containers start before
   MySQL/PostgreSQL is ready. Every Docker app with a database addon
   needs a wait loop in `start.sh`, and migrations must be non-fatal
   (so the web server still starts for diagnostics).

4. **Config file generation before migrations.** LimeSurvey's install
   command needs `config.php` to know the database. The Nix wrapper
   must generate config files before running pre-exec commands.

5. **Environment variable mapping.** Hop3 injects `DATABASE_URL` but
   apps expect `DB_HOST`, `DB_PORT`, etc. The `[env.computed]` section
   in nix-gen handles this, but native and Docker configs must do it
   manually in `start.sh` or `wp-config.php`.

### Effort Per Deployment Method

| Method | Avg. Time | Nix Knowledge? | Reproducible? | Portable? |
|--------|-----------|----------------|---------------|-----------|
| Native | 15 min | No | No | Yes (source) |
| Docker | 30-60 min | No | Partially | Yes (multi-arch build) |
| Nix (source build) | 1-3 hours | Yes | Yes | Yes |
| Nix (template, source) | 15-30 min | No | Yes | Yes |
| Nix (template, pre-built) | 15 min | No | **No** | **No (x86_64 only)** |

### Nix Reproducibility Tiers

| Tier | Method | Rebuilds identically? | Auditable to source? | Multi-arch? |
|------|--------|---------------|------------|-------------|
| 1 | nixpkgs package | Yes | Yes | Yes |
| 2 | Source build against a committed lockfile | Yes | Yes | One arch per lockfile |
| 3 | Pre-built upstream artefact (fetchurl) | Yes | No | **No** |

Every tier builds in a sealed sandbox: the dependency set is vendored into a
fixed-output derivation from a committed lockfile, so the package manager runs
offline. What the tier ranks is provenance, not hermeticity.

Only 2 of the 31 nix-gen apps remain Tier 3 (jenkins, wiki-js — nixpkgs itself
packages both from the upstream artefact); 6 are Tier 1 and 23 Tier 2. Run
`hop3-tools nix tiers apps/real-apps-nix-gen` for the current split, and see
ADR 008 for the full assessment.

## Remaining Issues

- ~8 apps in `real-apps-nix-bad/` need further work (etherpad, hedgedoc,
  cryptpad, searxng, listmonk, matrix-synapse, sonarqube, xwiki)
- 7 apps rely on pre-built binaries (need source-build Nix derivations)
- Multi-component apps (NextCloud cron, Invoice Ninja queue) need
  `[run.workers]` configuration
- Multi-service apps (Mastodon-like) need an ADR
- Docker apps on SSH targets have MySQL connectivity issues
- No production deployments with real traffic yet

## Conclusion

Hop3 can package and deploy a diverse set of applications across
multiple languages and frameworks. The template-based Nix generation
(ADR 008) is a significant contribution: it provides Nix benefits
without requiring Nix expertise.

However, the current reliance on pre-built binaries for 7 of 20 apps
is a known compromise. These apps work but do not deliver on the
reproducibility and portability promises of Nix. Moving to source
builds is the priority for the next phase. Additionally, multi-
component applications need a better architectural pattern than the
current single-process-per-app model.
