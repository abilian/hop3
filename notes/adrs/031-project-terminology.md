# ADR 031: Project Terminology (Ubiquitous Language)

- **Status**: Active
- **Type**: Guideline
- **Created**: 2025-11-28
- **Related-ADRs**: [020](./020-pluggable-architecture.md), [022](./022-build-deploy-plugin-system.md), [030](./030-two-level-build-architecture.md), [036](./036-cli-ergonomics.md)

## Context

A clear, consistent vocabulary is essential for any software project. Following Domain-Driven Design principles, we define an **ubiquitous language** - a shared vocabulary between domain experts (DevOps engineers, developers, SREs) and the codebase.

This ADR serves as the definitive reference for terminology used throughout the Hop3 project. It consolidates decisions from multiple discussions and ADRs into a single authoritative source.

### Problems Addressed

1. **Terminology Conflicts**: Words like "service" have multiple meanings in different contexts (microservices vs. backing services)
2. **Abstraction Level Confusion**: Mixing orchestration concepts with language-specific tooling
3. **Legacy Naming**: Old naming patterns that no longer reflect the architecture
4. **Documentation Drift**: Inconsistent terminology across code, docs, and discussions

---

## Decision

We adopt the following terminology as the standard vocabulary for Hop3.

---

## Core Concepts

### Applications and Blueprints

