# ADR 015: Documentation and Community Engagement

- **Status**: Active
- **Type**: Process
- **Created**: 2024-07-17

## Context

Hop3 needs reference material that lets users deploy and operate applications, and lets developers understand and extend the platform. It also needs channels through which the community can report problems, contribute changes, and follow the project's direction. Without a first-class documentation artefact and clear engagement channels, the platform is hard to adopt and hard to contribute to.

## Decision

Hop3 ships a comprehensive documentation site as a first-class artefact. Community engagement happens primarily through GitHub (issues, pull requests, releases), conference presentations, and the NGI project channels. Dedicated forums and webinar programmes are candidates rather than commitments.

## Detailed Design

### Documentation site

The documentation is built with MkDocs (Material theme) and published at [hop3.cloud](https://hop3.cloud/) and [abilian.github.io/hop3](https://abilian.github.io/hop3/). It contains:

- **User-facing reference** under `docs/src/`: the user guide, installation guide, CLI reference, and `hop3.toml` reference.
- **Developer documentation**: the plugin-development guide, an architecture overview, the testing guide, and package-level `CLAUDE.md` files.
- **Tutorials** across multiple programming languages under `docs/src/tutorials/`. Tutorials are exercised as executable tests via the **Validoc** custom-markdown system, so documentation drift is caught in CI.
- **CLI and testing cheat sheets** under `docs/src/reference/`.
- **Blog** for release announcements and conference talks.

### Outbound engagement

Active outbound engagement happens through conference presentations (OW2Con, OSXP), the NGI0 Commons Fund project page, and technical reports and the companion paper for systems venues.

### Candidate future mechanisms

The following mechanisms are not committed by this ADR; they would only be established if circumstances warrant:

- **Dedicated forum / discussion board.** The GitHub Issues and pull-request workflow serves this role. A dedicated forum is established only if community volume outgrows GitHub.
- **Webinars / office hours.** Deferred until there is a stable audience.
- **Formal feedback surveys.** Feedback comes from GitHub Issues and direct user contact.

## Consequences

### Benefits

- Users and developers have the reference material they need to deploy, operate, and contribute to Hop3.
- Tutorial executability (via Validoc) catches documentation drift in CI.

### Drawbacks

- Maintaining the tutorials-as-tests path has a small but non-zero cost per release: drift between upstream-app behaviour and tutorial assertions must be reconciled.

## Non-goals

- Real-time interactive support (chat rooms, Discord, etc.). Out of scope for a self-hosted PaaS project of this size; operators who need that engage commercially.
- Translations. The documentation is English-only. A translation programme would be welcome but is not a commitment.
