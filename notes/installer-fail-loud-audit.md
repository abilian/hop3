# Installer and deployer: the warning-and-continue audit

October 2026. Scope: `hop3-install server`, `hop3-install cli` and `hop3-deploy-server` (the `hop3-installer` package).

## How it started

Two bugs in `hop3-deploy-server`'s "Configuring local CLI" step survived for weeks: a readiness race (the step ran before the server listened) and a login check that sent a stale stored token instead of the new one. Each printed a ⚠ line, and the deploy still ended with "Deployment complete!". The race failed first and hid the second bug. In the same runs, the .NET SDK 9 install failed on every Ubuntu 24.04 server (no feed carries it there) and was reported the same way. Every e2e run log carried five to nine such lines, and every reader scrolled past them.

The project's rule is that an error is never silent: a step that cannot do what was asked aborts with an actionable message. A warning followed by "complete" breaks that rule while looking like it follows it, because the problem was printed. So every warning site was audited.

## What the audit found

105 sites: 99 `print_warning` calls in the installers, 6 `log(..., "warning")` calls in the deployer.

| Class | Sites | Meaning |
|---|---|---|
| Should abort | ~74 | A requested or required step failed, and the install continues to a broken server that reports success |
| Already abort, wrong label | ~10 | The run fails, but the failure is printed as a warning |
| Information | ~8 | An expected state worded as a problem ("already installed", "systemd absent under supervisor") |
| Legitimately non-fatal | ~11 | Continuing is safe, and the reason can be stated |
| Policy questions | ~4 | Decided below |

The worst cases, each of which ends in a successful-looking install:

- A failed write of `hop3-server.toml` leaves the server without database credentials or domain. Verification then skips its database checks, because they are keyed on the file's existence.
- A failed `createuser` or `createdb` for PostgreSQL is reported in a detail line and followed by a success line.
- The nginx include for app vhosts can be skipped, so every app the server configures is ignored by nginx.
- Services found stopped at verification produce a warning and "Installation complete!".
- On the Docker target, `--with docker` is passed by default and the Docker daemon can never start there. Docker-built apps then fail at build time, and the databases bind without the Docker bridge.
- The legacy passwordless sudo fragment can fail to be removed while the install reports the migration to `hop3-rootd` as done.

## Root patterns

The sites are symptoms of a few patterns, and the fixes follow the patterns.

1. **A blanket downgrade.** `_run_service_setup_steps` catches the failure of the systemd, SSL, nginx, PostgreSQL and MySQL steps and warns, truncating the error output to 100 characters; `main()` does the same for the config write and ACME. Several warnings further down are consequences of this one.
2. **`systemctl` without asking whether systemd runs.** Under supervisor (the Docker target) this raises, and the raise is caught as a "Systemd setup issue". The other modules already check `has_systemd()`.
3. **A deployer default that becomes a feature request.** The Docker target defaults to `with_features = ["docker"]`, so the installer is asked for something the target cannot provide, and then cannot fail loudly about it without failing every Docker-target install.
4. **Return `None` and let someone else notice.** The database setup returns `None` on failure; a generic check later turns it into an abort, with the cause and its output printed far above. Some return values are ignored outright, and some `except CommandError` blocks wrap code that runs with `check=False` and can never raise.
5. **Verification that warns.** Stopped services and a missing certificate do not change the verification's result.
6. **A warning that predicts an abort.** "hop3-rootd source not found ... install will abort": the install mutates the box first and fails later.

## Plan

In batches, each committed and checked by a clean Docker deploy whose log is free of warnings it does not justify:

1. The service setup steps, the systemd-absent path and verification (patterns 1, 2, 5).
2. The Docker target's default and the Docker daemon, bridge and group steps (pattern 3).
3. PostgreSQL, MySQL and Redis (pattern 4).
4. Toolchains and the remaining server steps: npm and the pinned pnpm, Go, Rust's symlinks, email, ACME, S3, the nginx include and restart, group memberships, the sudoers removal, an unknown distribution.
5. The CLI installer.
6. The deployer: a requested Let's Encrypt certificate that falls back to self-signed, the admin user, a missing `hop3-rootd` package.
7. **The gate.** `hop3-test` fails a server deploy whose log carries a ⚠ line that is not on an allowlist, each entry with the reason it is safe to continue. This is what keeps the result: a review does not reliably catch a new warning-and-continue, and a failed run does.

A failure that aborts uses the template the feature packages already follow: print the tail of the command's stdout and stderr, then raise.

## Decisions

- **Toolchains nobody asked for** (Leiningen, Elixir) are best-effort by default and abort when requested with `--with`, as Rust already is.
- **SSH key setup** for `git push` is part of the install contract and aborts.
- **The `hop3` PostgreSQL role's password** is generated, set and then read by nothing: the step is deleted.
- **Docker on the Docker target** is no longer requested by default. Running Docker-built apps there would need a privileged container, which is a separate decision.

## Legitimately non-fatal

These stay warnings and form the gate's first allowlist:

- `nft` missing or failing (making it fatal once caused an outage; apps that need a fixed port fail at deploy);
- no cgroup v2 hierarchy (a host property; only apps with `[limits]` are affected, at deploy);
- the `hop3-rootd --init-state` fallback (it writes identical content);
- the build-info file (read only by `hop3 system info`);
- a missing `hop3-cli` source on the server (used only by on-server tutorial tests);
- Rust without `--with rust`;
- the CLI installer's PATH hint for an unrecognised shell.

## See also

- [`lessons-learned/development-process.md`](./lessons-learned/development-process.md): the lessons from the two CLI-step bugs.
- [`lessons-learned/multi-distribution-support.md`](./lessons-learned/multi-distribution-support.md): "a `--with` feature that fails aborts the install", the rule this audit generalises.
