# ADR Index

Status terms: **Accepted** (approved, partially implemented) · **Final** (implemented, stable) · **Proposed** (under consideration) · **Draft** (being written) · **Deferred** (intentionally postponed) · **Superseded** (replaced by a newer ADR, linked) · **Active** (ongoing process or guideline).

| # | Title | Status |
|---|---|---|
| 001 | Config Files for Hop3 | Accepted |
| 002 | Detailed `hop3.toml` Format | Accepted |
| 003 | Config Parsing and Validation | Accepted |
| 004 | Development Tooling | Active |
| 005 | Web Terminal for Application Management | Deferred |
| 006 | Nix Integration with Hop3 | Accepted |
| 007 | Nix Builders for Existing Packages (Nixpkgs Mode) | Superseded by [008](008-nix-builders-2.md) |
| 008 | Template-Based Nix Expression Generation | Final |
| 009 | Nix Runtime Integration | Deferred |
| 010 | Security and Resilience (Umbrella) | Accepted |
| 011 | Data Encryption and Protection | Accepted |
| 012 | Multi-Factor Authentication (MFA) | Deferred |
| 013 | Software Supply Chain Security and SBOMs | Accepted |
| 014 | Authentication Bootstrap Process | Final |
| 015 | Documentation and Community Engagement | Active |
| 016 | Backup Strategy | Accepted |
| 017 | Distributed, Agent-Based Architecture | Draft |
| 018 | CLI-Server Communication | Final |
| 019 | Basic Commands for the Hop3 Command-Line | Accepted |
| 020 | Pluggable Architecture for Core Deployment Workflow | Final |
| 021 | Proxy Plugin System for Reverse Proxy Configuration | Final |
| 022 | Build and Deployment Plugin System | Final |
| 023 | Runtime Stack Replacement | Draft |
| 024 | Backup and Restore System | Final |
| 025 | CLI User Experience Improvements | Final |
| 026 | Dashboard UI Test Classification | Superseded by [043](043-unified-testing-architecture.md) |
| 027 | Configuration System Refactoring for Testability | Final |
| 028 | Pluggy + Dishka Integration for Plugin-Contributed Services | Final |
| 029 | Application Reconciliation and Health Check System | Accepted |
| 030 | Two-Level Build Architecture | Final |
| 031 | Project Terminology (Ubiquitous Language) | Active |
| 032 | Deployment Strategies and Artifact Lifecycle | Accepted |
| 033 | Docker Integration Strategy | Final |
| 034 | Streaming Deployment Logs | Final |
| 035 | Build Artifacts as Runtime Contract | Final |
| 036 | CLI Ergonomics and Command Surface | Accepted |
| 037 | Git-Based Deployment Architecture | Final |
| 038 | Multi-Service Application Support | Accepted |
| 039 | Python Deploy Strategies: Clarify and Make Explicit | Accepted |
| 040 | Network Firewall and Per-App Port Exposure | Superseded by [045](045-fixed-port-registry.md) |
| 041 | Privileged Operations Agent (hop3-rootd) | Accepted |
| 042 | CLI Context Model: Context = Deploy Environment | Accepted |
| 043 | Unified Testing Architecture | Accepted |
| 044 | Nightly Test Lab: Run and Report on the Full Test Suite | Accepted |
| 045 | Fixed-Port Registry: Exclusive Host Ports for Non-HTTP Apps | Accepted |
| 046 | Declarative Application Resources | Accepted |
| 047 | CLI Invocation Context | Draft |
| 048 | Server Configuration and Secret Storage | Accepted |
| 049 | Catalog Distribution: Fetching App Specs from a Central Source | Accepted |
| 050 | Layer-7 Web Application Firewall (LeWAF) | Accepted |
| 051 | Config Injection | Draft |
| 052 | CLI Argument Consistency | Accepted |
| 053 | Nix Closure Lifetime | Accepted |
| 054 | Email Transport and Notifications | Accepted |
| 055 | App-Runtime UID Separation | Proposed |
| 056 | App Admin Credentials: Bootstrap, Storage, and Retrieval | Accepted |
| 057 | A `hop3-tooling` Package for Maintainer & Operator Tooling | Accepted |
| 058 | Build Reproducibility Model | Accepted |

