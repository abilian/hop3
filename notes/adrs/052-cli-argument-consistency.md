# ADR 052: CLI Argument Consistency — one flag lexicon across every Hop3 command-line tool

- **Status**: Accepted
- **Type**: Guideline
- **Created**: 2026-06-30
- **Related-ADRs**: 042 (cli-context-model), 047 (cli-invocation-context), 043 (unified-testing-architecture), 044 (nightly-test-lab)

## Context

Hop3 ships five command-line entry points, built with three unrelated argument parsers:

| Tool | Purpose | Parser |
|------|---------|--------|
| `hop3` / `hop` | day-to-day client, talks to a running server | hand-rolled argv scanner (`hop3_cli/commands/flags.py`) |
| `hop3-test` | deploy Hop3 + run the app/demo/tutorial catalog | Click groups |
| `hop3-deploy` | dev tool: push Hop3 to a server/Docker over SSH | argparse (6 groups) |
| `hop3-install` | production installer (`cli` / `server` / `bundle`) | argparse, hand-dispatched subcommands |
| `hop3-tui` | terminal UI | Textual |

The same handful of concepts — *which server, where to install from, which optional services, how loud, machine-readable?* — recur in every one of these tools, and each tool spells them differently. A developer who runs `hop3`, `hop3-deploy`, and `hop3-test` in a single session, or an operator who runs `hop3-install` then `hop3`, has to relearn the flags each time. We are about to advertise a curated set of working apps; the tools that deploy and test them are part of that surface.

### What is inconsistent

The following are all *present in the code today* (surveyed flag-by-flag), not hypothetical.

**Naming the target is spelled five ways.** The reference `hop3` CLI has no `--host`: the target is a `--context` that resolves to a literal address (`ssh://root@host`), and SSH user/port are read from that URL (ADR 042). But `hop3-deploy` takes `--host/-H` + `--ssh-user/-u` + `--ssh-key/-i` + `--docker/-d`; `hop3-test system` takes `--ssh` + `--host` + `--user` + `--port` + `--ssh-key`; `hop3-test cloud` takes `--provider` + `--server-id` (a *number*). Four different vocabularies for "which machine," none matching the main CLI. The target's env var is `HOP3_DEV_HOST` (deploy), `HOP3_TEST_SERVER` (its alias), `HOP3_TEST_HOST` (test), and `HOP3_API_URL` (main) — four names for one idea.

**"Where to install from" is derived from a pile of overlapping flags.** `hop3-test system` gets it right with a single choice: `--deploy-from {local,git,pypi,none}`. But `hop3-deploy` *derives* the same choice from six flags (`--local/-l` > `--git/-g` / `--branch/-b` > `--version/-V` > `--pre` > default PyPI), one of which (`--pypi/-p`) is inert; and `hop3-install server` derives it from five (`--version`, `--git`, `--branch`, `--local-path`, `--pre`). The word "local" means three different things: `--deploy-from local` (a choice), `hop3-deploy --local` (a boolean: upload the working tree), and `hop3-install --local-path DIR` (a value: a directory to install from). Their env vars diverge too: `HOP3_LOCAL` vs `HOP3_LOCAL_PACKAGE`, `HOP3_PYPI_VERSION` vs `HOP3_VERSION`, `HOP3_PYPI_PRE` vs `HOP3_PRE`. And the default git branch is `devel` on `hop3-deploy` but `main` on `hop3-install`, and `--branch` implies `--git` on deploy but not on install.

**`--with` is one flag name with four different contracts.** It is `multiple=True` default `()` on `hop3-test system` (help: "nix, mysql, redis, all"); a single CSV string default `None` on `hop3-test cloud` (help: "docker, mysql, **postgresql**"); a CSV string default `["docker"]` on `hop3-deploy` (help: "docker, mysql, redis, nix"); and a CSV string default `""` on `hop3-install server` (help: "mysql, redis, docker, nix, s3, all"). The accepted vocabularies disagree (`postgres` vs `postgresql`), the installer silently accepts an undocumented `rust`, silently ignores `postgres` (always installed), and silently drops unknown features — a fail-loud violation hiding in a help string.

