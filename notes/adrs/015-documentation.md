# ADR 015: Documentation and Community Engagement

**Status**: Accepted
**Type**: Process
**Created**: 2024-07-17
**Updated**: 2026-04-14

## Revisions

- v0.2: Promoted from Draft to Accepted. The documentation component is shipped and operational. Aspirational community-engagement bullets that had no concrete commitment (forums, webinars) are demoted to "candidate future mechanisms" (2026-04-14).
- v0.1: Initial draft (2024-07-17)

## Implementation Status

**Shipped:**

- **Documentation site** built with MkDocs (Material theme) and published at [hop3.cloud](https://hop3.cloud/) and [abilian.github.io/hop3](https://abilian.github.io/hop3/).
- **User guide, installation guide, CLI reference, `hop3.toml` reference** under `docs/src/`.
- **Developer documentation**: plugin-development guide, architecture overview, testing guide, package-level `CLAUDE.md` files.
- **33 tutorials** across 9 programming languages under `docs/src/tutorials/`, many exercised as executable tests via the **Validoc** custom-markdown system.
- **CLI and testing cheat sheets** under `docs/src/reference/`.
- **Blog** for release announcements and conference talks.

**Active outbound engagement:**

- Conference presentations (OW2Con, OSXP) under NGI milestone M5.4.
- The NGI0 Commons Fund project page.
- Technical reports (TR-01) and the companion paper for systems venues.

**Candidate future mechanisms (not committed by this ADR):**

- Dedicated forum / discussion board. The GitHub Issues + PR workflow currently serves this role; a dedicated forum would only be established if community volume outgrows GitHub.
- Webinars / office hours. Low priority until 0.6 is shipped and there is a stable audience.
- Formal feedback surveys. Information currently comes from GitHub Issues and direct user contact.

## Decision

Hop3 ships a comprehensive documentation site as a first-class artefact. Community engagement happens primarily through GitHub (issues, pull requests, releases), conference presentations, and the NGI project channels. Dedicated forums and webinar programmes are candidates rather than commitments.

## Consequences

### Benefits

- Users and developers have the reference material they need to deploy, operate, and contribute to Hop3.
- Tutorial executability (via Validoc) catches documentation drift in CI.

### Drawbacks

- Maintaining the tutorials-as-tests path has a small but non-zero cost per release (drift between upstream-app behaviour and tutorial assertions).

## Non-goals

- Real-time interactive support (chat rooms, Discord, etc.). Out of scope for a self-hosted PaaS project of this size; operators who need that engage commercially.
- Translations. The documentation is English-only. A translation programme would be welcome but is not a commitment.