## Summaries

### 001 — Config Files for Hop3 — `Accepted`
Adopts `hop3.toml` as the primary configuration file format for Hop3 applications, supplemented by support for Procfiles and other scripts. This gives each app a single, version-controlled declaration of its build, deploy, addon, and runtime requirements.

### 002 — Detailed `hop3.toml` Format — `Accepted`
Specifies the complete `hop3.toml` schema: metadata, build configuration (builder selection, toolchain hints), runtime settings, addon declarations, health checks, backup policy, environment variables, and domain/proxy configuration. This is the canonical reference for what an app's config file can express.

### 003 — Config Parsing and Validation — `Accepted`
Commits to using an existing syntax (TOML) rather than creating a new DSL for `hop3.toml`. Establishes that validation happens at parse time with clear error messages, that unknown keys are rejected, and that the parsed config becomes a frozen dataclass passed through the deployment pipeline.

### 004 — Development Tooling — `Active`
Documents the core development tooling: `uv` for package management, Ruff for linting/formatting, pytest for testing, and task automation via Makefile. This is a living ADR that evolves as the toolchain does.

### 005 — Web Terminal for Application Management — `Deferred`
Proposes an in-browser terminal for app management (log streaming, interactive shells, one-off commands). Deferred because the foundational RPC and streaming infrastructure needed to be built first; the streaming deployment logs system (ADR 034) is the first deliverable.

### 006 — Nix Integration with Hop3 — `Accepted`
Establishes Nix as a first-class build and packaging system for Hop3. Nix-built applications produce a self-contained closure with all dependencies; Hop3 consumes the closure through a defined contract (see ADR 035). This was the umbrella decision that spawned ADRs 007–009, 030, 053, and 058.

### 007 — Nix Builders for Existing Packages (Nixpkgs Mode) — `Superseded by 008`
Originally proposed a dedicated "nixpkgs-mode builder" for wrapping existing nixpkgs packages. Superseded by ADR 008, which folds that function into the template-based generation system as the `nixpkgs-wrapper` template — a thin `hop3.nix` wrapping `pkgs.<app>` with the runtime contract.

### 008 — Template-Based Nix Expression Generation — `Final`
Defines the template system that generates `hop3.nix` expressions from `[nix].template` declarations in `hop3.toml`. Supports multiple template types (prebuilt-binary, prebuilt-archive, python-venv, php-app, java-war, nixpkgs-wrapper) with a shared spec model. This is the recommended path for most Nix-packaged apps.

### 009 — Nix Runtime Integration — `Deferred`
Envisions running Nix-built applications under Hop3's own runtime (uWSGI emperor + nginx) rather than as standalone Nix processes. Deferred because the `RuntimeConfig` contract (ADR 035) makes the nix→runtime handoff sufficiently clean that a deeper integration isn't needed yet.

### 010 — Security and Resilience (Umbrella) — `Accepted`
Landing page for Hop3's security design. Enumerates sub-concerns (encryption, MFA, supply chain, auth bootstrap, privilege separation, WAF, rate limiting) and delegates concrete design to child ADRs. Rejects the "broad-scope checklist" anti-pattern — each mechanism is decided in its own ADR.

### 011 — Data Encryption and Protection — `Accepted`
Establishes that Hop3 must protect data at rest and in transit through robust encryption. Covers encrypted credential storage in the database (per-value AES-256-GCM with a server key), TLS termination for all HTTP traffic, and secure key storage under `/etc/hop3/`.

