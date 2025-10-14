# Architecture Decision Records (ADRs) for Hop3

Architectural Decision Records (or ADR) are documents that captures an important architectural decision made along with its context and consequences.

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
