# ADR 036: CLI Ergonomics and Command Surface

- **Status**: Accepted
- **Type**: Design
- **Created**: 2026-03-05
- **Updated**: 2026-06-24
- **Related-ADRs**: 018, 019, 025, 031, 039, 042

The app-resolution chain (D7) and sticky-context state (D8) are superseded by [ADR 042](042-cli-context-model.md). Under ADR 042's second revision a *context* is a per-project deploy **environment** declared in the project's committed `hop3.toml` as `[contexts.<name>]` (server address + app + domains + non-secret env); the global `config.toml [contexts.*]` connection model was retired, `config.toml` holds no contexts (only prefs/aliases and an optional default-server address), and the per-server token lives in `~/.config/hop3-cli/credentials.toml`. The per-context `default_app` and the git-remote app source were dropped, and the resolution chains were redefined. The body of D7/D8 is retained for the record, with in-section supersession notes. (Updated for ADR 042 r2 on 2026-06-24; an earlier note here described the r1 "global connection in config.toml" model, which was itself superseded.) All other decisions remain authoritative.

> **Read alongside**: [ADR 031 (Terminology)](./031-project-terminology.md), [ADR 039 (Plugin CLI extension)](../cli/plugin-mechanism-todo.md), and the evidence in [`notes/cli/`](../cli/README.md).

## Context

The Hop3 CLI is the primary interface for managing applications. As a PaaS targeting users familiar with Heroku, Docker, Fly.io, Railway, and modern developer tooling (kubectl, gh, gcloud), the CLI must feel familiar to migrants and better than what they're used to. ADR 025 covers output styling; this ADR covers the command surface, argument grammar, help organization, discoverability, sticky state, aliases, and error handling.

### Sources of evidence

- [`competitive-analysis.md`](../cli/competitive-analysis.md) — how eight PaaS platforms organize their CLIs.
- [`real-world-usage.md`](../cli/real-world-usage.md) — measured frequencies and error rates from a 112-command shell-history sample.
- [`terminology-research.md`](../cli/terminology-research.md) — `env` vs `config`, `addon` vs `service`.
- [`addon-commands-analysis.md`](../cli/addon-commands-analysis.md) — addon command gap vs competitors.
- [`feature-gaps.md`](../cli/feature-gaps.md) — other missing commands.
- [`discussion.md`](../cli/discussion.md) — design discussion behind the command surface.
- [`command-catalog.md`](../cli/command-catalog.md) — complete canonical command list produced by this ADR.

### Key empirical findings

- **Command usage is concentrated**: six commands account for ~90% of daily use.
- **`run` has a measured ~40% error rate** under the old positional-app grammar. This is the single largest ergonomic failure in the current CLI.
- **`--context prod` appears in ~50% of typed commands** — large pure-boilerplate cost.
- **App-name typos are silent**: the CLI provides no "did you mean" suggestions.
- **Hop3 has a single user today**: no backwards-compat constraint; a clean break is cheap.

## Decisions

Decisions are grouped by concern. Each decision has a one-paragraph motivation.

### Syntax and structure

#### D1 — Commands are space-separated, with a hybrid top-level / namespaced surface

All multi-token commands use spaces (`hop3 env set`), not colons. The top-level surface holds (a) daily app-scoped verbs, (b) utilities, and (c) namespace roots. Namespaces hold management and CRUD verbs. The move from the legacy colon forms is a single breaking change: old colon forms produce a did-you-mean error that explicitly names the new spelling rather than silently aliasing.

*Motivation*: spaces are the modern convention (docker, kubectl, gh, gcloud, aws, fly, railway, helm, terraform). Colons require bash `COMP_WORDBREAKS` hacks and read as retro. Top-level for frequent verbs matches Heroku/Fly/Railway; namespaces scale and add friction to destructive operations.

#### D2 — Top-level placement is governed by a principled rule

A command is top-level if and only if *all three* are true:
1. It operates on at most one app.
2. It is a read (`logs`, `status`, `ps`), a non-destructive runtime control (`restart`, `scale`, `ssh`, `open`), or a deploy verb (`deploy`, `run`).
3. It is in the top ~15 by frequency.

Everything else — create, destroy, rename, configuration mutation, non-app resources — lives under a `<noun> <verb>` namespace.