**Verbosity and automation flags are ad-hoc.** The main CLI has stacking `-v/-vv/-vvv`, `-q/-qq`, `--debug`, `HOP3_VERBOSITY`, plus `--json/-j`, `--yes/-y`, `--no-input`, `--confirm=NAME`, `--dry-run`. The siblings have a plain non-stacking `--verbose/-v` (`store_true`); `-q/--quiet` exists only on `hop3-test system` and `hop3-deploy`; there is no `--json`, no `--yes`, and no confirmation model anywhere in test/deploy/install. Even `-v` isn't safe: `hop3-test cloud` *redefines* its own `-v`, shadowing the group's.

**`--force` collides.** On the main CLI, `--force` is a specific safety-guard bypass (project-mismatch / workspace guard, ADR 042 §D14) that also implies `--yes`. On `hop3-deploy` and `hop3-install`, `--force` means "reinstall/redeploy over an existing install." Same spelling, unrelated meaning.

**A latent correctness bug.** `hop3-deploy` applies a value-flag only when it differs from the argparse default. So with `HOP3_SSH_USER=deploy` in the environment, `--ssh-user root` on the command line is silently ignored (it equals the default). The same footgun affects `--branch`, `--admin-user`, `--admin-email`, `--docker-image`, `--docker-container`. Explicit input losing to ambient input is exactly the failure mode the main CLI's resolver was built to prevent.

**Help and structure drift.** `hop3-install` doesn't use argparse subparsers — it string-matches `sys.argv[1]` and rewrites `argv[0]`, so `hop3-install server --help` reports its `prog` as `install-server.py` and the top-level help is hand-written. `hop3-test`'s docstring and CLAUDE.md still advertise `apps`, `show`, `hetzner`, and `multi-distro` subcommands that no longer exist (merged into `cloud` or deleted). `list --show` overloads one subcommand into two modes.

**Two commands one keystroke apart mean opposite things.** `hop3 deploy` (the client verb) deploys an **app** to a running server; `hop3-deploy` (the installer tool) deploys the **server itself** — the whole platform — onto a machine. The names are a hyphen apart and read as synonyms, but they operate at opposite levels; a developer reaching for one trivially invokes the other.

### What is already right (and anchors this)

The main `hop3` CLI is coherent, and ADRs 042 and 047 already decided its model: the **context is the server** (one selector, `--context`), host/user are derived from a literal `ssh://` address rather than passed as flags, **`--app` is always a flag never a positional**, verbosity stacks, and `--json` / `--yes` / `--force` mean one thing each. `hop3-test`'s `--deploy-from {local,git,pypi,none}` is the one good expression of install-source in the tree. This ADR does not invent a new style; it names the existing good one and extends it outward.

### Why now

Three forces converge. We are advertising a curated app set, so the deploy/test tooling is user-facing. The env-override bug is a real footgun a user will hit. And the docs have already drifted from the code — a sign the surface grew faster than its conventions. Consolidating now is cheaper than after each tool accretes more one-off flags.

## Decision

Adopt **one flag lexicon** — a single canonical spelling, short flag, env var, and semantics for each recurring concept — and make every Hop3 command-line tool conform to it. The lexicon is the main CLI's vocabulary (ADRs 042/047) projected onto the operator/dev tools. Tools keep whatever parser their runtime constraints require (see D8); they do **not** keep their own vocabularies.

### D1. The canonical lexicon

One concept, one flag, one env var, one meaning. `HOP3_<FLAG>` is the env var for `--flag` unless noted.

