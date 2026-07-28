# Architecture Decision Records (ADRs) for Hop3

Architectural Decision Records (or ADR) are documents that capture important architectural decisions made along with their context and consequences.

This process is inspired by [Python's PEP process](https://www.python.org/dev/peps/pep-0001/) and [Gel's RFC process](https://github.com/edgedb/rfcs).

## ADR Index

The authoritative, always-current index (every ADR with its type and status, plus a grouping by status) is generated from the ADR preambles and published at **[/developers/adrs/](https://hop3.cloud/developers/adrs/)**. It is not duplicated here; the published page is the single source of truth.

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
| **Deferred** | Parked for later consideration. The proposal has merit but the timing is not right. |
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
**Authors**: Name <email> (optional)
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
3. **Concrete examples** - Simplified, practical illustrations
4. **Configuration guidance** - How to use and configure
5. **Trade-offs documentation** - Alternatives considered and why rejected

ADRs should NOT include:

- Exhaustive feature lists for each implementation
- Step-by-step integration guides
- Implementation details for all variants
- Detailed testing procedures

Each ADR is an architectural specification: it records decisions with enough detail for implementation.

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
