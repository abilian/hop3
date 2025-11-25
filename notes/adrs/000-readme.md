# Architecture Decision Records (ADRs) for Hop3

Architectural Decision Records (or ADR) are documents that captures an important architectural decision made along with its context and consequences.

## ADR Index

| # | Title | Status |
|---|-------|--------|
| [001](./001-config-files.md) | Config Files for Hop3 | Draft |
| [002](./002-config-format.md) | Detailed `hop3.toml` Format | Draft |
| [003](./003-config-parsing-and-validation.md) | Config Parsing and Validation | Draft |
| [004](./004-development-tooling.md) | Development Tooling | Accepted |
| [005](./005-web-terminal.md) | Web Terminal for Application Management | Proposed |
| [006](./006-nix-integration.md) | Nix Integration with Hop3 | Draft |
| [007](./007-nix-builder.md) | Development of Nix Builders for Existing Packages | Draft |
| [008](./008-nix-builders-2.md) | Creation of Nix Alternatives to Native Builders | Draft |
| [009](./009-nix-runtime.md) | Using Nix as a Runtime Isolation Mechanism | Draft |
| [010](./010-security-and-resilience.md) | Security and Resilience Enhancements | Draft |
| [011](./011-encryption.md) | Data Encryption and Protection | Draft |
| [012](./012-mfa.md) | Multi-Factor Authentication (MFA) | Draft |
| [013](./013-supply-chain.md) | Software Supply Chain Security and SBOMs | Draft |
| [014](./014-authentication-bootstrap.md) | Authentication Bootstrap Process | Draft |
| [015](./015-documentation.md) | Documentation and Community Engagement | Draft |
| [016](./016-backups.md) | Backup Strategy | Draft |
| [017](./017-agent-based-architecture.md) | Distributed, Agent-Based Architecture | Draft |
| [018](./018-cli-architecture.md) | CLI-Server Communication | Accepted |
| [019](./019-cli-commands.md) | Basic Commands for the Hop3 Command-Line | Draft |
| [020](./020-pluggable-architecture.md) | Pluggable Architecture for Core Deployment Workflow | Accepted |
| [021](./021-proxy-plugin-system.md) | Proxy Plugin System for Reverse Proxy Configuration | Accepted |
| [022](./022-build-deploy-plugin-system.md) | Build and Deployment Plugin System | Accepted |
| [023](./023-runtime-stack-replacement.md) | Runtime Stack Replacement | Proposed |
| [024](./024-backup-restore-system.md) | Backup and Restore System | Accepted |
| [025](./025-cli-user-experience.md) | CLI User Experience Improvements | In Progress |
| [026](./026-dashboard-ui-test-classification.md) | Dashboard UI Test Classification | Accepted |
| [027](./027-config-system-refactoring.md) | Configuration System Refactoring for Testability | Accepted |
| [028](./028-pluggy-dishka-integration.md) | Pluggy + Dishka Integration for Plugin-Contributed Services | Accepted |

### Status Legend

- **Draft**: Initial proposal, not yet reviewed
- **Proposed**: Under active discussion
- **In Progress**: Partially implemented
- **Accepted**: Approved and implemented (or ready for implementation)
- **Deprecated**: No longer recommended
- **Superseded**: Replaced by a newer ADR

---

These ADRs should provide:

1. Decision-focused content - Why we made these choices
2. Complete interfaces - Anyone can implement a plugin
3. Concrete examples - Not abstract, but simplified
4. Configuration guidance - How to use and configure
5. Trade-offs documentation - Alternatives considered and why rejected

They dshouldn't include:

- Exhaustive feature lists for each implementation
- Step-by-step integration guides
- Implementation details for all variants
- Detailed testing procedures

The ADRs are architectural specifications with sufficient detail to understand responsibilities and implement functionalities, while remaining focused on decisions rather than becoming implementation manuals.

More info: https://lab.abilian.com/Tech/Software%20Engineering/Architectural%20Decision%20Records/

Here's a template:

______________________________________________________________________

# Title

Status: \[Draft | Proposed | Accepted | Deprecated | Superseded | ...\]

## Introduction

Describes the background and intention of the ADR.

## Summary

A short summary of the decision and its context.

## Status

What is the (current) status, such as proposed, accepted, rejected, deprecated, superseded, etc.?

## Context and Goals

### Context

What is the issue that we're seeing that is motivating this decision or change? Describes the as-is or current situation.

### Goals

Sets out key success criteria and/or metrics up-front.

## Tenets

The principles and values that are relevant to this decision.

## Decision

What is the change that we're proposing and/or doing?

## Detailed Design

Explain the design in enough detail for someone familiar with the ecosystem to understand and implement. This should include specifics and address corner-cases.

## Examples and Interactions

Illustrate the detailed design with examples. This section should clarify any confusion from previous sections and provide practical scenarios demonstrating the decision's application.

## Consequences

### Benefits

What are the positive outcomes expected from this decision?

### Drawbacks

What are the negative outcomes or challenges associated with this decision?

## Lessons Learned

What has happened in the past and what was learned? Relevant historical context that influenced this decision.

## Action Items

### Strategic Priorities

The detailed plan for achieving the success criteria/metrics described earlier. Steps that need to be taken to implement the decision.

## Alternatives

What other options did we consider or could we have taken instead? For each design decision made, discuss possible alternatives and compare them to the chosen solution.

## Prior Art

Summarize earlier discussions or prior attempts at addressing this problem. Discuss what was good or bad about these attempts and compare them to the current proposal. If applicable, include insights from other projects and communities.

## Unresolved Questions

What parts of the design are still TBD or unknowns?

## Future Work

What future work, if any, would be implied or impacted by this decision without being directly part of the current effort?

## Related

What other decisions are related to this one?

## References

What sources of information did you use to make this decision?

## Notes

Any additional notes or information that might be helpful.

## Appendix

Additional data, tables, documents, and context that support the decision.
