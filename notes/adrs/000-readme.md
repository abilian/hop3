# Architecture Decision Records (ADRs) for Hop3

Architectural Decision Records (or ADR) are documents that capture important architectural decisions made along with their context and consequences.

This process is inspired by [Python's PEP process](https://www.python.org/dev/peps/pep-0001/) and [Gel's RFC process](https://github.com/edgedb/rfcs).

## ADR Index

| # | Title | Type | Status |
|---|-------|------|--------|
| [001](./001-config-files.md) | Config Files for Hop3 | Feature | Draft |
| [002](./002-config-format.md) | Detailed `hop3.toml` Format | Feature | Draft |
| [003](./003-config-parsing-and-validation.md) | Config Parsing and Validation | Feature | Draft |
| [004](./004-development-tooling.md) | Development Tooling | Process | Active |
| [005](./005-web-terminal.md) | Web Terminal for Application Management | Feature | Draft |
| [006](./006-nix-integration.md) | Nix Integration with Hop3 | Feature | Deferred |
| [007](./007-nix-builder.md) | Development of Nix Builders for Existing Packages | Feature | Deferred |
| [008](./008-nix-builders-2.md) | Creation of Nix Alternatives to Native Builders | Feature | Deferred |
| [009](./009-nix-runtime.md) | Using Nix as a Runtime Isolation Mechanism | Feature | Deferred |
| [010](./010-security-and-resilience.md) | Security and Resilience Enhancements | Feature | Draft |
| [011](./011-encryption.md) | Data Encryption and Protection | Feature | Draft |
| [012](./012-mfa.md) | Multi-Factor Authentication (MFA) | Feature | Draft |
| [013](./013-supply-chain.md) | Software Supply Chain Security and SBOMs | Feature | Draft |
| [014](./014-authentication-bootstrap.md) | Authentication Bootstrap Process | Feature | Final |
| [015](./015-documentation.md) | Documentation and Community Engagement | Process | Draft |
| [016](./016-backups.md) | Backup Strategy | Feature | Draft |
| [017](./017-agent-based-architecture.md) | Distributed, Agent-Based Architecture | Feature | Deferred |
| [018](./018-cli-architecture.md) | CLI-Server Communication | Feature | Accepted |
| [019](./019-cli-commands.md) | Basic Commands for the Hop3 Command-Line | Feature | Accepted |
| [020](./020-pluggable-architecture.md) | Pluggable Architecture for Core Deployment Workflow | Feature | Final |
| [021](./021-proxy-plugin-system.md) | Proxy Plugin System for Reverse Proxy Configuration | Feature | Final |
| [022](./022-build-deploy-plugin-system.md) | Build and Deployment Plugin System | Feature | Final |
| [023](./023-runtime-stack-replacement.md) | Runtime Stack Replacement | Feature | Draft |
| [024](./024-backup-restore-system.md) | Backup and Restore System | Feature | Final |
| [025](./025-cli-user-experience.md) | CLI User Experience Improvements | Feature | Final |
| [026](./026-dashboard-ui-test-classification.md) | Dashboard UI Test Classification | Guideline | Superseded (by 043) |
| [027](./027-config-system-refactoring.md) | Configuration System Refactoring for Testability | Feature | Final |
| [028](./028-pluggy-dishka-integration.md) | Pluggy + Dishka Integration for Plugin-Contributed Services | Feature | Final |
| [029](./029-reconciliation-health-checks.md) | Application Reconciliation and Health Check System | Feature | Draft |
| [030](./030-two-level-build-architecture.md) | Two-Level Build Architecture | Feature | Final |
| [031](./031-project-terminology.md) | Project Terminology | Guideline | Active |
| [032](./032-deployment-strategies-artifact-lifecycle.md) | Deployment Strategies & Artifact Lifecycle | Feature | Accepted |
| [033](./033-docker-integration.md) | Docker Integration Strategy | Feature | Final |
| [034](./034-streaming-deployment-logs.md) | Streaming Deployment Logs | Feature | Accepted |
| [035](./035-build-artifacts.md) | Build Artifacts as Runtime Contract | Architecture | Accepted |
| [036](./036-cli-ergonomics.md) | CLI Ergonomics and Command Surface | Design | Accepted (D7/D8 superseded by 042) |
| [037](./037-git-deployment-architecture.md) | Git-Based Deployment Architecture | Architecture | Implemented |
| [038](./038-multi-service-apps.md) | Multi-Service Application Support | Feature | Active (design) |
| [039](./039-python-deploy-strategies.md) | Python Deploy Strategies | Feature | Active (Phase 1 landed) |
| [040](./040-network-firewall-and-port-exposure.md) | Network Firewall and Per-App Port Exposure | Feature | Partially superseded (by 045) |
| [041](./041-privileged-operations-agent.md) | Privileged Operations Agent (hop3-rootd) | Architecture | Draft |
| [042](./042-cli-context-model.md) | CLI Context Model — Servers and Project Contexts | Feature (breaking) | Accepted |
| [043](./043-unified-testing-architecture.md) | Unified Testing Architecture | Process | Draft |
| [044](./044-nightly-test-lab.md) | Nightly Test Lab — Web App to Run & Report on Tests | Architecture | Draft (provisional) |
| [045](./045-fixed-port-registry.md) | Fixed Port Registry | Feature | Accepted |
| [046](./046-declarative-app-resources.md) | Declarative Application Resources — Secrets, Volumes, Dynamic Env, Limits | Feature | Accepted |
| [047](./047-cli-invocation-context.md) | CLI Invocation Context | Feature | Draft |
| [048](./048-waf-l7-lewaf.md) | Layer-7 Web Application Firewall (LeWAF) | Feature | Draft |

## ADRs by Type

### Features (36)

| # | Title | Status |
|---|-------|--------|
| [001](./001-config-files.md) | Config Files for Hop3 | Draft |
| [002](./002-config-format.md) | Detailed `hop3.toml` Format | Draft |
| [003](./003-config-parsing-and-validation.md) | Config Parsing and Validation | Draft |
| [005](./005-web-terminal.md) | Web Terminal for Application Management | Draft |
| [006](./006-nix-integration.md) | Nix Integration with Hop3 | Deferred |
| [007](./007-nix-builder.md) | Development of Nix Builders for Existing Packages | Deferred |
| [008](./008-nix-builders-2.md) | Creation of Nix Alternatives to Native Builders | Deferred |
| [009](./009-nix-runtime.md) | Using Nix as a Runtime Isolation Mechanism | Deferred |
| [010](./010-security-and-resilience.md) | Security and Resilience Enhancements | Draft |
| [011](./011-encryption.md) | Data Encryption and Protection | Draft |
| [012](./012-mfa.md) | Multi-Factor Authentication (MFA) | Draft |
| [013](./013-supply-chain.md) | Software Supply Chain Security and SBOMs | Draft |
| [014](./014-authentication-bootstrap.md) | Authentication Bootstrap Process | Final |
| [016](./016-backups.md) | Backup Strategy | Draft |
| [017](./017-agent-based-architecture.md) | Distributed, Agent-Based Architecture | Deferred |
| [018](./018-cli-architecture.md) | CLI-Server Communication | Accepted |
| [019](./019-cli-commands.md) | Basic Commands for the Hop3 Command-Line | Accepted |
| [020](./020-pluggable-architecture.md) | Pluggable Architecture for Core Deployment Workflow | Final |
| [021](./021-proxy-plugin-system.md) | Proxy Plugin System for Reverse Proxy Configuration | Final |
| [022](./022-build-deploy-plugin-system.md) | Build and Deployment Plugin System | Final |
| [023](./023-runtime-stack-replacement.md) | Runtime Stack Replacement | Draft |
| [024](./024-backup-restore-system.md) | Backup and Restore System | Final |
| [025](./025-cli-user-experience.md) | CLI User Experience Improvements | Final |
| [027](./027-config-system-refactoring.md) | Configuration System Refactoring for Testability | Final |
| [028](./028-pluggy-dishka-integration.md) | Pluggy + Dishka Integration for Plugin-Contributed Services | Final |
| [029](./029-reconciliation-health-checks.md) | Application Reconciliation and Health Check System | Draft |
| [030](./030-two-level-build-architecture.md) | Two-Level Build Architecture | Final |
| [032](./032-deployment-strategies-artifact-lifecycle.md) | Deployment Strategies & Artifact Lifecycle | Accepted |
| [033](./033-docker-integration.md) | Docker Integration Strategy | Final |
| [034](./034-streaming-deployment-logs.md) | Streaming Deployment Logs | Accepted |
| [038](./038-multi-service-apps.md) | Multi-Service Application Support | Active (design) |
| [039](./039-python-deploy-strategies.md) | Python Deploy Strategies | Active (Phase 1 landed) |
| [040](./040-network-firewall-and-port-exposure.md) | Network Firewall and Per-App Port Exposure | Draft |
| [042](./042-cli-context-model.md) | CLI Context Model — Servers and Project Contexts | Accepted |
| [045](./045-fixed-port-registry.md) | Fixed Port Registry | Draft |
| [046](./046-declarative-app-resources.md) | Declarative Application Resources | Accepted |

### Processes (3)

| # | Title | Status |
|---|-------|--------|
| [004](./004-development-tooling.md) | Development Tooling | Active |
| [015](./015-documentation.md) | Documentation and Community Engagement | Draft |
| [043](./043-unified-testing-architecture.md) | Unified Testing Architecture | Draft |

### Guidelines (2)

| # | Title | Status |
|---|-------|--------|
| [026](./026-dashboard-ui-test-classification.md) | Dashboard UI Test Classification | Superseded (by 043) |
| [031](./031-project-terminology.md) | Project Terminology | Active |

### Architecture (4)

| # | Title | Status |
|---|-------|--------|
| [035](./035-build-artifacts.md) | Build Artifacts as Runtime Contract | Accepted |
| [037](./037-git-deployment-architecture.md) | Git-Based Deployment Architecture | Implemented |
| [041](./041-privileged-operations-agent.md) | Privileged Operations Agent (hop3-rootd) | Draft |
| [044](./044-nightly-test-lab.md) | Nightly Test Lab | Draft (provisional) |

### Design (1)

| # | Title | Status |
|---|-------|--------|
| [036](./036-cli-ergonomics.md) | CLI Ergonomics and Command Surface | Accepted (D7/D8 superseded by 042) |

## ADRs by Status

### Final (11)

Fully implemented features.

| # | Title | Type |
|---|-------|------|
| [014](./014-authentication-bootstrap.md) | Authentication Bootstrap Process | Feature |
| [020](./020-pluggable-architecture.md) | Pluggable Architecture for Core Deployment Workflow | Feature |
| [021](./021-proxy-plugin-system.md) | Proxy Plugin System for Reverse Proxy Configuration | Feature |
| [022](./022-build-deploy-plugin-system.md) | Build and Deployment Plugin System | Feature |
| [024](./024-backup-restore-system.md) | Backup and Restore System | Feature |
| [025](./025-cli-user-experience.md) | CLI User Experience Improvements | Feature |
| [027](./027-config-system-refactoring.md) | Configuration System Refactoring for Testability | Feature |
| [028](./028-pluggy-dishka-integration.md) | Pluggy + Dishka Integration for Plugin-Contributed Services | Feature |
| [030](./030-two-level-build-architecture.md) | Two-Level Build Architecture | Feature |
| [033](./033-docker-integration.md) | Docker Integration Strategy | Feature |
| [037](./037-git-deployment-architecture.md) | Git-Based Deployment Architecture | Architecture |

### Active (4)

Processes, guidelines, and in-design features currently being worked on.

| # | Title | Type |
|---|-------|------|
| [004](./004-development-tooling.md) | Development Tooling | Process |
| [031](./031-project-terminology.md) | Project Terminology | Guideline |
| [038](./038-multi-service-apps.md) | Multi-Service Application Support | Feature |
| [039](./039-python-deploy-strategies.md) | Python Deploy Strategies | Feature |

### Accepted (8)

Approved and ready for implementation.

| # | Title | Type |
|---|-------|------|
| [018](./018-cli-architecture.md) | CLI-Server Communication | Feature |
| [019](./019-cli-commands.md) | Basic Commands for the Hop3 Command-Line | Feature |
| [032](./032-deployment-strategies-artifact-lifecycle.md) | Deployment Strategies & Artifact Lifecycle | Feature |
| [034](./034-streaming-deployment-logs.md) | Streaming Deployment Logs | Feature |
| [035](./035-build-artifacts.md) | Build Artifacts as Runtime Contract | Architecture |
| [036](./036-cli-ergonomics.md) | CLI Ergonomics and Command Surface | Design |
| [042](./042-cli-context-model.md) | CLI Context Model — Servers and Project Contexts | Feature |
| [046](./046-declarative-app-resources.md) | Declarative Application Resources | Feature |

### Draft (17)

Initial proposals, not yet reviewed.

| # | Title | Type |
|---|-------|------|
| [001](./001-config-files.md) | Config Files for Hop3 | Feature |
| [002](./002-config-format.md) | Detailed `hop3.toml` Format | Feature |
| [003](./003-config-parsing-and-validation.md) | Config Parsing and Validation | Feature |
| [005](./005-web-terminal.md) | Web Terminal for Application Management | Feature |
| [010](./010-security-and-resilience.md) | Security and Resilience Enhancements | Feature |
| [011](./011-encryption.md) | Data Encryption and Protection | Feature |
| [012](./012-mfa.md) | Multi-Factor Authentication (MFA) | Feature |
| [013](./013-supply-chain.md) | Software Supply Chain Security and SBOMs | Feature |
| [015](./015-documentation.md) | Documentation and Community Engagement | Process |
| [016](./016-backups.md) | Backup Strategy | Feature |
| [023](./023-runtime-stack-replacement.md) | Runtime Stack Replacement | Feature |
| [029](./029-reconciliation-health-checks.md) | Application Reconciliation and Health Check System | Feature |
| [040](./040-network-firewall-and-port-exposure.md) | Network Firewall and Per-App Port Exposure | Feature |
| [041](./041-privileged-operations-agent.md) | Privileged Operations Agent (hop3-rootd) | Architecture |
| [043](./043-unified-testing-architecture.md) | Unified Testing Architecture | Process |
| [044](./044-nightly-test-lab.md) | Nightly Test Lab | Architecture |
| [045](./045-fixed-port-registry.md) | Fixed Port Registry | Feature |

### Deferred (5)

Parked for later consideration.

| # | Title | Type |
|---|-------|------|
| [006](./006-nix-integration.md) | Nix Integration with Hop3 | Feature |
| [007](./007-nix-builder.md) | Development of Nix Builders for Existing Packages | Feature |
| [008](./008-nix-builders-2.md) | Creation of Nix Alternatives to Native Builders | Feature |
| [009](./009-nix-runtime.md) | Using Nix as a Runtime Isolation Mechanism | Feature |
| [017](./017-agent-based-architecture.md) | Distributed, Agent-Based Architecture | Feature |

### Superseded (1)

Replaced by a newer ADR.

| # | Title | Type | Superseded by |
|---|-------|------|---------------|
| [026](./026-dashboard-ui-test-classification.md) | Dashboard UI Test Classification | Guideline | [043](./043-unified-testing-architecture.md) |

---

## ADR Types

An ADR can describe one of three types:

| Type | Description | Final Status |
|------|-------------|--------------|
| **Feature** | New functionality or capability in Hop3 | Final |
| **Architecture** | Cross-cutting structural decisions (build, deploy, agents) | Implemented / Accepted |
| **Design** | Interface/UX and command-surface decisions | Accepted |
| **Process** | How we do things (workflows, development practices) | Active |
| **Guideline** | Conventions, best practices, standards | Active |

## ADR Statuses

### Lifecycle

```
                    ┌─────────────┐
                    │    Draft    │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ Accepted │ │ Rejected │ │ Deferred │
        └────┬─────┘ └──────────┘ └──────────┘
             │
      ┌──────┴──────┐
      ▼             ▼
┌──────────┐  ┌──────────┐
│  Final   │  │  Active  │
│(features)│  │(process/ │
└──────────┘  │guideline)│
              └────┬─────┘
                   ▼
             ┌──────────┐
             │ Inactive │
             └──────────┘
```

### Status Definitions

| Status | Description |
|--------|-------------|
| **Draft** | Initial proposal, not yet reviewed or discussed |
| **Accepted** | Approved after discussion, ready for implementation |
| **Rejected** | Explicitly decided against after discussion |
| **Deferred** | Parked for later consideration (not rejected, just not now) |
| **Final** | Feature is fully implemented (note which version) |
| **Active** | Process or guideline is in effect |
| **Inactive** | Process or guideline has been abandoned or replaced |
| **Superseded** | Replaced by a newer ADR (reference the replacement) |

---

## ADR Structure

### Required Preamble

Every ADR should start with a structured metadata block:

```markdown
# ADR NNN: Title

**Status**: Draft | Accepted | Rejected | Deferred | Final | Active | Inactive | Superseded
**Type**: Feature | Process | Guideline
**Created**: YYYY-MM-DD
**Authors**: Name <email>
**Implemented-In**: vX.Y.Z (for Final status)
**Superseded-By**: ADR NNN (if superseded)
**Related-ADRs**: NNN, NNN, NNN
```

### Required Sections

1. **Context** - What is the issue motivating this decision?
2. **Decision** - What change are we proposing?
3. **Consequences** - What are the positive and negative outcomes?

### Recommended Sections

- **Motivation** - Why is the existing situation inadequate?
- **Detailed Design** - Technical specification
- **Examples** - Practical scenarios demonstrating the decision
- **Alternatives Considered** - Other options and why they were rejected
- **Security Implications** - Security considerations
- **Backwards Compatibility** - Impact on existing functionality

---

## ADR Guidelines

ADRs should provide:

1. **Decision-focused content** - Why we made these choices
2. **Complete interfaces** - Anyone can implement against the design
3. **Concrete examples** - Not abstract, but simplified
4. **Configuration guidance** - How to use and configure
5. **Trade-offs documentation** - Alternatives considered and why rejected

ADRs should NOT include:

- Exhaustive feature lists for each implementation
- Step-by-step integration guides
- Implementation details for all variants
- Detailed testing procedures

The ADRs are architectural specifications with sufficient detail to understand responsibilities and implement functionalities, while remaining focused on decisions rather than becoming implementation manuals.

---

## Full Template

```markdown
# ADR NNN: Title

**Status**: Draft
**Type**: Feature
**Created**: YYYY-MM-DD
**Authors**: Name <email>
**Related-ADRs**: NNN, NNN

## Context

What is the issue that we're seeing that is motivating this decision or change?

- Current situation (as-is state)
- Pain points or limitations
- Stakeholders affected

## Motivation

Why is the existing situation inadequate to address the problem?

- Why now? What triggered this decision?
- What happens if we do nothing?

## Decision

What is the change that we're proposing and/or doing?

- High-level summary of the approach
- Key principles or tenets guiding this decision

## Detailed Design

Explain the design in enough detail for someone familiar with the ecosystem
to understand and implement.

- Architecture and components
- Interfaces and protocols
- Configuration options
- Corner cases and edge conditions

## Examples

Illustrate the detailed design with examples.

- Common use cases
- Configuration examples
- API usage examples

## Consequences

### Positive

- Benefits and improvements
- Problems solved

### Negative

- Trade-offs and limitations
- New complexity introduced
- Migration or compatibility concerns

## Security Implications

Security considerations for this decision.

- Authentication/authorization impact
- Data protection concerns
- Attack surface changes

## Backwards Compatibility

Impact on existing functionality.

- Breaking changes
- Migration path
- Deprecation timeline

## Alternatives Considered

What other options did we consider? Why were they rejected?

- Alternative A: Description, pros, cons, why rejected
- Alternative B: Description, pros, cons, why rejected

## Prior Art

How do other projects solve this problem?

- Similar solutions in other systems
- Lessons learned from previous attempts

## Unresolved Questions

What parts of the design are still TBD?

- Open issues to be resolved during implementation
- Questions needing further research

## Future Work

What future work is implied by this decision?

- Follow-up ADRs needed
- Features enabled by this decision
- Technical debt to address later

## References

- Links to relevant documentation, issues, or discussions
- External specifications or standards
```

### Minimal Template

For smaller decisions, a minimal template may suffice:

```markdown
# ADR NNN: Title

**Status**: Draft
**Type**: Feature
**Created**: YYYY-MM-DD
**Authors**: Name <email>

## Context

[Brief description of the problem]

## Decision

[What we decided to do]

## Consequences

[Key positive and negative outcomes]
```

---

## More Information

- [Architectural Decision Records (Lab Abilian)](https://lab.abilian.com/Tech/Software%20Engineering/Architectural%20Decision%20Records/)
- [Python PEP Process](https://www.python.org/dev/peps/pep-0001/)
- [Gel RFC Process](https://github.com/edgedb/rfcs)
