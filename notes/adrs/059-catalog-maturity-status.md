# ADR 059: Catalog Maturity Status

- **Status**: Accepted
- **Type**: Architecture
- **Created**: 2026-08-11
- **Related-ADRs**: [049](./049-catalog-distribution.md) (catalog distribution), [057](./057-hop3-tooling-package.md) (maintainer tooling), [043](./043-unified-testing-architecture.md) (testing architecture)

## Context

The catalog is flat. Every entry sits in one directory and every entry is offered on the same terms, so the artefact can say only one thing about an application: it is in the catalog. That is too coarse for the corpus Hop3 actually has.

The corpus is not uniform and is not meant to be. Packaging an application is a probe of the platform's edges ("Project Ethos"), so at any moment some recipes are verified end to end, some deploy but have never been signed into, some are known broken and kept *because* the breakage names a platform gap, and some are dropped for reasons upstream of us. A flat directory forces each of those into one of two states (published or absent), and absence is the same answer for "we retired this" and "we never finished this", which is how a deferred app becomes an app nobody remembers.

The gap has been anticipated twice. [ADR 057](./057-hop3-tooling-package.md) reserves channel management for `hop3-tools` "when the catalog grows maturity channels", and the catalog-acceptance plan expects new-app work to move into the catalog repo under maturity subdirectories. Both leave the vocabulary and the mechanism open. This ADR fixes them.

Two existing constraints bound the design. [ADR 049](./049-catalog-distribution.md) F1 makes the signed `index.json` authoritative for the published file set and pins the per-app artefact shape (`<app-id>/{…}`) as the boundary that does not change across distribution phases; a deployed node's loader is written against it. And the recurring defect in this area is the hand-maintained list that mirrors something the system already knows: a release script's package list, a Makefile's test paths, a `screenshots = []` field beside a populated directory. Each of them went stale silently.

## Decision

An application's recipe carries a **maturity status**, expressed as the directory it lives in.

### The statuses

Each is defined by the evidence that admits a recipe to it, so that promotion is a check rather than an opinion.

| Status | Admission | Published |
|---|---|---|
| `golden` | Installs from the published catalog and is verified through the application's own authentication with the credential Hop3 generated; a wrong password is refused. Carries `[admin]`, and `[probe]` where the application has accounts. Presentation metadata complete. | yes |
| `beta` | Deploys and serves *its own content*: readiness passes a `[healthcheck].contains` assertion, not a bare status line. The sign-in bar is unmet or does not apply. | yes, marked |
| `alpha` | Deploys. Verification is status-only or unproven. | no |
| `broken` | A recorded failure, with the reason written down. Retained deliberately: the failure is a platform backlog item. | no |
| `retired` | Withdrawn for a reason upstream of the platform: the project is archived, the licence is incompatible, or another variant supersedes it. | no |

`alpha`, `broken` and `retired` are *in the repository and out of the artefact*. Keeping them costs a directory and preserves the reason; dropping them destroys the only record of why an application was hard.

### The directory is the status

A recipe's status is the directory containing it, and nothing else records it. A `status = "beta"` field beside a `beta/` directory would be a second source of truth for one fact. The failure mode of that arrangement is well attested here: the two drift, the file wins in one code path and the field in another, and neither is wrong enough to fail.

The published `index.json` therefore carries a `status` field **derived at publish time**. That is not a duplicate: it is the value crossing a boundary, from a source tree a node cannot see into an artefact it can.

### The artefact stays flat

The hierarchy is a property of the source tree. The publish step walks it and emits the same flat `<app-id>/…` tree it always has, so ADR 049's F1 bijection and the loader on every deployed node are untouched. Publishing refuses a recipe whose status is not publishable: an operator who expects an application in the catalog and does not find it is owed the reason.

### One default build path per application

An application packaged several ways has one entry that carries the application's name and is the one an operator gets by default; the others are suffixed variants at their own status. The default is the **native** build path, because it is the tested source the sign-in verification was built around, and because a default has to be the path with the most evidence behind it.

This does not settle whether the catalog should eventually show one entry per application with the build path as a choice inside it. That changes the artefact's shape and is deferred to ADR 049.

## Consequences

- An operator can be shown what is proven, what is provisional, and what is known broken.
- A recipe's status cannot be asserted, only earned: each level names the check that admits it, and the checks already exist as the acceptance harness and the readiness gate.
- Deferred and withdrawn work keeps a home and a reason, which is what makes the packaging backlog readable as a platform backlog.
- `hop3-tools` acquires the promotion commands ADR 057 anticipated: moving a recipe between statuses is a tool's job, because it must re-run the admitting check.
- Cost: the publish path grows a tree walk and a refusal, and every tool that resolves an app by path learns the hierarchy. The artefact's consumers learn nothing, which is the point.
- A status can go backwards. A `golden` recipe whose next verification fails is demoted, and demotion is the normal outcome of a failing run.

## Alternatives Considered

- **A `status` field in `catalog.toml`, flat tree.** Cheaper to implement and needs no tool changes. Rejected: it makes status invisible in the layout, so the answer to "what state is the corpus in" requires a script, and it puts the fact in a file beside a directory that also implies it once the corpus outgrows one directory.
- **Three channels (`unstable`/`testing`/`stable`).** The shape ADR 057 and the acceptance plan sketched. Rejected as too coarse at the bottom: it gives one bucket to "not verified yet", "known broken" and "withdrawn", which are three different pieces of information and only one of them is a backlog item.
- **Publish everything and let the client filter.** Rejected: it ships recipes known not to work, and the installer would be the last line of defence against a catalogue entry that was never meant to be installable.
- **Delete what is not published.** The status quo for anything outside the catalog. Rejected on the ethos: a failed packaging attempt is evidence about the platform, and deleting it discards the finding while keeping the cost of having made it.