*Motivation*: the rule keeps the top-level surface small enough to learn in one sitting while placing dangerous operations behind extra friction.

#### D3 — Namespace inventory: 11 canonical namespaces

`app`, `addon`, `backup`, `env`, `context`, `user`, `system`, `auth`, `completion`, `plugin`, `help`. (`config` is a back-compat alias of `env` — see D17.)

Flattened from today: `admin:user:*` → `user *`. Removed from user-visible surface: `admin`, `git`, `nix`. `sbom` demoted from top-level to `app sbom`.

*Motivation*: three-level nesting (`admin user add`) is painful. `admin` had no content other than `user` and `system`. `git` and `nix` expose implementation details users shouldn't think about.

#### D4 — Verb naming: create/destroy vs add/remove split by semantic

| Verb | Use when | Applied to |
|------|----------|------------|
| `create` / `destroy` | Hop3 instantiates and tears down the resource | `app`, `addon`, `backup` |
| `add` / `remove` | Hop3 registers or de-registers an externally-existing entity | `user` (a person), `context` (server reference), `domain` (DNS entry), `access` (grant) |
| `list` | Summary of many | all |
| `show` | Full state of one | all |
| `get` | One specific value (key granularity) | `env get KEY` |
| Domain verbs | Operation-specific, not expressible above | `attach`/`detach`, `enable`/`disable`, `grant-admin`/`revoke-admin`, `set-password`, `generate-token`, `restore`, `ping`, `start`/`stop`/`restart`, `set`/`unset`, `register`, `use`, `rename` |

`info` is dropped entirely; use `show`. `delete` and `destroy` are not both verbs in the vocabulary — only `destroy` for Hop3-instantiated resources, `remove` for externally-existing entities.

*Motivation*: `create` / `destroy` carry semantic weight that makes them inappropriate for entities existing outside Hop3 ("destroying a user" sounds violent; users are people Hop3 registers, not provisions).

#### D5 — Arguments: `--app` is always a flag; positionals are the direct object

The app is *never* positional. Every command that targets an app takes it via `--app <name>` (short form `-a`), or resolves it implicitly (D7). The positional slot(s) are for the direct object of the verb (the resource being created, the KEY=VALUE being set, the command being run).

*Motivation*: the old positional-app grammar was the root cause of `run`'s ~40% error rate. Making `--app` universal eliminates the category of error entirely and makes `run` unambiguous without a `--` separator.

### Resolution and state

#### D6 — Global flags

| Long | Short | Scope | Does |
|------|-------|-------|------|
| `--help` | `-h` | all | show help |
| `--version` | — | top-level only | show version |
| `--app <n>` | `-a` | app-scoped | target app |
| `--context <n>` | `-c` | server-touching | target context |
| `--json` | — | read commands | machine-readable output |
| `--quiet` | `-q` | all | suppress non-essential output |
| `--verbose` | `-v` | all | stackable: `-v`, `-vv`, `-vvv` |
| `--yes` | `-y` | destructive | skip confirmation prompt |
| `--force` | — | most dangerous | override safety checks |
| `--confirm <name>` | — | typed-name ops | scriptable alternative to interactive typed-name prompt; preserves other safety checks |
| `--no-input` | — | all | refuse to prompt; fail with instructions if input would be required |
| `--no-color` | — | all | disable ANSI color (deferred — use `NO_COLOR=1` env var) |
| `--no-progress` | — | long-running | disable spinners (deferred — no long-running spinners yet) |
| `--config <path>` | — | all | alternative CLI config file (deferred — use `HOP3_CONFIG_DIR`) |
| `--no-alias` | — | all | bypass alias resolution |
| `--why` | — | all | print resolution trace and exit (diagnostic-only — does not run the command) |

Flags may appear before or after the subcommand. Environment-variable equivalents (e.g., `HOP3_APP`, `HOP3_CONTEXT`) follow the pattern `HOP3_<FLAG>`. `--json` implies non-interactive (no prompts, no colors, no spinners).

#### D7 — Implicit app resolution