### 012 — Multi-Factor Authentication (MFA) — `Deferred`
Proposes adding TOTP-based MFA to the authentication flow. Deferred because the current threat model's primary path (CLI → SSH tunnel → RPC) already provides an SSH-backed second factor for operators, and the web dashboard is not yet the primary administration surface.

### 013 — Software Supply Chain Security and SBOMs — `Accepted`
Commits to generating Software Bill of Materials (SBOMs) for every deployed application and for the Hop3 platform itself. Covers CycloneDX format, integration into the build pipeline, and the `hop3 app sbom` command for retrieval.

### 014 — Authentication Bootstrap Process — `Final`
Defines the initial admin-account bootstrap flow: the installer generates a random password displayed once at install time, the operator logs in and can create additional users. This avoids shipping a default credential while keeping the first-login experience simple.

### 015 — Documentation and Community Engagement — `Active`
Commits Hop3 to first-class reference documentation and community channels. Covers the docs site (`docs/src/`), tutorial structure, contribution guidelines, and the public roadmap. A living ADR that shapes how the project communicates.

### 016 — Backup Strategy — `Accepted`
Defines the long-term backup strategy: file-based core (configuration, app data, databases), automated scheduling, remote storage, encryption, and incremental backups. ADR 024 implements the file-based core; the remaining features are follow-ons.

### 017 — Distributed, Agent-Based Architecture — `Draft`
Long-term vision for evolving Hop3 from a single-server PaaS to a distributed agent-based platform. Each server runs a hop3-agent reporting to a central controller; the reconciliation loop (ADR 029) is the first architectural step. Draft status reflects its dependency on foundational work not yet complete.

### 018 — CLI-Server Communication — `Final`
Establishes the JSON-RPC protocol for CLI-to-server communication, with the server doing the heavy lifting (logic, formatting) and the CLI acting as a thin presenter. The CLI sends `{"method": "cli", "params": {"cli_args": [...]}}` and renders the structured response.

### 019 — Basic Commands for the Hop3 Command-Line — `Accepted`
Defines the kernel command set: `app`, `addon`, `backup`, `domain`, `env`, `user`, `auth`, `system`, `network`, `catalog`, `cert`, `waf`, `plugin`, `ps`, `port`, `git`, `nix`, `version`, `help`. The dispatch mechanism uses a `@register` decorator with longest-prefix matching.

### 020 — Pluggable Architecture for Core Deployment Workflow — `Final`
Refactors Hop3's deployment from a monolithic, hardcoded process into three swappable plugin stages: builder → deployer → proxy. Each stage has a well-defined protocol; plugins register via Pluggy hooks. This is the architectural backbone of the entire platform.

### 021 — Proxy Plugin System for Reverse Proxy Configuration — `Final`
Implements the proxy stage of the pluggable architecture. There is one reverse proxy per server; the plugin system lets operators choose Nginx, Caddy, or Traefik. Each proxy plugin implements `get_proxy_strategy()` and handles virtual hosting, TLS, and upstream configuration.

### 022 — Build and Deployment Plugin System — `Final`
Implements the build and deploy stages of the pluggable architecture. Builders and deployers are discovered via Pluggy; the application's source code determines which builder/deployer pair is used, with no hardcoded conditionals in core code.

### 023 — Runtime Stack Replacement — `Draft`
Proposes replacing the current runtime stack (uWSGI + nginx + supervisor) with a modernized architecture that maintains functionality while reducing complexity. Goals include hot reconfiguration, elimination of unmaintained dependencies, and cleaner separation of concerns. Still draft — the current stack works and the migration cost is high.

### 024 — Backup and Restore System — `Final`
Implements the file-based core of the backup system from ADR 016. Covers per-app backup creation, listing, restoration, and destruction; backs up app source, environment, database dumps, and uploaded files to a configurable backup directory.

