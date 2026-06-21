# ADR 047: CLI Invocation Context — transmit the resolved app and environment with every call

**Status**: Draft
**Type**: Feature (breaking — one coordinated CLI+server release)
**Created**: 2026-06-04
**Related-ADRs**: 036 (§D7 implicit app resolution), 042 (resolution chains, project contexts), 039 (plugin command manifest — future)

This decision supersedes the client-side app-scoped injection mechanism (`hop3_cli/core/app_scope.py`), a stopgap retired by the design below.

## Context

### The stopgap and why it drifts

The CLI must decide *before* the RPC round-trip whether a command operates on a single app, so it can resolve an implicit app (ADR 036 §D7, ADR 042 §Resolution chains) and inject it. It makes that decision from a hardcoded `set[tuple[str, ...]]` in `core/app_scope.py`, and on a match injects the resolved app as the first positional argument. The module is a stopgap pending ADR 039.

The drift it causes is a recurring class of bug: the hardcoded set falls out of sync with the server's command registry, so a renamed or added command silently stops resolving its implicit app. A representative case is `hop3 app status` demanding an explicit `<app_name>` while its siblings (`app ping`, `app logs`, …) resolve one, because the set still lists the renamed `app show` and is missing `app status`.

The set is a hand-maintained copy of a property that actually lives server-side (each `Command` either needs an app or doesn't). So it drifts silently whenever a command is renamed or added, and the failure is quiet: the command still runs, it just stops resolving the implicit app and falls back to "Usage: … `<app_name>`". The same disease appears in two sibling hardcoded sets — `commands/destructive.py::DESTRUCTIVE_COMMANDS` and `main.py::_MISMATCH_GUARDED_PREFIXES` — and the whole approach structurally cannot cover plugin commands (ADR 039), which the CLI has never heard of.

The constraint that makes "just ask the server per command" a non-starter is real: app resolution happens before any round-trip, must work offline (`--why`, error messages), must not add latency to every call, and must work before authentication (`auth login` cannot query a gated endpoint to learn it is not app-scoped).

### The reframing

The drift comes from the CLI needing to know, *per command*, whether to inject the app. Invert it: the CLI always resolves the **ambient app** (and the rest of the resolved environment) and ships it as a side-channel **invocation context** on every call. Each server command consumes `context.app` only if it wants one. The CLI no longer needs to know which commands are app-scoped — that knowledge stays entirely server-side, where it belongs — and the wire channel already exists.

### The wire channel already exists

The `cli` RPC already carries a side dict (`extra_args`) alongside the positional args: `get_extra_args` (CLI) populates `repository`, `env_vars`, `streaming`, `verbosity`; the server's `call(command_name, args, extra_args)` already treats some keys as **context, not command kwargs** — it pops `verbosity` ("extracted as context") and injects `_token`. The invocation context is the same pattern, generalized into one reserved sub-structure.

## Decision

Add a single **invocation context** object, resolved client-side once per command and transmitted with every CLI→server call. The server treats it as ambient context (never a raw command kwarg) and fills a command's `app` parameter from it on demand. The client-side app-scoped set is retired from its injection role.

### The context object

A JSON object under a reserved key in `extra_args` (proposed: `_context`, mirroring `_token`):

```jsonc
{
  "_context": {
    "app":        "ac-sciences",          // resolved ambient app, or null
    "app_source": "hop3.toml [metadata].id at /…/ac-sciences",  // for --why and §D14
    "server":     "prod",                 // resolved server name (ADR 042), or null
    "context":    "prod",                 // resolved project context name, or null
    "cwd":        "/Users/…/ac-sciences", // operator's working directory
    "cwd_app_id": "ac-sciences",          // [metadata].id at/above cwd (for §D14), or null
    "cli_version": "0.6.0"
  }
}
```

The object is **open for extension** ("may be useful for other things"): future fields (locale, output width, dry-run intent, trace id) ride here without a protocol change. Unknown fields are ignored by older code that doesn't read them — but see *Versioning* on the reserved-key requirement.

Values are still produced by ADR 042's resolution chains; nothing about *how* the app/server/context resolve changes. ADR 042 stays authoritative for the resolution model (servers, project contexts, the resolution order); this ADR is authoritative only for *how* the resolved values travel to the server and are consumed there. What changes is that resolution is **always performed and always transmitted**, rather than gated on a hardcoded app-scoped check and injected positionally.

### Server-side consumption

The RPC dispatch pops `_context` (exactly as it pops `verbosity`/`_token` today — it never reaches `command.call(**kwargs)`). Then, for the command being dispatched:

- If the command's `call`/`run` signature declares an `app` (or `app_name`) parameter **and** no app was supplied positionally, fill it from `_context.app`.
- An explicit positional/flag app always wins over the ambient context.
- A command with no app parameter ignores `_context.app` entirely — so a command that is not app-scoped can never accidentally pick up the ambient app.

The server already introspects command signatures for an `app` parameter (`server/cli/cli.py` does this for the argparse CLI: *"add the app argument if the command has an App parameter"*). That same introspection becomes the single source of truth for app-scoped-ness, consumed by the RPC path.

### What this retires

`core/app_scope.py`'s injection role disappears: the CLI stops maintaining a set to decide *whether* to inject, because it always resolves and transmits. A command that needs an app and didn't get one (no positional, empty `_context.app`) errors server-side with the same structured "no app resolved — here's how to fix" message (ADR 036 §D10), which can be sourced from `_context.app_source`'s trace.

Whether the **destructive-confirmation** set (`DESTRUCTIVE_COMMANDS`) and the **§D14 mismatch guard** (`_MISMATCH_GUARDED_PREFIXES`) also fold into this model is an open question (below) — they are related (both are per-command metadata the CLI hardcodes) but distinct concerns (they gate *client-side prompting*, which still needs to happen before the round-trip).

### Bonus: the §D14 mismatch guard gets cleaner

The ADR 042 §D14 guard compares the resolved app against the CWD project's `[metadata].id`. With `_context` carrying `app`, `app_source`, `cwd`, and `cwd_app_id` together, the check has everything it needs in one structure — and could move server-side (refuse the destructive RPC) so the guarantee holds regardless of which client issued it.

## Rejected alternatives

### Keep positional injection, source app-scoped-ness from a cached server manifest

The server exposes a machine-readable command manifest (name, `app_scoped`, `destructive`, …); the CLI caches it (the `completion --refresh` cache + `cached_subcommand_index()` already do exactly this for aliases) and derives the injection decision from the cache instead of a hardcoded set. This fixes drift and covers plugins, and keeps positional injection unchanged.

Rejected as the primary mechanism because it still requires the CLI to *make a per-command decision* (and keep a cache fresh) to do something the server could just do from the context. The invocation context is simpler: the CLI ships ambient state unconditionally and the consumer decides. The manifest remains a good complement for the *client-side* concerns the context can't cover (destructive prompting, did-you-mean), and is the natural ADR 039 surface.

### Per-command round-trip ("ask the server if this needs an app")

Rejected: adds latency and a network dependency to every command, breaks offline use and `--why`, and is impossible before authentication.

### Do nothing (keep the hardcoded set, patched)

Acceptable short-term, guarded by patching as drift is found. Rejected as the end state because drift is silent and recurring, and plugins can't be covered.

## Open questions

1. **Reserved-key name and shape.** `_context` (underscore = reserved/context param, like `_token`) vs a flatter set of `_`-prefixed keys. Nested is more extensible; flat is simpler to pop.
2. **Eager vs lazy resolution.** Resolving the ambient app walks the filesystem (and possibly git) on every invocation. Cheap, but pointless for purely-local commands (`version`, `settings`) that never reach the server. Gate resolution on "command will hit the server", or accept the cost for uniformity?
3. **Do destructive-confirmation and the §D14 guard fold in here, into a manifest, or stay hardcoded?** They need *client-side* per-command knowledge (to prompt before sending), which the context alone does not provide.
4. **Server-side §D14.** Move the mismatch refusal server-side (using `_context`), or keep it client-side with richer context?
5. **Trust.** `_context` is client-supplied. The server must treat `cwd`, `cwd_app_id`, etc. as untrusted hints (fine for UX and the mismatch guard, never for authorization). Confirm no security decision keys off context fields.

## Versioning and migration

The CLI and server roll out together in one coordinated release (consistent with ADR 042's brutally-relentless stance): the CLI starts sending `_context` and the server starts popping and consuming it in lockstep.

The reserved key **must** be popped by the server dispatch before `command.call(**kwargs)`; an unknown `extra_args` key would otherwise reach the command as a kwarg and raise `TypeError`, so an old server cannot silently tolerate a new CLI's `_context`. Mixed old-server / new-client is therefore explicitly unsupported. New-server / old-client keeps working: the server fills `app` from a positional (as before) when `_context` is absent, so the dispatch must treat a missing context as "no ambient app", not an error.
