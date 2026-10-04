# Lessons Learned: Development Process

**Updated**: 2026-09-08, consolidated from internal notes (December 2025 to April 2026) and the September 2026 review of the shell branch.

These habits cost time when skipped. Each entry names the incident that made it a rule.

## Search the codebase before building

The MySQL addon was planned as new work; it existed, with tests, under `plugins/mysql/`. `find` and `grep` for the class or the feature name take a minute and have saved days more than once.

## Inherited code is a claim

The uWSGI configuration carried a `project` directive inherited from piku. uWSGI ignores directives it does not know, so the directive did nothing for months, until `strict = true` made it an error. Review inherited code with validation on, and treat "it was always there" as a reason to look. Enable strict modes wherever a tool offers them.

## Debug logging is structured, and removed

Investigation logging gets a prefix and a flag so it can be found and turned off. Left in, it becomes noise that hides the next signal.

## Two small Python and ORM rules that each broke something

- **Every foreign key states its `ondelete`.** Deleting an app failed on `FOREIGN KEY constraint failed` because `EnvVar` and `Backup` rows had no `CASCADE`. Decide per relation whether children cascade, null out, or block.
- **ORM models stay thin; a method that needs business logic imports it lazily.** `App.deploy()` calling `do_deploy()` was a circular import, because the deployer imports `App`. Type hints go under `if TYPE_CHECKING:`; the runtime import goes inside the method.
- **Warning filters run at import time.** A `filterwarnings` placed after `import paramiko` silences nothing; put it before the import that emits.

## A systemic fix is shipped everywhere it applies, or it is not shipped

A tier-aware build timeout was "done" for the Docker builder while the Nix builder kept its hardcoded ceiling. The two had copy-pasted the same logic, and only one was updated. The same happened with the exception unwrapper that turned `RepositoryError` into a diagnosis. It was installed on the RPC path, and missing on the `git push` hook path that real users hit, so they saw "There was an error during data processing" while every test was green.

Before claiming a cross-cutting fix, grep for the concern (the constant, the function, the config key) and find every sibling. If two implementations share logic by convention, move it to a shared module so the next change cannot forget one. The fix is real when the grep finds one helper.

## A signature change is workspace-wide

Packages import each other's internals: hop3-tui uses hop3-cli's `SshTunnel` and its config; hop3-testing is a pytest plugin every package loads. Renaming `SshTunnel(key=…)` to `settings=…` was grepped only inside hop3-cli, so the TUI kept the old keyword and `make test-e2e` failed in the TUI suite. The same rename then broke the TUI's own integration test, whose stub of the tunnel still took `key=`, and left a CLI test checking a keyword the client no longer sent. Grep the whole tree for callers and for test stubs of the class, and run the check tier (`make test`), because the fast tier does not run the integration suites.

## Review your own duplication before committing

The September shell branch, reviewed against the code-quality checklist, had three builders of the same `ssh` prefix and three readings of the same settings. All were written in one session. Each was reasonable alone. Consolidation was cheap the same day and would have been a migration a month later. A quick review pass for the five anti-patterns (defensive noise, soft invariants, band-aids, invented abstractions, duplication) belongs before the commit.

## A check verifies exactly what it was given

`hop3 login --token` verified the new token by building a throwaway config around it and calling the server. But a config's own token ranks below the per-server credential store and `HOP3_API_TOKEN`, so the check sent whatever was already stored for that server. After every `hop3-deploy-server --docker --clean`, that was the previous container's token, signed with a key that no longer existed: the new token was refused with "Authentication required" without ever leaving the machine. A test covered the verification, but it ran with an empty store, so it could not fail on this.

A probe is built from its inputs, never from the general resolution chain, which answers with whatever wins it. Its test seeds decoys (a stored token, the environment variable) so it can fail.

## Adding a source to a precedence chain re-reads every lower source's callers

The credential store was added above the config's token (ADR 042 r2), and the one caller that built a config expecting its token to win was not re-read. It is the second time this shape has bitten: a recipe's `[run].start` overrode the php-fpm worker, so the new runtime shipped with no users and seven defects. When a source joins a precedence order, grep every place that constructs one of the sources it outranks.

## A warning that the deploy carries on past is a failure nobody reads

Two bugs in `hop3-deploy-server`'s CLI step, a readiness race and the token above, printed ⚠ lines and the deploy still ended with "Deployment complete!". The race failed first and hid the token bug. The .NET SDK 9 install, which no feed carries for Ubuntu 24.04, failed on every such server the same way. Every e2e run log carried five to nine such lines, for weeks, and every reader scrolled past them. A warning-and-continue is not caught by review: it has to fail something mechanically.

## Related

- [`deployment-diagnostics.md`](./deployment-diagnostics.md): the `Diagnosis` record that the entry-point rule protects.
- [`e2e-test-infrastructure.md`](./e2e-test-infrastructure.md): why a skipped test is a hole.
