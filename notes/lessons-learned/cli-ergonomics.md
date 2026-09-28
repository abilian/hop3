# Lessons Learned: CLI Ergonomics & Surface Evolution

**Updated**: 2026-09-25, adding the two parsers that read one argv. 2026-09-08 added the `app shell` round (validate before you confirm, global flags, one ssh settings object). 2026-09-01 added the September round (a corrupt cache, a hand-copied registry, scraping the peer's prose, and secrets on the command line), from measuring a maintainer's shell history against the shipped CLI.

How to evolve the CLI command surface (rename, de-duplicate, deprecate) without breaking users. The design decisions behind it are in [ADR 036](../adrs/036-cli-ergonomics.md).

## Rename Behind an Alias, and Keep the Old Spelling Working

A rename changes the *canonical* name; it must not break what users already type. Change the command's canonical name and register the old name as an alias to the same handler. The dispatch table maps both; the help catalog advertises only the canonical one.

```python
class CreateAppCmd(Command):
    name = ("app", "create")            # new canonical
    aliases = [("app", "launch")]       # old spelling still dispatches
```

Test both directions: the new canonical resolves, and every old alias resolves to the *same* handler.

## Deprecate by Hiding

When a command is superseded by a flag or by another command, mark it `hidden`. Hidden commands are excluded from the help catalog (the surface stays clean) but remain dispatchable (scripts and muscle memory keep working).

- `app build-logs` → folded into `app logs --build`; `BuildLogsCmd` kept `hidden = True`.
- `auth register` → an admin-gated subset of `user add`; deleted the class, kept `("auth", "register")` as an alias of `user add`.

The catalog the client fetches filters `hidden`, but dispatch keeps it: test both invariants.

## A Rename Isn't Finished Until the Platform Stops Teaching the Old Name

Every place the platform prints a command name is part of the surface: failure diagnostics, troubleshooting hints, and a command's own `--help`/usage text. When those still show the old spelling, users learn the deprecated form.

**Case (June 2026):** after renaming `app launch`→`create`, `domains`→`domain`, `backup info`→`show`, and `app build-logs`→`app logs --build`, dispatch resolved both names and the suite was green. But ~10 user-facing messages still printed the old spelling, including the deployer's hint on *every* failed build (`run hop3 app build-logs`).

Two checks caught it:

1. Rebuild the real dispatch table and assert every new canonical *and* every old alias resolves to the expected handler; assert each hidden command is absent from the catalog but present in dispatch.
2. `grep` every user-facing string (diagnostics, hints, usage, `--help`) for the old spellings; the command definition is not the only place names appear.

## Never Advertise a Path the User Can't Actually Take

Help text and errors must only suggest actions the caller can perform *from their current state*. A confident pointer to an impossible flow is worse than silence: it sends the user down a dead end and erodes trust in every other message.

**Case (June 2026):** the "Authentication required" (401) error told an *unauthenticated* user to `hop auth register …`, but account creation is admin-only (`user add`). An unauthenticated user can never register. The fix removed the register line, leaving only the path that works (log in with admin-provided credentials).

## A Client-Side Cache Is a Feature's Weakest Link

Suggestions, completion and offline help all read a cache the client writes locally. That cache stops working in three ways, all of which present as "the feature does nothing":

- **It was written in place.** An interrupted write leaves a truncated or NUL-padded file that nothing downstream can tell from content. Write beside the target and rename over it, so a reader sees either the old file or the new one.
- **Nothing refreshes it.** A cache filled only by an explicit `--refresh` subcommand holds, for most users, whatever it held the day they installed the CLI. Hang the refresh on an event that already happens: a successful login.
- **A damaged file reads as content.** Parse on read and keep only well-formed names, so a corrupt cache degrades to an absent one, which every caller already handles.

**Case (September 2026):** a maintainer's shell history showed five command typos and no evidence of a suggestion. Three plausible explanations queued up: thin coverage, a cache refreshed only by hand, suggestions reconstructed from error prose. All three were real. None was the immediate cause. `~/.cache/hop3/commands.txt` on that machine held four NUL bytes, dated the same minute as an empty `apps.txt`: since that July write, the suggestion path had been reading garbage and returning nothing.

Read the artifact on disk before theorizing about the code that reads it.

## A Copy of the Other Side's Registry Rots

A client that mirrors part of the server's command list (for completion, offline help, anything usable before the first connection) owns a duplicate of a source of truth it cannot see. The duplicate drifts without either test suite noticing, since each side is self-consistent on its own.

Copy as little as possible: top-level names only, since the deeper tree comes from the cache the server fills. Then pin what you do copy with a test that resolves every entry against the real registry.

**Case (September 2026):** the client's fallback list still named the pre-ADR-036 `config:*` and `addons:*` spellings a release after the colon syntax was removed. A bad reformat had also flattened `"addons create"` into a bare `"create"` and `"destroy"`. Shell completion offered those to anyone whose cache was missing. The list is now the client's own commands plus the server's top-level names, with a test that fails when a top-level command is added or renamed.

## Send the Structure, Don't Scrape the Prose

When one side of a boundary knows something the other needs, it should send it as data. A client that recovers structure by regex over the peer's error message is coupled to that sentence's wording and needs another regex for every new site of the same kind.

The server knows the typed token and the candidate set that was valid where the lookup failed; it is the party holding both. Carry them on the error (`{kind, typed, candidates, hint}`) and let the client, which knows its own dialect (`--context`, `--app`), render one phrasing per kind.

**Case (September 2026):** `hop3 cataloig` produced a suggestion only if a locally cached command list happened to exist, because the client was pulling the typed token out of `"Command 'x' not found"` with a regex and matching it against that cache. With the payload on the error, the suggestion arrives from the side that had the answer all along, leaving the cache to what it is good for: working offline.

Keep the scraping path while old servers exist. A CLI on a laptop meets whatever server the operator has deployed.

## Secrets: the Leak Is argv, and the Echo

A value passed as `KEY=VALUE` is in the shell history, in `ps` for the length of the call, and in whatever the receiving side logs. So the fix belongs in the client, before the value is ever a command-line token: a value source per key (`KEY=-` for stdin, `KEY=@<path>` for a file) and a hidden prompt for a bare key. The marker sits on the key itself so that several keys in one call stay unambiguous.

Then audit the write path. A redactor is usually added for the *display* commands, and forgotten on the *mutation* that accepts the secret in the first place.

**Case (September 2026):** `redact_sensitive_value` had been guarding `env show`, `env live` and `app info` since March, while `env set` printed `Set KEY=<value>` and, on an overwrite, `(was: <the previous secret>)`. The same audit found the heuristic blind to the credential in the sample that prompted it: a Sentry DSN carries its key as colon-less userinfo (`https://<key>@host`), which matched neither the name patterns nor a URL rule written for `user:password@`.

A redactor covers the paths you pointed it at. Enumerate the paths that print the value, and test with the shape of secret that actually showed up in a real history.

## Validate Before You Confirm

A destructive command checks its arguments before it asks anything. `hop3 app destroy` with no resolvable app used to ask "Are you sure?", take a "yes" and then fail for want of a name. The September 2026 variant was worse: `hop3 app destroy ac-sciences-2` prompted "Type 'ac-sciences' to confirm", because the app was resolved from the ambient context before the stray positional was rejected. The server then rejected the positional. The order is parse, validate, confirm, execute. The September case ran the third step before the second.

## Global Flags Stop at the Program

The flag parser scanned the whole argv for global flags, so inside `hop3 run --app x python -c "..."` it took `-c` as `--context`, stripped it with its value, and failed on an unknown context. For `run` and `app run`, global-flag parsing stops at the program, and everything after it passes through verbatim. `run`'s own `--input` is still recognized before the program. A POSIX `--` ends flag parsing for every command.

## One Settings Object Behind Every ssh

The CLI spawns ssh in four places: the RPC tunnel, `hop3 tunnel`, `hop3 app shell`, and the `login --ssh` bootstrap (a fifth caller lived in another package; see [`development-process.md`](./development-process.md)). Each read the key and port from the config its own way. The bootstrap ran a bare `ssh user@host`, so a server on a non-standard SSH port answered through the tunnel while the login that sets that tunnel up could not reach it. The fix introduced one `SshSettings` read once from the config (`ssh_key`, `ssh_port`, `ssh_options`), one `ssh_base_argv` every call site starts from, and a port accepted in the target (`root@host:2222`). A new `ssh_options` setting carries what an operator needs (`ProxyJump`, a private known_hosts). Every call site now starts from that object.

## Escape User Content Before a Markup Renderer

Log lines containing brackets (`[database]`, `[2026-02-27]`) were parsed as Rich markup and garbled the output. Anything that came from outside (log text, filenames, app output) is escaped at the boundary before it meets a formatting library.

## Two Parsers Read One argv

The client parses argv before the server sees it. It keeps its own flags (`--app`, `--force`, `--dry-run`, `-d`, `-q`, `-v`), expands aliases, and hands `--app` back only to commands in its app-scope table. A server command's help and argument spec say nothing about that first pass, so the two drifted on every axis at once. On 2026-09-25 the list was: `addon list`, `backup list`, `addon promote`, `app create` and `cert renew` documented `--app` the client refused; `ps scale` matched the table as `ps`, so `--app` was injected into the middle of the command; `cert renew --force` became a confirmation skip; `system cleanup --dry-run` pruned for real; `system info -v` and `system status -q` never saw their flag; and `catalog install -d <host>` turned on debug output. Two commands never ran at all: `addon status` read a key its spec never declared, and `nix eject` inherited a namespace's `call`, so it printed help while its tests, which called `run`, passed. The guides and tutorials had drifted the same way: `addon attach <app> <addon>`, `app logs --tail`, `backup list <app>`.

Each fix is small; the lesson is the missing link. `test_app_scope_matches_server.py` now reads both sides. Every flag a server command reads must pass through the client's parser intact. Every command that reads `--app` must be in the client's table. Every `hop3 …` line in a command's help, and in the docs' code blocks, must reach a command that accepts it. A server command whose argument name collides with a client flag renames it (`--force-renewal`) or reads what the client forwards (`get_verbosity()`, `json_output`).

The usage text had the same flaw inside one side: each command wrote its usage twice, in the docstring and in a `return [text("Usage: …")]` that exited 0 (`export > dump.sql` with no name wrote the usage into the dump). `Command.usage_error()` raises the docstring's own `Usage:` line, so a missing argument fails with exit 2 and the text cannot drift from `hop3 help`.