### 025 — CLI User Experience Improvements — `Final`
Defines CLI syntax conventions (space form `hop3 backup destroy` over colon form `hop3 backup:delete`), help-text standards, error-recovery hints, and streaming output protocol. References ADRs 034 and 036 for detailed specifications.

### 026 — Dashboard UI Test Classification — `Superseded by 043`
Originally classified dashboard UI tests into tiers. Superseded by ADR 043's unified testing architecture, which subsumes UI test classification into the broader three-tier (unit/integration/e2e) model.

### 027 — Configuration System Refactoring for Testability — `Final`
Refactors the configuration system to support dependency injection: config values flow through Dishka providers rather than being imported as module-level constants. Makes the entire system testable by allowing test code to inject configuration without monkeypatching.

### 028 — Pluggy + Dishka Integration for Plugin-Contributed Services — `Final`
Bridges Pluggy (plugin discovery) and Dishka (dependency injection) so that plugins can contribute services to the DI container. Introduces the `get_di_providers` hook — plugins return Dishka provider instances, and the container aggregates them at startup. Unblocks addon, proxy, and deployer plugins from needing global registries.

### 029 — Application Reconciliation and Health Check System — `Accepted`
Introduces a background reconciliation loop that periodically checks application state against the declared configuration and attempts automatic recovery. The first step toward the self-healing platform vision of ADR 017. Includes active health checks (`_app_serves_http`) that distinguish a bound socket from a genuinely serving application.

### 030 — Two-Level Build Architecture — `Final`
Separates the build system into two levels: a high-level `Builder` (language detection, build orchestration) and low-level `Toolchain` plugins (Python, Node, Go, Rust, etc.). The builder delegates to the toolchain, which produces a `BuildArtifact`. This decouples build strategy from language implementation.

### 031 — Project Terminology (Ubiquitous Language) — `Active`
Defines the canonical vocabulary for the project following Domain-Driven Design principles: Application, Addon, Builder, Deployer, Proxy, Catalog, Context, Artifact, Toolchain. Ensures that code, documentation, and CLI messages use consistent terms.

### 032 — Deployment Strategies and Artifact Lifecycle — `Accepted`
Moves from a simple "stop-then-deploy" model to explicit deployment strategies (rolling, blue-green, canary) and defines the artifact lifecycle (build → store → deploy → archive → garbage-collect). The `BuildArtifact` type becomes the runtime contract between stages.

### 033 — Docker Integration Strategy — `Final`
Makes Docker a first-class deployment target alongside native uWSGI deployment. A `DockerComposeDeployer` plugin handles docker-compose lifecycle (up, down, stop, status); Docker images are built by the Docker builder and deployed with port allocation, proxy wiring, and resource limits.

### 034 — Streaming Deployment Logs — `Final`
Introduces real-time log streaming for deployments via Server-Sent Events (SSE). The `hop3 deploy` command returns immediately; build and deployment progress streams to the CLI, dashboard, and WebSocket/SSE endpoints. The streaming protocol is shared across all output channels.

### 035 — Build Artifacts as Runtime Contract — `Final`
Defines `BuildArtifact` as the typed contract between build and deploy stages. A builder produces an artifact (kind + location + metadata); the deployer consumes it without inspecting the build internals. The `RuntimeConfig` contract in `$out/hop3/runtime.json` bridges Nix and native builds.

### 036 — CLI Ergonomics and Command Surface — `Accepted`
Specifies the CLI's command surface and interaction patterns. Introduces the context model (server + app binding), `--app` flag resolution, env var passthrough, and streaming output conventions. Partially superseded by ADR 042's context model revision.

### 037 — Git-Based Deployment Architecture — `Final`
Implements Heroku-style `git push` deployments alongside the explicit `hop3 deploy` path. A post-receive hook on the Hop3 server triggers build and deploy; the `git-hook` command reads the push data from stdin and orchestrates the full pipeline. The two paths share the same deployer infrastructure.