> **Superseded by ADR 042.** The resolution chain is defined in
> [ADR 042 §Resolution](042-cli-context-model.md#resolution).
> Notable deltas: the app now resolves **CWD-rooted** — sources 6 (`default_app`)
> and 7 (git remote) below are **dropped**, and `hop3 use <app>` writes a
> `.hop3-app` pin (source 3) instead of a context default. Project-scoped
> `[contexts.*]` in the committed `hop3.toml` is the source of truth; the r1
> global `config.toml [contexts.*]` was retired (ADR 042 r2, 2026-06-24). The
> selected context's app is a *conditionally-trusted* source (ADR 042
> §Resolution). The body below is retained for the record; see ADR 042 for the
> authoritative chain.

When a command requires `--app` and none is given, resolve in order:

1. `--app` (or `-a`) on the command line
2. `$HOP3_APP` env var
3. `.hop3-app` file in CWD or any ancestor directory up to `$HOME`
4. `[cli].app` in `hop3.toml` in CWD or any ancestor
5. `[metadata].id` in `hop3.toml` in CWD or any ancestor — the project's canonical name, the "I'm physically standing in this project" source
6. Active context's `default_app` from `~/.config/hop3-cli/state.toml`
7. Git remote named `hop3` if it uniquely identifies an app on the active context

Unresolvable → fail with the chain printed and a one-line fix suggested.

#### D8 — Sticky state: contexts and default app

> **Superseded by ADR 042.** Under ADR 042 r2 a **context** is a per-project
> deploy environment declared in the committed `hop3.toml` as `[contexts.<name>]`
> (server address + app + domains + non-secret env), managed by `hop3 context`
> (there is no `hop3 server`, no `servers.toml`, and no per-context `default_app`).
> The server connection is invisible plumbing: the bearer token lives in
> `~/.config/hop3-cli/credentials.toml` keyed by server address, and `config.toml`
> is secret-free (prefs + an optional default-server pointer). `hop3 use <app>`
> now pins the app for the current directory by writing `.hop3-app`. The
> per-checkout context selector is `.hop3-local.toml [local].context`
> (`.hop3-context` was retired). Body retained for the record.

- **Active context** lives in `~/.config/hop3-cli/state.toml` (XDG). Set via `hop3 context use <name>`. Overridable per-shell by `HOP3_CONTEXT`, per-project by `hop3.toml [cli].context`.
- **Context's default app** lives in the same file under `[contexts.<name>].default_app`. `hop3 use <app>` is sugar for setting the current context's default app.
- **Context resolution** mirrors app resolution: `--context` flag → `$HOP3_CONTEXT` → `hop3.toml` → `state.toml` → error.
- **`hop3 context`** (bare) prints the active context + resolved defaults + source. `hop3 use` (bare) prints the resolved app + source.
- **`--why`** on any command prints the resolution trace and exits — diagnostic-only, so `hop3 deploy --why` shows how `<app>` resolves without actually deploying.
- **Atomic writes** (write-temp + rename); last-write-wins on racing shells.

`hop3 init` interactively creates the first context. `hop3 context add <name>` adds subsequent ones.

### Aliases

#### D9 — Alias mechanism: disjoint union, no shadowing

**The alias table is a disjoint union** of three layers (core, plugin, user). **Collisions are forbidden.**