| Concept | Flag | Short | Env var | Replaces |
|---------|------|-------|---------|----------|
| Docker target | `--docker [NAME]` | — | `HOP3_DOCKER` | keep; unify the default container name |
| SSH host | `--host ADDR` | — | `HOP3_HOST` | `--ssh` + `--host`; accepts `ssh://user@host:port`; retires `HOP3_DEV_HOST`/`HOP3_TEST_SERVER`/`HOP3_TEST_HOST` |
| SSH user | `--user NAME` | — | `HOP3_SSH_USER` | `--ssh-user/-u`, `--user` |
| SSH port | `--port N` | — | — | `--port` |
| SSH identity | `--identity KEY` | `-i` | `HOP3_SSH_KEY` | `--ssh-key` (matches `ssh -i`) |
| Cloud server | `--server-id N` | — | `HOP3_SERVER_ID` | `--provider` + `--server-id` (the OS-reset target) |
| Install source | `--from {pypi,git,local}` | — | `HOP3_FROM` | `--git`, `--pypi`, `--local` (bool), `--deploy-from`, `--use-local-repo/--no-local-repo` |
| Git branch | `--branch NAME` | `-b` | `HOP3_BRANCH` | (valid only with `--from git`) |
| PyPI version | `--version V` | — | `HOP3_VERSION` | `HOP3_PYPI_VERSION` |
| PyPI pre-releases | `--pre` | — | `HOP3_PRE` | `HOP3_PYPI_PRE` |
| Local source dir | `--path DIR` | — | `HOP3_PATH` | `--local-path`, `--local-repo-path` |
| Optional services | `--with LIST` | `-w` | `HOP3_WITH` | (unify arity + vocabulary, D4) |
| Start fresh | `--clean` | — | `HOP3_CLEAN` | `--force` (reinstall sense), `--skip-reset` (inverted) |
| Bypass a safety guard | `--force` | — | — | reserved for the guard-bypass meaning only |
| Verbosity ↑ (stacking) | `--verbose` | `-v`/`-vv` | `HOP3_VERBOSITY` | plain `store_true --verbose` |
| Quiet | `--quiet` | `-q` | | (add where missing) |
| Debug | `--debug` | `-d` | | (add where missing) |
| Skip confirmation | `--yes` | `-y` | | (add to destructive ops) |
| Never prompt (CI) | `--no-input` | — | `HOP3_NO_INPUT` | |
| Machine-readable output | `--json` | `-j` | | (add where a tool emits data) |
| Plan only | `--dry-run` | `-n` | | |
| Stop on first failure | `--fail-fast` | `-x` | | (already consistent) |

Short flags are reserved **globally** by this table, not per-tool: `-i` is always the SSH identity, `-w` always `--with`, `-x` always fail-fast. Tool-specific flags that would collide (e.g. `hop3-test list --tier`) stay long-only.

### D2. One target-selection convention — no invented URLs

Remote-driving tools (`hop3-deploy-server`, `hop3-test`) select their target with the **same flags in the same spelling** across both tools — not each with its own subset, and not a fabricated URL scheme. The three target kinds are *acquired* differently (the tool creates/tears down a local container; you hand it an SSH host; it OS-rebuilds a dedicated cloud server it neither creates nor destroys), so they don't share one address space. Each keeps its own flag:

- **Docker** — `--docker [NAME]`.
- **SSH** — `--host ADDR` + `--user` / `--port` / `--identity`. `--host` also accepts the real `ssh://user@host:port` form — the same address a context's `server` uses (ADR 042) — so user and port can travel inside the address. `docker://` and `hetzner://` are **not** introduced: they are not real URL schemes, and the kinds don't reduce to one grammar.
- **Cloud** — `--server-id N` (+ `--image`) for a Hetzner-managed box.

This collapses today's `--host/-H --ssh-user/-u --docker/-d` (deploy) vs `--ssh --host --user --port` (test system) vs `--provider --server-id` (test cloud) into one shared set. `hop3-install server` has no target flags at all: it installs **on the box it runs on** (as root), the on-box counterpart to the remote drivers.