### 038 — Multi-Service Application Support — `Accepted`
Extends the deployment model to support applications with multiple independent services (e.g., web + worker + scheduler) that share the same source tree, environment, and addons. Services are declared via `[run.workers]` in `hop3.toml` and managed as a group by the deployer.

### 039 — Python Deploy Strategies: Clarify and Make Explicit — `Accepted`
Documents the decision tree used by the Python language toolchain to select an installation strategy at build time. Covers pip, poetry, uv, pipenv, and requirements.txt detection, with clear precedence rules and actionable error messages when detection is ambiguous.

### 040 — Network Firewall and Per-App Port Exposure — `Superseded by 045`
Originally defined per-app port exposure through `[[ports]]` declarations in `hop3.toml`. Superseded by ADR 045, which provides a more complete fixed-port registry with exclusive allocation, port lifecycle, and integration with the L7 WAF (ADR 050).

### 041 — Privileged Operations Agent (hop3-rootd) — `Accepted`
Introduces `hop3-rootd`, a privileged Unix-socket daemon that executes kernel-boundary operations (nft firewall rules, nginx reload, cgroup management, mounts, DKIM key generation) on behalf of the unprivileged `hop3-server`. Authentication is via `SO_PEERCRED` (peer UID must be `hop3` or `root`). This is the cornerstone of Hop3's privilege-separation model.

### 042 — CLI Context Model: Context = Deploy Environment — `Accepted`
Defines the CLI context model through three revisions. Final version: a *context* is a deploy environment declared in the project's `hop3.toml` as `[contexts.<name>]` (server + app + domains + env); `config.toml` holds global named servers for project-less commands; `--context <name>` resolves project-first, then global. Supersedes ADR 036's context model.

### 043 — Unified Testing Architecture — `Accepted`
Unifies Hop3's fragmented testing landscape (pytest layers, hop3-test runner, demos harness, tutorials, validoc, nox, Makefile/CI) into a single model. Defines three tiers (fast/check/nightly), three pytest layers (unit/integration/e2e) stamped by directory, and a hop3-testing framework for full app-deploy-verify cycles. See also ADR 044 for the nightly test lab.

### 044 — Nightly Test Lab — `Accepted`
Implements the nightly tier from ADR 043: a system that provisions real servers (Hetzner Cloud), deploys the full app catalog, demos, and tutorials against them, and produces an HTML report. Uses the `hop3-test` runner's `--images` sweep to test across OS images. Runs overnight as a scheduled job.

### 045 — Fixed-Port Registry: Exclusive Host Ports for Non-HTTP Apps — `Accepted`
HTTP/HTTPS is the only protocol Hop3 multiplexes via virtual hosting. Non-HTTP protocols (SMTP, XMPP, RTMP, Matrix federation, IMAP, TURN) must bind exclusive host ports. This ADR defines the `[[ports]]` declaration in `hop3.toml`, the fixed-port registry in the database, allocation/deallocation lifecycle, and integration with the L7 WAF (ADR 050). Supersedes ADR 040.

### 046 — Declarative Application Resources — `Accepted`
Establishes a declarative model for application resources in `hop3.toml`: generated secrets (`[env]` with `$(generate ...)` ), persistent volumes (`[[volumes]]` ), resource limits (`[limits]` with memory/CPU/process caps), resource-aware backup policy, and proxied secondary ports. The platform realizes the declarations idempotently, failing loud when it cannot.

### 047 — CLI Invocation Context — `Draft`
Specifies how the CLI transmits the resolved app and environment with every RPC call, so that server-side commands receive a fully materialized context without re-resolution. Draft status reflects ongoing iteration on the exact payload shape and backward-compatibility with existing commands.

### 048 — Server Configuration and Secret Storage — `Accepted`
Consolidates server configuration and secret storage into a consistent model. Secrets (signing keys, database passwords, API tokens) live under `/etc/hop3/` with strict file permissions; the server reads them at startup. Configuration uses a layered model: environment variables override `/etc/hop3/config.toml` defaults. Replaces the previous ad-hoc per-secret approach.