- Core and plugin collisions → plugin load fails (strict by default; lax via `HOP3_PLUGIN_COLLISION_MODE=lax`).
- User-config collisions with core or plugin → the user alias is skipped with a warning on next bare `hop3` invocation (loud but non-fatal; one bad line doesn't break the whole CLI).

**Resolution rule**: an alias fires *unless* the next token would be a known subcommand of the target namespace side of the expansion. Flags do not count as subcommands. For the conflict case, `hop3` emits a did-you-mean error rather than silently dispatching.

**Prefix aliases are supported**: an alias may rewrite the first N tokens, not just the first. `pg = "addon postgres"` is valid and makes `hop3 pg diagnose mydb` expand to `hop3 addon postgres diagnose mydb`. The subcommand-check at the expansion point still applies.

**Sources**:
- **Core aliases** (built-in, shipped with the CLI): small curated set — see `command-catalog.md`.
- **Plugin aliases**: registered via the plugin manifest (see ADR 039).
- **User aliases**: in `~/.config/hop3-cli/config.toml` under `[aliases]`. Static text expansions only (no `$VAR`, no backticks). Circular or unresolvable → rejected.

**`--no-alias`** bypasses resolution entirely.

`hop3 aliases` lists all effective aliases with source and expansion; flags skipped-user aliases for remediation.

### Error handling and discoverability

#### D10 — Did-you-mean and bare-command help

When an unknown top-level command, subcommand, or app name is given, suggest the closest match (Levenshtein ≤ 2). When a required argument is missing, show that command's help instead of a bare usage error. `hop3 --context prod` (no subcommand) shows top-level help with a note that context is set. `hop3 app` (namespace bare) shows that namespace's subcommand list.

#### D11 — Help output format

Help is layered:

- **`hop3`** (bare) and **`hop3 help`** — categorized top-level surface (Daily / Lists / Management / Administration / Utilities) plus a dynamic bottom line showing the resolved active context and current app if any. The very last line is a feedback link: `Report issues: https://github.com/abilian/hop3/issues`.
- **`hop3 <namespace>`** — namespace's subcommands with inline alias notes.
- **`hop3 help <cmd>`** and **`hop3 <cmd> --help`** — structured format: **USAGE / EXAMPLES / POSITIONAL / OPTIONS / SEE ALSO / Part of:**. **Examples lead** (after USAGE) because users skim and examples are the highest-bandwidth signal; at least one example is mandatory for every command.
- **`hop3 help --all`** — flat alphabetical list with markers (`[top]`, `[alias → …]`, `[local]`, `[plugin: X]`).

Full format specification in `command-catalog.md`.

#### D12 — Shell completion

Static + dynamic completion for bash, zsh, fish. Static completion is bundled; dynamic refresh via `hop3 completion --refresh` fetches the current server's command tree from the `help:commands` RPC and caches at `~/.cache/hop3/commands.txt`. App-name completion queries the cached app list.

Under D1 (space-separated), the `COMP_WORDBREAKS` bash hack is no longer necessary.

#### D13 — `--json` output envelope

Read commands with `--json`:

```json
{
  "status": "ok",
  "data": <command-specific payload>,
  "meta": { "context": "...", "app": "...", "timestamp": "..." }
}
```

Errors:

```json
{
  "status": "error",
  "error": { "code": "APP_NOT_FOUND", "message": "...", "suggestion": "...", "exit_code": 3 },
  "meta": { ... }
}
```

Exit code 0 on success (including empty results). Non-zero only for actual errors. `exit_code` in the envelope matches `$?`.

### Safety

#### D14 — Confirmation prompts on destructive operations

Destructive operations (`destroy`, `restore`, `user remove`, `context remove`) prompt by default.

- The most severe ops (`app destroy`, `addon destroy`, `backup destroy`) require typing the resource name as confirmation.
- Others (`backup restore`, `user remove`) use `[y/N]`.
- `--yes` / `-y` skips the prompt but still prints the preview.
- `--confirm=<name>` is the scriptable alternative for typed-name ops: `hop3 app destroy myapp --confirm=myapp` works without a tty and preserves all other safety checks (context warnings, attached-addon detection). Use this in scripts in preference to `--force`.
- `--force` overrides all safety checks. Required for `app destroy` and `context remove` when apps exist in that context; also bypasses preview and attached-resource warnings.
- **No `--password` flag for secret input.** Secrets come from (a) an interactive prompt with no echo, (b) `--stdin` reading from stdin, or (c) `--password-file <path>` reading from a file. Flag values leak into `ps`, shell history, systemd/Docker inspection.
- Non-tty invocation without `--yes`, `--confirm=<name>`, or `--force` refuses to proceed. The CLI never silently assumes yes in scripts.
- Context-mismatch warning: if a destructive op is run in a non-sticky context, a visible warning precedes the prompt.
- No `--dry-run` for destructive ops (deferred as unnecessary; the preview shown with `--yes` and the typed-name prompt serve the audit purpose).

#### D15 — Hidden commands

A command with `hidden: True`:
- Does not appear in `hop3 help`, help-all, namespace help, or tab completion.
- Still invokable explicitly if its name is typed.
- Appears in `hop3 help --hidden` (opt-in view).
- Cannot be the target of a user-defined alias (rejected at load).

Current hidden commands: `git-hook` (git invocation), `help:commands` (RPC endpoint). `nix:eject` is removed from the CLI entirely.

### Exit codes and contract

#### D16 — Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success (including empty results) |
| 1 | Generic error (fallback) |
| 2 | Usage / syntax error |
| 3 | Resolution error (app / context not found) |
| 4 | Authentication error (not logged in, token expired) |
| 5 | Authorization error (forbidden) |
| 6 | Conflict (already exists) |
| 7 | Network / server error |
| 8 | Deployment failure |
| 9 | Plugin error |
| 10 | Confirmation declined or non-tty blocked |
| 130 | Interrupted (SIGINT) |

Scripts can distinguish user error (2, 10), resolution (3), auth (4, 5), server (7), and deployment (8). JSON envelope includes `error.exit_code` for programmatic access.

### Terminology

#### D17 — `env` and `addon` are the canonical terms

- **`env`** for environment variables. Canonical commands are `env show/get/set/unset/live`. `config` is a full back-compat alias, registered server-side on each command, so `hop3 config set …` keeps working — no breakage for existing scripts or docs. Procfile→`hop3.toml` conversion is `app migrate`, not an `env` subcommand: it is not environment management.
- **`addon`** for backing services. "Service" is overloaded across modern PaaS (means app components in Railway/Render).

`env` is canonical rather than `config` (the Heroku/Piku lineage) because `config` collides with `hop3.toml`, the app's *configuration file*. `hop3 config show` listing environment variables while "the config" means the TOML file is a naming clash. `env` names exactly what the commands manage (environment variables), and the `config`/`settings` vocabulary is then freed for future app-level settings. `config` is retained as a full alias purely for compatibility.

### Extensibility

#### D18 — Plugin extension: see ADR 039

Plugins register commands, sub-namespaces, top-level namespaces, and aliases. Full design is ADR 039; key decisions captured in [`plugin-mechanism-todo.md`](../cli/plugin-mechanism-todo.md):

- Command name as tuple of tokens.
- Sub-namespaces under `addon` for addon type-specific operations (`addon postgres diagnose`). An addon subcommand must not reuse a top-level verb name with a different meaning — e.g. the per-addon diagnostic is `addon <type> activity`, not `ps`, since top-level `ps` means scaling.
- Plugin manifest in `pyproject.toml [tool.hop3.plugin]`.
- Command tree served by `help:commands` RPC (extended with children + positional/flag schema).
- 3-level depth is a strong guideline; 4+ discouraged but not hard-rejected.

### Output conventions

#### D19 — Stdout/stderr discipline, `-` for files, state-change summaries

Three cross-cutting rules for well-behaved Unix-citizen output.

**(a) Primary output to stdout; messaging to stderr.** Every command splits its output:

- **stdout**: the command's primary data — log lines from `logs`, status table from `status`, app list from `apps`, JSON envelope under `--json`. Anything a downstream pipe might consume.
- **stderr**: progress spinners, confirmation prompts, warnings, errors, diagnostic messages, the `--why` trace, the dynamic "Active context / Current app" line.

Pipes keep the data stream clean. `hop3 apps | grep prod` and `hop3 logs | tee logs.txt` behave as expected. Errors and warnings remain visible even when stdout is redirected.

**(b) Support `-` for file arguments.** Any flag that accepts a file path accepts `-` to mean stdin (for reads) or stdout (for writes). Examples:

```
hop3 env set --from-file -              # read KEY=VAL pairs from stdin
cat .env | hop3 env set --from-file -
hop3 backup download <id> -             # stream backup to stdout (future)
hop3 user set-password alice --password-file -   # read from stdin
```

This is the Unix convention and composes with pipes. `--password-file -` is equivalent to `--stdin` for secret input (D14).

**(c) Mutating commands acknowledge state change.** Every command that mutates server state prints a one- or two-line summary of what changed, to stderr (per rule (a)). Silent success on mutation is a bug, not a feature.

Examples:

```
$ hop3 env set FOO=bar
[prod / myapp] set FOO=bar; restarted web worker.

$ hop3 deploy
[prod / myapp] deployed rev a2c4f8; 3 processes running.

$ hop3 addon attach mydb --app myapp
[prod / myapp] attached addon 'mydb' (postgres); added DATABASE_URL.
```

Format: bracketed `[context / app]` prefix when both resolve, then the state change and any cascading effect. Machine-readable equivalents appear in the `--json` envelope's `data.summary` field.

Silent success is permitted only for pure reads (`logs`, `status`, `apps`) and for explicit-quiet mode (`--quiet`).

## Consequences

### Positive

1. **Error rate drops substantially** on `run` (per D5, D7) and app-name typos (per D10 with cached app list from D12).
2. **Typed characters drop ~50%** on server-touching commands (per D8 sticky context).
3. **Discoverability improves**: categorized help (D11), namespace help pages, did-you-mean (D10), `hop3 aliases` introspection.
4. **Familiarity for migrants**: Heroku/Docker/Fly/Railway users recognize most of the surface; cross-platform aliases (D9) ease migration.
5. **Scriptability**: consistent exit codes (D16), JSON envelope (D13), non-tty safety (D14).

### Negative

1. **Implicit-app footgun**: mitigated by `--why`, source attribution in help, and context-mismatch warnings (D14).

### Trade-offs

| Choice | Alternative | Chosen because |
|--------|-------------|----------------|
| Space-separated | Colon-separated | Modern convention; tab-completion; no bash hacks |
| Hybrid top-level + namespaced | All top-level | Top-level stays small, learnable |
| Hybrid | All namespaced | Daily commands should fall to hand |
| `--app` always flag | Positional allowed | Eliminates `run` grammar failure |
| Sticky context at context-level only | Global default + context default | Avoids two sources of implicit app |
| No shadowing | User aliases override built-ins | Predictability trumps ergonomics for dangerous ops |
| `create`/`destroy` + `add`/`remove` | Single verb | Semantic accuracy ("creating a user" is weird) |

## Alternatives Considered

| Alternative | Rejected because |
|-------------|------------------|
| Colon separator | Retro; tab-completion clumsy; `COMP_WORDBREAKS` required |
| Hyphen separator | Conflicts with flag syntax (`--config-set`) |
| All-flat (no namespaces) | Doesn't scale beyond ~15 commands |
| All-namespaced (`app deploy`, `app logs`) | Too much typing for daily ops |
| Positional app everywhere | Causes the `run` grammar failure |
| Single creation verb everywhere | Semantic mismatch for users / contexts |
| `delete` instead of `destroy` | Weaker safety signal |
| Global default app (independent of context) | Two implicit-app sources confuse on context switch |
| User aliases may shadow built-ins | Unpredictable behavior for destructive ops |
| `--dry-run` on destroy | Unnecessary complication |
| Keep colon forms as aliases | Clutter; single-user means no migration cost saved |

## Open / Deferred

| Item | Where |
|------|-------|
| Plugin extension mechanism | ADR 039 |
| Blueprint commands | Deferred until Blueprint feature is designed (ADR 031) |
| Top-level `pg` / `psql` shortcuts | Users can add via `[aliases]` config; reassess if usage justifies built-in |
| `ssh` canonical command | Defined as top-level verb in D2; implementation TBD |
| `domain`, `release`, `drain`, `access` namespaces | Future features; namespace placeholders reserved |

## References

### Related ADRs
- [ADR 018: CLI Architecture](./018-cli-architecture.md)
- [ADR 019: CLI Commands](./019-cli-commands.md)
- [ADR 025: CLI User Experience](./025-cli-user-experience.md)
- [ADR 031: Project Terminology](./031-project-terminology.md)
- ADR 039: Plugin CLI Extension (brief at [`plugin-mechanism-todo.md`](../cli/plugin-mechanism-todo.md))

### Supporting evidence and data
- [`notes/cli/README.md`](../cli/README.md) — index
- [`competitive-analysis.md`](../cli/competitive-analysis.md)
- [`real-world-usage.md`](../cli/real-world-usage.md)
- [`terminology-research.md`](../cli/terminology-research.md)
- [`addon-commands-analysis.md`](../cli/addon-commands-analysis.md)
- [`feature-gaps.md`](../cli/feature-gaps.md)
- [`discussion.md`](../cli/discussion.md) — grilling record
- [`command-catalog.md`](../cli/command-catalog.md) — complete canonical command list

### External
- [CLI Guidelines](https://clig.dev/)
- [12 Factor CLI Apps](https://medium.com/@jdxcode/12-factor-cli-apps-dd3c227a0e46)
- [Command Line Interface Guidelines](https://primer.style/cli/)