### D3. One install-source selector

`--from {pypi,git,local}` is the single choice, defaulting to `pypi`. `--branch`, `--version`/`--pre`, and `--path` are modifiers valid only with the matching source (`git`, `pypi`, `local` respectively); passing one with the wrong `--from` is a loud error, not a silent no-op. There is no separate boolean `--git`/`--local`/`--pypi`.

The default git branch is **`main`** for every tool; a dev workflow passes `--branch devel` explicitly. Today `hop3-deploy` defaults to `devel` and `hop3-install` to `main`; they converge on `main`, so the safe/production branch is the default and "give me the unstable branch" is always an explicit act.

### D4. `--with` is one validated set

`--with` accepts a comma-separated list from **one** canonical, enumerated feature set (`docker, mysql, redis, nix, s3, rust`), with `all` as the expansion. The always-on baseline (PostgreSQL — either spelling, `postgres`/`postgresql`) is **not** a feature and is never named. An unknown feature is a **loud error** listing the valid set — never silently dropped. Default is empty (baseline only) for every tool; `hop3-deploy`'s implicit `["docker"]` default is dropped.

### D5. Verbosity, automation, and output — the rich model is the client's

The full model — stacking `-v/-vv/-vvv` levels, `-q/--quiet`, `--debug`, `HOP3_VERBOSITY`, `--yes/-y`, `--no-input`, and `--json/-j` — lives on the **interactive main `hop3` CLI**, which already has it. It is *not* pushed onto the operator/dev tools: `hop3-deploy-server`, `hop3-install`, and `hop3-test` are **one-shot, non-interactive commands** that don't prompt, don't emit machine-parsed data, and have no use for a verbosity level beyond on/off. Forcing the rich model onto them is churn without benefit.

