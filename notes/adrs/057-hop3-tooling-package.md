# ADR 057: A `hop3-tooling` Package for Maintainer & Operator Tooling

- **Status**: Accepted
- **Type**: Architecture
- **Created**: 2026-07-18
- **Related-ADRs**: [049](./049-catalog-distribution.md) (catalog distribution), [043](./043-unified-testing-architecture.md) (testing architecture)

## Context

Hop3 accumulates tooling that no shipped package owns: automation a *maintainer* runs to develop, release, and operate the platform and its catalog. Consider the recurring jobs: checking a catalog copy against its tested source, promoting a tested recipe into the catalog, installing every catalog app on a clean box and verifying it works, bumping versions, probing a box's infrastructure, reading an app's generated credentials over SSH. None of these belongs to the platform, the client, the installer, or the test framework, yet all are recurring, reused work.

Today this tooling lives as ad-hoc files under the repo-root `scripts/` directory. That directory has grown into a broad mix (Python and shell, checks and generators and deploy helpers) with structural problems that compound as it grows:

- **No discovery.** A tool is useful only to a maintainer who already knows its filename exists. There is no `--help`, no index, no "what can I run here."
- **No contract.** Scripts vary in argument style, exit-code discipline, and output. Some are `set -e` shell, some argparse Python, some neither.
- **No tests.** A 500-line script like `verify-security-batch.py`, which SSHes to a box, drives `hop3 catalog install`, and asserts security properties, has no test and no way to acquire one in place.
- **No shared library.** Every script re-implements the same primitives: shell out to the `hop3` CLI, parse `hop3 app credentials`, SSH to a box, talk to a staged catalog. The logic drifts between copies.

The other workspace packages each have a narrow, defensible purpose that this tooling does not fit. `hop3-cli` is the end-user client; putting maintainer tooling there blurs "what a user runs." `hop3-server` is the platform. `hop3-installer` installs and deploys the platform. `hop3-testing` is the E2E **test framework**: a library plus the `hop3-test` runner. A version-bumper or a catalog promoter does other work entirely, and folding it in overloads that package's boundary. `hop3-tui` is the terminal UI; `hop3-rootd` is the privileged helper. Maintainer, release, and operator tooling has no home.

The catalog work ([ADR 049](./049-catalog-distribution.md), and the catalog-acceptance plan) is the concrete trigger: it needs at least three durable tools (a drift check, a promote step, and a whole-catalog acceptance harness) that must be discoverable, documented, tested, and share a common library. Adding them as three more files under `scripts/` deepens the smell instead of resolving it.

## Decision

Add a workspace package **`hop3-tooling`** (`packages/hop3-tooling`, `src/hop3_tooling`) exposing a **`hop3-tools`** CLI with subcommands. It is held to the same bar as any other package: `--help` on every command, an argument and exit-code contract, and a test suite. It is a **maintainer/operator** tool: never shipped to end users, never on the app-runtime path, and free to depend on developer conveniences the shipped packages avoid.

The package has two parts:

- **Commands.** The durable tools a maintainer runs. The catalog trio (`drift`, `promote`, `verify`) seeds it; existing durable one-offs graduate from `scripts/` as they earn it (version bump, config/infra checks, box diagnostics).
- **A shared internal library** for the primitives the commands reuse (invoking the `hop3` CLI, parsing `hop3 app credentials`, SSHing to a box, reading a staged catalog), so tools stop re-implementing them.

The boundary follows the **audience** rather than the mechanism:

- **Belongs in `hop3-tooling`:** work the people who maintain Hop3 and its catalog run, meaning repo, release, and ops automation.
- **Does not belong:** anything a normal user runs (→ `hop3-cli`); the E2E test framework itself (→ `hop3-testing`, which `hop3-tools` may *call*); installing or deploying the platform (→ `hop3-installer`).

`scripts/` is not abolished. A genuine throwaway or a few lines of glue can still live there. The rule targets the *durable, reused, wants-help-and-tests* class of tool: those graduate into `hop3-tooling`. The heuristic for "graduate it": a script that others are expected to run, that has grown non-trivial logic, or that needs to be trusted (it mutates a box, gates a release, or asserts a security property).

## Consequences

- Maintainer tooling gains discovery (`hop3-tools --help`), a UX contract, tests, and a shared library that removes duplication; these are the properties every shipped package already has.
- The catalog-acceptance work has a proper home, and the eventual decoupling of packaging from the platform (when the catalog becomes the packaging source of truth) has somewhere for its channel-management tooling to live.
- Cost: one more package to maintain, a one-time migration as scripts move in, and a recurring judgment call (script vs. tool), bounded by the audience heuristic above.
- The line stays clean only if the boundary is enforced in review: the temptation to drop a user-facing convenience into `hop3-tools`, or a test into it, is the failure mode to watch.

## Alternatives Considered

- **Keep everything in `scripts/`.** The status quo. Fails on discovery, help, tests, and shared code, and is already painful at the current spread of scripts. Rejected: the problems grow with the directory.
- **Fold the tooling into `hop3-testing`.** Overloads a package whose job is the test framework. A catalog promoter or a version-bumper does different work, and mixing them muddies the one boundary that package needs to keep sharp. Rejected. (`hop3-tools` calling `hop3-testing` is fine: a dependency, with no merge implied.)
- **Makefile targets.** A `Makefile` is a fine thin entry point *into* tools. Non-trivial logic, `--help`, and tests belong elsewhere. Kept as a complement.
- **A `hop3 dev …` subcommand tree in `hop3-cli`.** Puts maintainer tooling inside the user-facing client, bloating it and blurring "what users run." Rejected on the same audience boundary that motivates the package.

## Future Work

When packaging decouples from platform evolution and the catalog grows maturity channels (`unstable`/`testing`/`stable`), `hop3-tools` is the natural home for channel management (promoting an app across channels). Those commands are added once the channels exist. The package name is settled (`hop3-tooling`); the command name (`hop3-tools` vs. alternatives) can settle in review.