The Blueprint vocabulary is the candidate naming for the packaged-app installation use case; the open questions it raises are listed under [Unresolved Questions](#unresolved-questions).

Hop3 supports two distinct use cases that both result in deployed applications:

| Use Case | Analogy | User | Workflow |
|----------|---------|------|----------|
| **Custom App Deployment** | Heroku, Fly.io | Developer | Push code → Build → Deploy |
| **Packaged App Installation** | App Store, YunoHost | Operator | Browse catalog → Install → Configure |

#### Core Terms

| Term | Definition | Notes |
|------|------------|-------|
| **App** | A deployed application instance | Universal term for any deployed instance |
| **Blueprint** | A packaged application definition in the catalog | *Candidate term* |
| **Custom App** | An App deployed from user's own code | No associated blueprint |
| **Blueprint App** | An App created from a Blueprint | Has `blueprint_name` reference |
| **Catalog** | Collection of available Blueprints (free, self-host) | Canonical term; "marketplace" reserved for the commercial product (see below) |

#### App Origin

An App can originate from:
1. **Custom code** - Developer pushes their own code (Heroku-style)
2. **Blueprint** - Operator installs from catalog (App Store-style)

The origin is metadata. All apps share the same management commands regardless of origin.

#### Catalog vs. Marketplace

**Catalog** is the canonical term for the free, self-host collection of installable Blueprints (browse → install → configure on your own server). It carries no commercial connotation: there are no prices, sellers, or payments.

**Marketplace** is reserved for the future *commercial* product: a hosted, branded "SaaS marketplace" with premium/paid apps. Do not call the free feature a "marketplace": keeping the two distinct stops a product feature being conflated with a business model.

Spelling: use the US **catalog**, not the British "catalogue", to match the codebase's prevailing US-English convention (`color`, `license`, `behavior`).

The web UI carries this name throughout: the `server/catalog/` package, the `CatalogController`/`CatalogService`/`CatalogApp` classes, and the `/dashboard/catalog` route. See [Migration Notes](#from-previous-terminology).

#### Additional App Terms

| Term | Definition | Notes |
|------|------------|-------|
| **App State** | The lifecycle state: RUNNING, STOPPED, PAUSED | Stored in `app.run_state` |
| **Process Type** | A named entry point in Procfile (e.g., `web`, `worker`) | Heroku-compatible |
| **Worker** | A running instance of a process type | Can scale horizontally |

#### Data Model

```python
class App:
    """A deployed application instance."""
    name: str                           # Instance name: "acme-blog"

    # Origin tracking (optional)
    blueprint_name: str | None = None   # e.g., "wordpress" or None for custom
    blueprint_version: str | None = None

    @property
    def is_custom(self) -> bool:
        return self.blueprint_name is None

    @property
    def is_from_blueprint(self) -> bool:
        return self.blueprint_name is not None


class Blueprint:
    """A packaged application available in the catalog."""
    name: str           # e.g., "wordpress", "nextcloud"
    version: str        # e.g., "6.4.1"
    description: str
    # ... catalog metadata, deployment instructions
```

#### CLI Examples

**Custom App (Developer workflow):**
```bash
git push hop3 main              # Deploy from git
hop3 apps list
# NAME        ORIGIN    STATE
# my-api      custom    running
```

**Blueprint App (Operator workflow):**
```bash
hop3 blueprints list            # Browse catalog
hop3 blueprints install wordpress --name company-blog
hop3 apps list
# NAME          ORIGIN              STATE
# company-blog  wordpress@6.4.1     running
# my-api        custom              running
```

### Deployment Pipeline

The deployment process follows a three-stage pipeline: **Build → Deploy → Proxy**.

| Term | Definition | Protocol | Hook | Level |
|------|------------|----------|------|-------|
| **Builder** | Orchestrates HOW to build (environment, isolation) | `Builder` | `get_builders()` | Level 1 |
| **LanguageToolchain** | Executes WHAT to build (language-specific logic) | `LanguageToolchain` | `get_language_toolchains()` | Level 2 |
| **Deployer** | Runs build artifacts and manages application lifecycle | `Deployer` | `get_deployers()` | - |
| **Proxy** | Configures reverse proxy for HTTP routing | `Proxy` | `get_proxies()` | - |

#### Two-Level Build Architecture (from [ADR 030](./030-two-level-build-architecture.md))

**Level 1: Builder (Orchestration)**
- Defines HOW to build: locally, in Docker, with Nix
- Examples: `LocalBuilder`, `DockerBuilder`, `NixBuilder`
- Selection: Configuration-driven (`hop3.toml`) or auto-detection

**Level 2: LanguageToolchain (Language-Specific)**
- Defines WHAT tools to use for a specific language
- Examples: `PythonToolchain`, `NodeToolchain`, `JavaToolchain`
- Selection: Auto-detection based on project files (requirements.txt, package.json)
- Only used by `LocalBuilder`; other builders encapsulate their own logic

### Data Flow Objects

| Term | Definition | Usage |
|------|------------|-------|
| **BuildContext** | Context for build operations (before deployment) | Passed to Builders and LanguageToolchains |
| **DeploymentContext** | Context for deployment operations (after build) | Passed to Deployers |
| **BuildArtifact** | Describes what was built (kind, location, metadata) | Returned by Builders, passed to Deployers |
| **DeploymentInfo** | Connection details for the proxy (protocol, address, port) | Returned by Deployers |

### Platform Resources

| Term | Definition | Protocol | Hook | Heroku Equivalent |
|------|------------|----------|------|-------------------|
| **Addon** | Platform-managed backing service (database, cache, etc.) | `Addon` | `get_addons()` | Add-on |
| **OS** | Operating system configuration and package management | `OS` | `get_os_implementations()` | Stack |

#### Addon vs. Service Distinction

This is a critical distinction to avoid confusion:

| Term | Meaning | Example |
|------|---------|---------|
| **Addon** | Platform-managed resource provided by Hop3 | PostgreSQL, Redis, S3 |
| **Service** | User's application component in their domain | Celery worker, API microservice |

**Rationale**: Using "Addon" (Heroku convention) avoids collision with microservices terminology. Platform-managed resources are called "addons"; the user's application components remain "services" in their domain.

### Plugin System

| Term | Definition | Notes |
|------|------------|-------|
| **Plugin** | A module that extends Hop3 functionality | Uses pluggy framework |
| **Hook** | An extension point that plugins can implement | e.g., `get_builders()` |
| **Hook Implementation** | A plugin's implementation of a hook | Decorated with `@hop3_hook_impl` |
| **Protocol** | A Python interface (PEP 544) defining required methods | Structural typing |

---

## Complete Terminology Reference

### A

| Term | Definition | Context |
|------|------------|---------|
| **Addon** | Platform-managed backing service | Replaces "service" for platform resources |
| **addon_name** | Specific instance name for an addon | e.g., "my-postgres-db" |
| **App** | A deployed application instance | Universal term regardless of origin |
| **Application** | See App | |
| **Artifact** | See BuildArtifact | |

### B

| Term | Definition | Context |
|------|------------|---------|
| **Backing Service** | 12-factor term for attached resources | We use "Addon" |
| **Blueprint** | Packaged application definition in the catalog | *Candidate term*: App Store use case |
| **Blueprint App** | An App created from a Blueprint | Has `blueprint_name` reference |
| **Build** | Process of preparing source code for deployment | |
| **BuildArtifact** | Descriptor of built output | kind, location, metadata |
| **BuildContext** | Build-time context (app_name, source_path, config) | Separate from DeploymentContext |
| **Builder** | Level 1: Build orchestration (HOW to build) | LocalBuilder, DockerBuilder, NixBuilder |
| **Buildpack** | Heroku-style build artifact type | kind="buildpack" |

### C

| Term | Definition | Context |
|------|------------|---------|
| **Caddy** | A reverse proxy implementation | Proxy plugin |
| **Catalog** | Collection of available Blueprints (free, self-host) | Canonical; "marketplace" reserved for the commercial product (see M) |
| **Container** | Docker/OCI container | Deployment target |
| **Context** | Information passed to strategies | BuildContext, DeploymentContext |
| **Custom App** | An App deployed from user's own code | No associated blueprint |

### D

| Term | Definition | Context |
|------|------------|---------|
| **Deploy** | Process of running a built application | Second stage |
| **Deployer** | Manages deployment and application lifecycle | UWSGIDeployer, DockerDeployer |
| **DeploymentContext** | Deployment-time context | Includes App ORM object |
| **DeploymentInfo** | Connection details for proxy | protocol, address, port |

### E-H

| Term | Definition | Context |
|------|------------|---------|
| **ENV** | Environment file containing app configuration | Located at `APP_PATH/ENV` |
| **Env** | Environment configuration object | Wrapper around env vars |
| **Hook** | Plugin extension point | Hookspec definition |
| **Hop3** | The PaaS platform | |

### L

| Term | Definition | Context |
|------|------------|---------|
| **LanguageToolchain** | Level 2: Language-specific build tools | PythonToolchain, NodeToolchain |
| **LocalBuilder** | Builder that uses native toolchains on host | Default builder |

### M

| Term | Definition | Context |
|------|------------|---------|
| **Marketplace** | Reserved for the future commercial/hosted ("SaaS marketplace") product | NOT the free catalog: see [Catalog vs. Marketplace](#catalog-vs-marketplace) |

### N-O

| Term | Definition | Context |
|------|------------|---------|
| **Nginx** | Default reverse proxy | Proxy plugin |
| **Nix** | Declarative package manager | Future builder option |
| **NixBuilder** | Builder using Nix for reproducible builds | Planned |
| **OS** | Operating system plugin | Debian, Ubuntu, RHEL, etc. |

### P

| Term | Definition | Context |
|------|------------|---------|
| **Plugin** | Extensible module using pluggy | Core architecture |
| **Procfile** | Declares process types | Heroku-compatible |
| **Process Type** | Named entry in Procfile | web, worker, etc. |
| **Protocol** | Python structural typing interface | PEP 544 |
| **Proxy** | Reverse proxy configuration | Nginx, Caddy, Traefik |

### S

| Term | Definition | Context |
|------|------------|---------|
| **Service** | User's application component | NOT platform resources |
| **Static** | Static file serving | StaticDeployer |
| **Strategy** | Implementation of a protocol | Legacy term; prefer specific names |

### T

| Term | Definition | Context |
|------|------------|---------|
| **Toolchain** | See LanguageToolchain | Language-specific build tools |
| **Traefik** | A reverse proxy implementation | Proxy plugin |

### U-W

| Term | Definition | Context |
|------|------------|---------|
| **uWSGI** | Application server for Python | Default deployer |
| **Worker** | Running instance of a process type | Can scale |

---

## Naming Conventions

### Protocol Names

- Use noun form: `Builder`, `Deployer`, `Addon`, `Proxy`, `OS`
- Capitalize as proper nouns when referring to the protocol

### Class Names

| Pattern | Example | Notes |
|---------|---------|-------|
| `{Language}Toolchain` | `PythonToolchain`, `NodeToolchain` | Level 2 build |
| `{Method}Builder` | `LocalBuilder`, `DockerBuilder` | Level 1 build |
| `{Type}Deployer` | `UWSGIDeployer`, `DockerDeployer` | Deployment |
| `{Proxy}Proxy` | `NginxProxy`, `CaddyProxy` | Note: Avoid redundant suffix in some cases |
| `{Type}Addon` | `PostgreSQLAddon`, `RedisAddon` | Platform addons |
| `{Distribution}OS` | `DebianOS`, `UbuntuOS` | OS plugins |

### Hook Names

| Pattern | Example | Returns |
|---------|---------|---------|
| `get_{plural}()` | `get_builders()` | List of classes |
| `get_{descriptive}_implementations()` | `get_os_implementations()` | When plural is ambiguous |
| `get_language_toolchains()` | | Explicit Level 2 |

### Field Names

| Field | Protocol | Notes |
|-------|----------|-------|
| `name` | All | Type identifier (e.g., "python", "uwsgi") |
| `addon_name` | Addon | Instance name |
| `context` | Builder, Deployer | BuildContext or DeploymentContext |
| `artifact` | Deployer | BuildArtifact from build stage |

---

## Codebase Alignment

Two identifiers carry forward names that predate this vocabulary and remain candidates for alignment:

| Item | Notes |
|------|-------|
| Directory `builders/` → `toolchains/` | Cosmetic; the code is already correct |
| `Addon.name` → `Addon.addon_type` | Ties into the addon-vs-service distinction |

---

## Unresolved Questions

The Blueprint vocabulary names a use case whose terminology is not yet final. The following questions remain open.

### Blueprint Terminology

1. **Is "Blueprint" the right term?**
   - Alternatives considered: Package, Template, Recipe, Offering
   - "Blueprint" is preferred for its clear metaphor (blueprint → building)

2. **Should blueprints be versioned independently?**
   - Can users upgrade a deployed app to a newer blueprint version?
   - How do we handle breaking changes in blueprints?

3. **Blueprint sources?**
   - Official catalog only?
   - Community-contributed blueprints?
   - Self-hosted blueprint repositories?

4. **Relationship to Nix**
   - If pursuing Nix integration (ADRs 007-009), should Blueprints map to Nix flakes?
   - Or keep them as a higher-level abstraction?

5. **CLI command naming**
   - `hop3 blueprints install` vs `hop3 install` vs `hop3 apps create --from-blueprint`
   - Should blueprint commands be under `apps` or separate?

---

## Migration Notes

### From Previous Terminology

| Old Term | New Term | Reason |
|----------|----------|--------|
| `BuildStrategy` | `Builder` | Clearer domain language |
| `DeploymentStrategy` | `Deployer` | Clearer domain language |
| `ServiceStrategy` | `Addon` | Avoid microservices conflict |
| `PlatformSetupStrategy` | `OS` | Clearer, specific |
| `ProxyStrategy` | `Proxy` | Simpler |
| `service_name` (in Addon) | `addon_name` | Consistent with Addon terminology |
| `Marketplace*` / `server/marketplace/` / `/dashboard/marketplace` | `Catalog*` / `server/catalog/` / `/dashboard/catalog` | "Catalog" is the canonical name for the free feature; this is a UI-only rename, with no DB or RPC change. The `Catalog`-named classes in `hop3-testing`/`hop3-testlab` are a separate package and concept (test-app catalog): no collision. |

### Deprecated Terms (Do Not Use)

- ~~Service~~ for platform resources (use **Addon**)
- ~~Platform~~ for OS (use **OS**)
- ~~Runtime~~ for deployers (use **Deployer** - covers systemd, static, etc.)
- ~~Strategy~~ as suffix (use specific protocol names)

---

## Rationale

### Why Heroku-Inspired Naming?

1. **Industry Recognition**: Heroku terminology is widely understood in the PaaS space
2. **Clear Semantics**: Terms like "addon" have specific, unambiguous meanings
3. **User Familiarity**: Developers migrating from Heroku find familiar concepts
4. **Avoids Conflicts**: "Addon" doesn't conflict with microservices terminology

### Why Two-Level Build Architecture?

1. **Separation of Concerns**: Build orchestration vs. language-specific logic
2. **Multi-Language Support**: One builder can use multiple toolchains
3. **Extensibility**: Easy to add new builders or toolchains independently
4. **Type Safety**: Clear protocol boundaries enable proper type checking

See [ADR 030](./030-two-level-build-architecture.md) for detailed rationale.

### Why "Deployer" Not "Runtime"?

"Runtime" implies execution environment, but deployers also:
- Manage static file serving (no runtime)
- Configure systemd services (process manager)
- Handle lifecycle management (start, stop, scale)

"Deployer" accurately describes deployment + lifecycle management for all implementations.

### Why "OS" Not "Platform"?

"Platform" is ambiguous:
- Could mean the PaaS platform (Hop3)
- Could mean infrastructure (AWS, bare metal)
- Could mean OS (Debian, Ubuntu)

"OS" is clear and specific.

---

## Success Criteria

This terminology is successful when:

1. New developers understand concepts without explanation
2. Documentation uses consistent vocabulary
3. Code identifiers match domain language
4. No terminology conflicts in discussions
5. Plugin authors know which protocol to implement

---

## References

- [Domain-Driven Design (Eric Evans)](https://www.domainlanguage.com/ddd/) - Ubiquitous Language concept
- [Heroku Platform](https://devcenter.heroku.com/) - Addon terminology
- [12-Factor Apps](https://12factor.net/) - Backing services concept
- [ADR 020: Pluggable Architecture](./020-pluggable-architecture.md)
- [ADR 022: Build/Deploy Plugin System](./022-build-deploy-plugin-system.md)
- [ADR 030: Two-Level Build Architecture](./030-two-level-build-architecture.md)