Those tools therefore carry only the minimum: a boolean `-v/--verbose` and (where it already exists) `-q/--quiet`, plus `--clean`/`--force` (D6). What is enforced across all of them: **no tool redefines a global short flag locally** (e.g. `hop3-test cloud` must not shadow the group's `-v`), and short flags keep their global meaning (D1). A tool that grows a data-emitting mode (a `--list-images`, a status query) may add `--json` at that point — but it is not a blanket requirement.

### D6. `--force` means one thing

`--force` is reserved for "bypass a safety guard" (the main CLI's meaning). "Reinstall / redeploy over an existing install" is `--clean`. The installer's current force-reinstall flag is renamed accordingly.

### D7. One env-var scheme and one precedence rule

One env var per concept, named `HOP3_<FLAG>` for `--flag`, replacing the `HOP3_PYPI_VERSION` / `HOP3_LOCAL_PACKAGE` / `HOP3_DEV_HOST` sprawl. Precedence is uniform and correct everywhere: **explicit flag > env var > built-in default**, and an explicitly-passed flag wins *even when its value equals the default* (fixing the `hop3-deploy` sentinel bug). Implement with "was this provided" tracking (argparse `default=SUPPRESS`, or a None sentinel), never by comparing against the default value.

### D8. Enforcement: one lexicon, per-tool definitions, drift caught at the seams

There is **no single arg-spec module imported by every tool.** `hop3-testing`
depends on `hop3-installer` only to run the shipped `hop3-deploy-server` binary
as a subprocess — it deliberately imports none of the installer's code, so it
exercises the same binary a user would; a shared Python module would couple the
two against that grain, and the installer must stay stdlib-only regardless (it is
bundled into the `curl … | python3` one-liner and runs before any dependency
exists). Instead, **this document's lexicon is the source of truth for the
names**, and each tool defines its own options to match it:

- `hop3-installer` (both `hop3-deploy-server` and `hop3-install`) keeps argparse
  and stays stdlib-only. Its two tools live in one package, so they share one
  small stdlib module for the migration mechanics (deprecation aliases) and the
  lexicon constants.
- `hop3-test` keeps Click and defines matching options with its own small alias
  helper; it does not import the installer's definitions.
- The main `hop3` CLI is the source of the vocabulary; it already conforms.

Drift between the tools is caught not by a shared module but by **contract tests
at the coupling seams** — chiefly the Test Lab ↔ engine contract, which pins the
exact flags the Lab passes to `hop3-test`. Documentation (help strings,
CLAUDE.md, `docs/`) is checked against the lexicon so phantom commands and stale
feature lists can't recur.

`hop3-install` keeps its current subcommand dispatch rather than moving to
argparse subparsers: `prog` reading `install-server.py` is *correct* for the
bundled standalone (`curl | python3` runs a file of that name). Where the
`hop3-install server --help` program name matters, set `prog` explicitly.

### D9. `hop3-test`: one `run`, with cardinality as a flag — not a `system`/`cloud`/`matrix` split

`system` and `cloud` are not fundamentally different commands. Both deploy Hop3 and run the identical app/demo/tutorial catalog through the same core (`cli.runners.run_single_test` → the three runners → `DeploymentSession`, over a `RemoteTarget`). `cloud` adds exactly two things over `system --host`: it OS-rebuilds a *dedicated, operator-supplied* Hetzner server before testing (via `servers.rebuild` — it never creates or destroys the machine), and it can sweep a list of OS images serially on that one server. So the axes that actually matter are the **target** (docker / SSH host / managed cloud server) and the **cardinality** (one target vs an OS-image sweep) — not "local vs cloud."

There is **one command, `hop3-test run`**, and both axes are expressed as *flags* on it — cardinality does not warrant a second command:

- **Target** per D2 — `--docker`, `--host`, or `--provider hetzner` (+ `--server-id`/`--image`) to OS-rebuild a managed box first. Subsumes `system` and the single-image `cloud` path.
- **Cardinality** — a single target by default; **`--images ubuntu-24.04,debian-13`** (or `--images all`) sweeps a matrix of OS images, each leg a full `run --provider hetzner --image X` (provision → deploy → test → persist), aggregated. `--list-images` lists them.

A first draft made the sweep its own command (`matrix`, with `cloud` as an alias). Rejected on reflection: the sweep is *`run` repeated over images* — same lexicon, same core — so "one vs many" is exactly what a flag expresses, and a whole command (plus its help, its alias, its docs) is heavier than `--image` vs `--images`. Folding it in leaves a single command whose help holds the entire cloud cluster (`--provider/--image/--images/--server-id/--list-images`) in one place.

The two deploy wrappers behind these — the `DeploymentTarget.start()` path (docker/ssh) and the separate `system_tests` `DeploymentManager` (cloud) — collapse onto one as a consequence: the cloud target is a `RemoteTarget` to the rebuilt server's address, which is what it already SSHes to. `list` and `why` are orthogonal and unchanged.

The cloud target should additionally **provision** — create a throwaway server and free it afterwards — making `--server-id` optional (today it only OS-rebuilds a dedicated, operator-supplied box). That is a real missing feature and gets its own ADR; it is noted here only because it shapes the `--server-id`/`--image` surface this one is unifying.

### D10. Rename `hop3-deploy` to `hop3-deploy-server`

The tool is renamed to **`hop3-deploy-server`** so its name states what it deploys — the server/platform, not an app — and no longer collides with the client's `hop3 deploy` verb. The name parallels `hop3-install server` (the production counterpart): both act on the server, one from local dev code over SSH/Docker, the other on-box as root. `hop3-deploy` is kept as a deprecated alias for one release (a one-line notice pointing at the new name), then removed. The entry point, `HOP3_*` env vars, Makefile targets, and docs move to the new name in the same change.

### Before / after

```
# today
hop3-deploy --host prod.example.com --ssh-user root --git --branch devel --with mysql,redis
hop3-test system --ssh --host prod.example.com --deploy-from git --branch devel --with mysql,redis
hop3-install server --local-path /src --branch main --with mysql,redis,s3 --domain x

# under this ADR (no invented URLs; --host takes a plain host or the real ssh:// form)
hop3-deploy-server  --host ssh://root@prod.example.com --from git --branch devel --with mysql,redis
hop3-test run       --host ssh://root@prod.example.com --from git --branch devel --with mysql,redis
hop3-install server --from local --path /src --with mysql,redis,s3 --domain x   # on-box; no target
```

## Rejected alternatives

**One parser for all tools.** Appealing, but `hop3-installer` cannot take a dependency (Click/Typer) — it is stdlib-only by construction so the bundled one-liner installer works on a bare box. Unifying the *vocabulary* across parsers (D8) delivers the consistency without forcing a single framework.

**Fold the operator tools into `hop3` subcommands** (`hop3 deploy-server`, `hop3 test`). The lexicon makes them *look* like one tool; making them *be* one is tempting but wrong: they are completely different programs. `hop3-install`/`hop3-deploy` run before `hop3-cli` exists, as root, and ship bundled standalone; `hop3-test` is a dev-only dependency with a heavy import graph; the client talks to a running server. They stay separate binaries — the shared lexicon gives the *feel* of one family without the coupling.

**A single `--target URL` with `docker://` / `hetzner://` schemes.** The first draft of this ADR. Rejected: those are invented URL schemes, and the three target kinds are acquired too differently (create-and-destroy a container, attach to a host, OS-rebuild a dedicated server) to coherently share one address grammar. Only `ssh://` is a real scheme, and it is accepted as one *form* of `--host` (D2), not as a mandatory wrapper.

**Keep `system` and `cloud` as the top-level split.** Rejected: it names the target *provider* (local vs cloud) as the command boundary, but the boundary that actually matters is single-target vs OS-image sweep. It also keeps two deploy wrappers for one shared test core and leaves `cloud` a grab-bag (single-server run and multi-image sweep conflated in one command).

**Do nothing / per-tool freedom.** The status quo. Rejected: it already produced a correctness bug (D7), silent-failure help strings (D4), and doc drift, and the cost compounds with every new flag.

## Consequences

- One mental model. `--host`/`--docker`, `--from`, `--with`, `-v/-q`, `--json`, `--yes` mean the same thing in every tool; muscle memory transfers.
- A correctness fix (D7) lands as part of the cleanup, not as a separate patch.
- Help, CLAUDE.md, and docs derive from one spec, so they stop drifting.
- Migration cost is real: flags and env vars are renamed. Mitigated by back-compat aliases (Migration) so no invocation breaks on the first release.
- The installer stays dependency-free; only its *spelling* changes.

## Migration

Old names remain accepted as **deprecated aliases** for one release, each emitting a one-line stderr deprecation notice pointing at the new spelling — the renamed binary (`hop3-deploy` → `hop3-deploy-server`), flags (`--ssh-user` → `--user`, `--ssh-key` → `--identity`, `--local` → `--from local`, `--deploy-from git` → `--from git`), the changed `--branch` default (`devel` → `main`), and env vars (`HOP3_PYPI_VERSION` → `HOP3_VERSION`, etc.). The alias table lives beside the shared spec. Makefile targets and `docs/` examples move to the new spelling in the same change. The phantom `hop3-test` subcommands are removed from the docstring and CLAUDE.md immediately (they don't exist, so there's nothing to alias). Aliases are dropped in the following release.

The `hop3-test cloud`/`matrix` commands are the one exception to the deprecated-alias rule: because the image sweep becomes a *flag* (`run --images`, D9) rather than a renamed command, there is no command to alias it to, so both are removed outright. The sole automated consumer (the Test Lab, ADR 044) shells `hop3-test run`, never `cloud`/`matrix`, so nothing breaks.
