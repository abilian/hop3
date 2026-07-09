# Lessons Learned: CLI Ergonomics & Surface Evolution

**Updated**: 2026-06-17 - first cut, from the ADR 036 consistency pass.

How to evolve the CLI command surface (rename, de-duplicate, deprecate) without breaking users or lying to them. Context: [ADR 036](../adrs/036-cli-ergonomics.md).

## Rename Behind an Alias - Never Break the Old Spelling

A rename changes the *canonical* name; it must not break what users already type. Change the command's canonical name and register the old name as an alias to the same handler. The dispatch table maps both; the help catalog advertises only the canonical one.

```python
class CreateAppCmd(Command):
    name = ("app", "create")            # new canonical
    aliases = [("app", "launch")]       # old spelling still dispatches
```

Test both directions: the new canonical resolves, and every old alias resolves to the *same* handler.

## Deprecate by Hiding, Not Deleting

When a command is superseded by a flag or by another command, don't delete it - mark it `hidden`. Hidden commands are excluded from the help catalog (the surface stays clean) but remain dispatchable (scripts and muscle memory keep working).

- `app build-logs` → folded into `app logs --build`; `BuildLogsCmd` kept `hidden = True`.
- `auth register` → an admin-gated subset of `user add`; deleted the class, kept `("auth", "register")` as an alias of `user add`.

The catalog the client fetches filters `hidden`, but dispatch keeps it — test both invariants: hidden commands don't appear in the catalog, yet still resolve when invoked.

## A Rename Isn't Finished Until the Platform Stops Teaching the Old Name

Dispatch resolving and tests passing is *not* "done". Every place the platform prints a command name is part of the surface: failure diagnostics, troubleshooting hints, a command's own `--help`/usage text. If those still show the old spelling, you've taught users the deprecated form.

**Case (June 2026):** after renaming `app launch`→`create`, `domains`→`domain`, `backup info`→`show`, and `app build-logs`→`app logs --build`, dispatch resolved both names and the suite was green - but ~10 user-facing messages still printed the old spelling, including the deployer's hint on *every* failed build (`run hop3 app build-logs`).

The verification that caught it:

1. Rebuild the real dispatch table and assert every new canonical *and* every old alias resolves to the expected handler; assert each hidden command is absent from the catalog but present in dispatch.
2. `grep` every user-facing string (diagnostics, hints, usage, `--help`) for the old spellings - the command definition is not the only place names appear.

Verify the *messages*, not just the dispatch.

## Never Advertise a Path the User Can't Actually Take

Help text and errors must only suggest actions the caller can perform *from their current state*. A confident pointer to an impossible flow is worse than silence: it sends the user down a dead end and erodes trust in every other message.

**Case (June 2026):** the "Authentication required" (401) error told an *unauthenticated* user to `hop auth register …` - but account creation is admin-only (`user add`). An unauthenticated user can never register. The fix removed the register line, leaving only the path that works (log in with admin-provided credentials).

This is "fail loud, never lie" applied to *guidance*: don't gate a suggestion behind a permission the caller doesn't have, and prefer removing a misleading hint over rewording it.