### 049 — Catalog Distribution: Fetching App Specs from a Central Source — `Accepted`
The app Catalog is a curated collection of installable app specs distributed from a central source controlled by the Hop3 project. The `hop3 catalog refresh` command fetches the latest catalog index; installation uses the catalog as a lookup table mapping `app_id` to a deployable spec. Moves away from the "directory alongside source" model.

### 050 — Layer-7 Web Application Firewall (LeWAF) — `Accepted`
Implements a minimal L7 WAF integrated with the Hop3 proxy layer. Bans are per-IP with configurable duration; the WAF reads nginx access logs, applies rate-limit rules, and pushes nftables bans via hop3-rootd. Starts with two concrete use cases (login brute-force protection, path-based abuse) and defers speculative features until customer feedback justifies them.

### 051 — Config Injection — `Draft`
Extends the addon wiring model (where addon connection details become environment variables) to handle config-file-based and database-configured apps. Apps declare injection targets in `hop3.toml`; the platform renders config files from templates with injected addon credentials and DB connection strings.

### 052 — CLI Argument Consistency — `Accepted`
Establishes a single flag lexicon across all Hop3 command-line tools (`hop3`, `hop3-install`, `hop3-deploy-server`, `hop3-test`, `hop3-tui`). Common flags (`--app`, `--context`, `--server`, `--verbose`) have identical names, semantics, and short forms across all entry points. Reduces the cognitive load of working with five CLIs built with three different argument parsers.

### 053 — Nix Closure Lifetime — `Accepted`
Nix-packaged apps exec hardcoded store paths (`${pkg}/bin/<name>`). A garbage collection that deletes the running app's closure kills the process mid-request. This ADR defines the GC-root strategy: the deployer registers an indirect GC root (`.nix-result`) in the app directory before launching the app, re-roots the previous closure during rebuild to keep it alive throughout, and the root is deleted on app destroy.

### 054 — Email Transport and Notifications — `Accepted`
Treats email as a backing service, symmetrical to databases and caches: provisioned as an addon, attached to apps, consumed through injected connection variables (`SMTP_HOST`, `SMTP_PORT`, etc.). Supports a swappable backend (SMTP relay, local postfix via rootd) and provides a notification framework for password resets, invitations, and system alerts.

### 055 — App-Runtime UID Separation — `Proposed`
Proposes running each deployed application under its own system UID rather than all apps sharing the `hop3` user. This would prevent a compromised app from reading another app's source, environment, or addon credentials. Currently at the proposal stage; the implementation requires rootd-mediated UID allocation and per-app filesystem ownership.

### 056 — App Admin Credentials: Bootstrap, Storage, and Retrieval — `Accepted`
Installing an app is more than starting its process — most real apps gate everything behind a login. This ADR defines the admin-credential bootstrap flow: the platform generates a random admin password during install, stores it encrypted in the credential store, and exposes it via `hop3 app credentials <name>` and the dashboard. Makes the install experience complete rather than leaving the operator at a login wall.

### 057 — A `hop3-tooling` Package for Maintainer & Operator Tooling — `Accepted`
Creates a `hop3-tooling` package for automation scripts that don't belong to the platform, client, installer, or test framework: catalog copy verification, tested-recipe promotion, bulk app installation, version bumping, infrastructure probing, and credential reading over SSH. Consolidates recurring maintainer work into a shipped, tested, and documented package.

### 058 — Build Reproducibility Model — `Accepted`
Defines the precise claim of reproducibility for Hop3 builds: a third party with the same inputs (source, `hop3.toml`, and build environment) can rebuild a deployment and verify it produces bit-identical artifacts. Constrains every build path (three Nix tiers, native toolchain, Docker) and defines what "same inputs" means for each. The property is stated precisely enough to be falsified — which is the point.
