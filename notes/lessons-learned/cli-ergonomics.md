# Lessons Learned: CLI Ergonomics & Surface Evolution

**Updated**: 2026-09-01 - added the September round (a corrupt cache, a hand-copied registry, scraping the peer's prose, and secrets on the command line), from measuring a maintainer's shell history against the shipped CLI.

How to evolve the CLI command surface (rename, de-duplicate, deprecate) without breaking users. The design decisions behind it are in [ADR 036](../adrs/036-cli-ergonomics.md).

## Rename Behind an Alias - Never Break the Old Spelling

A rename changes the *canonical* name; it must not break what users already type. Change the command's canonical name and register the old name as an alias to the same handler. The dispatch table maps both; the help catalog advertises only the canonical one.

```python
class CreateAppCmd(Command):
    name = ("app", "create")            # new canonical
    aliases = [("app", "launch")]       # old spelling still dispatches
```

Test both directions: the new canonical resolves, and every old alias resolves to the *same* handler.

## Deprecate by Hiding, Not Deleting

When a command is superseded by a flag or by another command, mark it `hidden`. Hidden commands are excluded from the help catalog (the surface stays clean) but remain dispatchable (scripts and muscle memory keep working).

- `app build-logs` → folded into `app logs --build`; `BuildLogsCmd` kept `hidden = True`.
- `auth register` → an admin-gated subset of `user add`; deleted the class, kept `("auth", "register")` as an alias of `user add`.

The catalog the client fetches filters `hidden`, but dispatch keeps it: test both invariants. Hidden commands don't appear in the catalog, yet still resolve when invoked.

## A Rename Isn't Finished Until the Platform Stops Teaching the Old Name

Every place the platform prints a command name is part of the surface: failure diagnostics, troubleshooting hints, a command's own `--help`/usage text. When those still show the old spelling, users learn the deprecated form. A rename completes only when the platform's own output teaches the new name.

**Case (June 2026):** after renaming `app launch`→`create`, `domains`→`domain`, `backup info`→`show`, and `app build-logs`→`app logs --build`, dispatch resolved both names and the suite was green - but ~10 user-facing messages still printed the old spelling, including the deployer's hint on *every* failed build (`run hop3 app build-logs`).

The verification that caught it:

1. Rebuild the real dispatch table and assert every new canonical *and* every old alias resolves to the expected handler; assert each hidden command is absent from the catalog but present in dispatch.
2. `grep` every user-facing string (diagnostics, hints, usage, `--help`) for the old spellings - the command definition is not the only place names appear.

Verify the messages alongside the dispatch.

## Never Advertise a Path the User Can't Actually Take

Help text and errors must only suggest actions the caller can perform *from their current state*. A confident pointer to an impossible flow is worse than silence: it sends the user down a dead end and erodes trust in every other message.

**Case (June 2026):** the "Authentication required" (401) error told an *unauthenticated* user to `hop auth register …` - but account creation is admin-only (`user add`). An unauthenticated user can never register. The fix removed the register line, leaving only the path that works (log in with admin-provided credentials).

This is "fail loud, never lie" applied to *guidance*: suggest only actions the caller can perform, and remove misleading hints.

## A Client-Side Cache Is a Feature's Weakest Link

Suggestions, completion and offline help all read a cache the client writes on the user's own machine. Three ways that cache stops working, all of which present as "the feature does nothing":

- **It was written in place.** An interrupted write leaves a truncated or NUL-padded file, and nothing downstream can tell that from content. Write beside the target and rename over it, so a reader sees either the old file or the new one.
- **Nothing refreshes it.** A cache filled only by an explicit `--refresh` subcommand holds, for most users, whatever it held the day they installed the CLI. Hang the refresh on an event that already happens: a successful login.
- **A damaged file reads as content.** Parse on read and keep only well-formed names, so a corrupt cache degrades to an absent one, which every caller already handles.

**Case (September 2026):** a maintainer's shell history showed five command typos and no evidence of a suggestion. The candidate explanations queued up plausibly - thin coverage, a cache refreshed only by hand, suggestions reconstructed from error prose - and all three were real. None was the immediate cause. `~/.cache/hop3/commands.txt` on that machine held four NUL bytes, dated the same minute as an empty `apps.txt`: since that July write, the suggestion path had been reading garbage and returning nothing.

Read the artifact on disk before theorizing about the code that reads it. A feature nobody sees working deserves a `cat` of its inputs first.

## A Copy of the Other Side's Registry Rots

A client that mirrors part of the server's command list - for completion, offline help, anything usable before the first connection - owns a duplicate of a source of truth it cannot see. It will drift, and nothing in either test suite notices, because each side is self-consistent.

Two defences: copy as little as possible (top-level names; the deeper tree comes from the cache the server fills), and pin what you do copy with a test that resolves every entry against the real registry.

**Case (September 2026):** the client's fallback list still named the pre-ADR-036 `config:*` and `addons:*` spellings a release after the colon syntax was removed, and a bad reformat had flattened `"addons create"` into a bare `"create"` and `"destroy"`. Shell completion offered those to anyone whose cache was missing. The list is now the client's own commands plus the server's top-level names, with a test that fails when a top-level command is added or renamed.

## Send the Structure, Don't Scrape the Prose

When one side of a boundary knows something the other needs, it should send it as data. A client that recovers structure by regex over the peer's error message is coupled to that sentence's wording, and every new site of the same kind costs another regex.

The server knows the token the user typed and the candidate set that was valid where the lookup failed - it is the party holding both. Carry them on the error (`{kind, typed, candidates, hint}`) and let the client render one phrasing per kind. Rendering stays on the client, where the user's own dialect (`--context`, `--app`) is known.

**Case (September 2026):** `hop3 cataloig` produced a suggestion only if a locally cached command list happened to exist, because the client was pulling the typed token out of `"Command 'x' not found"` with a regex and matching it against that cache. With the payload on the error, the suggestion arrives from the side that had the answer all along, and the cache drops back to what it is good for: working offline.

Keep the scraping path while old servers exist. A CLI on a laptop meets whatever server the operator has deployed, and that skew is not a bug to design away.

## Secrets: the Leak Is argv, and the Echo

A value passed as `KEY=VALUE` is in the shell history, in `ps` for the length of the call, and in whatever the receiving side logs. So the fix belongs in the client, before the value is ever a command-line token: a value source per key (`KEY=-` for stdin, `KEY=@<path>` for a file) and a hidden prompt for a bare key. Put the marker on the key rather than on a separate flag, and several keys in one call stay unambiguous.

Then audit the write path. A redactor is usually added for the *display* commands and forgotten on the *mutation* that accepts the secret in the first place.

**Case (September 2026):** `redact_sensitive_value` had been guarding `env show`, `env live` and `app info` since March, while `env set` printed `Set KEY=<value>` - and, on an overwrite, `(was: <the previous secret>)`. The same audit found the heuristic blind to the credential in the sample that prompted it: a Sentry DSN carries its key as colon-less userinfo (`https://<key>@host`), which matched neither the name patterns nor a URL rule written for `user:password@`.

A redactor covers the paths you pointed it at. Enumerate the paths that print the value, and test with the shape of secret that actually showed up in a real history.
