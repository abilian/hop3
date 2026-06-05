# ADR 042: CLI Context Model — Servers and Project Contexts

**Status**: Accepted
**Type**: Feature (breaking)
**Created**: 2026-05-30
**Updated**: 2026-06-01
**Related-ADRs**: 036 (supersedes D7 + D8), 018, 025
**Supersedes**: ADR 036 §D7 (app resolution chain), §D8 (sticky state: contexts and default app)

## Revisions

- v0.2 (2026-06-01): Resolved nine open questions. Folded the answers into the relevant sections — `[env]` merge semantics, `domains` replace semantics, `hop3 use` becomes project-scoped, frozen `ResolvedContext` dataclass for typed accessors, deny-list for reserved context names, `hop3 server use --default-app` semantics, duplicate-target lint surface, separate `hop3 init` / `hop3 context init` verbs, git-remote promoted to a resolution source. Status moved Draft → Accepted.
- v0.1 (2026-05-30): Initial draft. Triggered by a production incident in which `hop3 deploy` from an unrelated project's directory deployed onto the wrong app because the active CLI "context" carried a sticky `default_app` that outranked every project-local source except `.hop3-app` (rare in practice) and `[cli].app` (rarely set).

## Context

### What broke

An operator ran `hop3 deploy` from inside a project directory. The system packaged the local code, sent it to the server, and overwrote an unrelated app — because `hop3 use <other-app>` had been run weeks earlier in a different shell session, setting a context-wide sticky default that followed the operator into every directory.

Two surface fixes landed immediately (a `--why` flag that exits without running the command, and a resolution-chain change that prefers `[metadata].id` over the global context default). The post-mortem then surfaced three deeper problems beneath the surface bug:

1. **"Context" is overloaded.** Today a context bundles {server URL, auth token, SSH access, SSL settings, default_app}. The first four describe *which Hop3 server I am connecting to*. The last describes *what I'm doing on that server*. These should not share a noun, and they should not be stored in the same record.
2. **There is no first-class concept of "this project, on this server, called this name".** A common real use case — same codebase, deployed to dev/staging/prod, possibly across two Hop3 servers — has no native shape in the configuration. Users patch around it with sticky `hop3 use` (the trap above) or by typing `--app` and `--context` on every command.
3. **The local-checkout overlay is anaemic.** `.hop3-context` exists today as a one-line file holding a single context name. There is no symmetric mechanism for an app override, a domain override, or anything else a developer working on multiple branches/environments of one project needs.

### Why now

We are pre-1.0 and have explicit license to make breaking changes ("brutally relentless"). Carrying the conflated `context` noun forward into 1.0 hardens a known footgun and a known UX dead-end. The cost of a single coordinated breaking change here is much smaller than the cost of patching around the conflation indefinitely.

## Decision

### Core vocabulary change

The existing "context" concept is split in two:

| New noun | Lives in | What it is | Cardinality |
|----------|----------|------------|-------------|
| **Server** | global CLI config | A Hop3 server binding: URL, auth token, SSH settings, SSL settings, protected flag | One per reachable Hop3 host |
| **Context** | project `hop3.toml` | A deploy target on a server: which server, app name, domains, env var overrides | Per project, one per deploy target (dev / staging / prod / …) |

The verb `context` keeps its place in the CLI surface, but its meaning is now project-scoped. The previously-global object (server URL + auth) is now spelled `server`.

### File layout

#### Global server registry — `~/.config/hop3-cli/servers.toml`

```toml
[servers.dev]
url = "https://hop3-dev.abilian.com"
token = "<jwt>"
ssh_user = "root"
ssh_port = 22
protected = false

[servers.prod]
url = "https://hop3.abilian.com"
token = "<jwt>"
ssh_user = "root"
ssh_port = 22
protected = true       # blocks destructive ops without --confirm/--force
verify_ssl = true
```

This file holds *all* the fields currently on `Context`: `api_url`, `api_token`, `ssh_user`, `ssh_port`, `ssh_key`, `ssl_cert`, `verify_ssl`, `protected`. The `default_app` field is removed (its functions move to project contexts and the resolution chain).

#### Project file — `hop3.toml` gains `[contexts.*]`

```toml
[metadata]
id = "myapp"                # canonical project name; default app when no context selected

[contexts.dev]
server = "dev"              # name of a server in ~/.config/hop3-cli/servers.toml
app = "myapp-dev"
domains = ["dev.myapp.example.com"]

[contexts.staging]
server = "dev"              # same server, different app
app = "myapp-staging"
domains = ["staging.myapp.example.com"]

[contexts.prod]
server = "prod"
app = "myapp"
domains = ["myapp.example.com"]

[contexts.prod.env]         # optional: env-var overrides scoped to this context
DEBUG = "false"
LOG_LEVEL = "warning"
```

Every key under `[contexts.<name>]` other than `server` is optional and inherits from top-level `hop3.toml` sections (`[domains]`, `[env]`, `[addons]`, etc.) when absent. Most projects can get away with just `server` and `app`.

#### Local overlay — `.hop3-local.toml` (gitignored)

```toml
[current]
context = "dev"             # which [contexts.*] block I'm working in right now
```

`hop3 init` writes this file with a sensible default and appends it to `.gitignore`. Replaces the existing `.hop3-context` one-liner. (The migration kills `.hop3-context` outright; see §Migration.)

### Resolution chains

Three things now resolve through layered chains: server, context, app. A `git remote get-url hop3-<env>` source feeds into all three so `git push hop3-prod main` and `hop3 deploy --context prod` reach the same target without duplication.

#### Server resolution

For commands that need to know which Hop3 host to talk to:

1. `--server <name>` flag
2. `$HOP3_SERVER` env var
3. The server named by the resolved current context (`[contexts.<current>].server`)
4. Git remote: if a `hop3-<name>` remote in CWD parses as `hop3@<host>:<app>` and `<host>` matches a known server URL, use that server
5. Single-server fallback: if `~/.config/hop3-cli/servers.toml` defines exactly one server, use it
6. Error: "no server resolves; run `hop3 server use <name>` or pass `--server`"

#### Context resolution

For commands that operate within a project context:

1. `--context <name>` flag
2. `$HOP3_CONTEXT` env var
3. `.hop3-local.toml [current].context` in CWD or any ancestor up to `$HOME`
4. Git remote: if the working tree has exactly one `hop3-<name>` remote and `<name>` matches a declared `[contexts.<name>]`, use it
5. If `hop3.toml` defines exactly one `[contexts.*]` block, use it
6. None — operations fall back to the `[metadata].id`-only path (single-app project, no deploy targets defined)

#### App resolution (extends ADR 036 §D7)

1. `--app` / `-a` flag
2. `$HOP3_APP`
3. `.hop3-app` file in CWD or any ancestor
4. `hop3.toml [cli].app` in CWD or any ancestor
5. **`hop3.toml [contexts.<current>].app`** (NEW — only when context resolves)
6. `hop3.toml [metadata].id` in CWD or any ancestor
7. Git remote: if `hop3-<resolved-context>` exists in CWD, parse the `<app>` portion of `hop3@<host>:<app>`
8. Server-level fallback: `default_app` field on the resolved server's record (for one-app-per-server users who skipped `[contexts]`)
9. Error

The new source #5 is the load-bearing addition: it's the path that makes "same codebase, deployed as `foo-dev` to one place and `foo-prod` to another" work without sticky global state. The git-remote sources (server #4, context #4, app #7) are integration glue for the common `git push hop3-prod` workflow; they never override an explicit declaration. Server-level `default_app` (source #8) is the lowest-priority fallback — it never beats a context-derived value.

#### Typed resolver surface

The Step-2 resolver exposes a single typed object rather than a raw dict:

```python
@dataclass(frozen=True, slots=True)
class ResolvedContext:
    name: str            # the context name (or "" when no context resolved)
    server: str          # server alias (key into ~/.config/hop3-cli/servers.toml)
    app: str             # resolved app name
    domains: list[str]   # final hostname list (see §Merge semantics below)
    env: dict[str, str]  # final env-var map (see §Merge semantics below)
```

`Hop3Config.resolve_context(name) -> ResolvedContext` is the resolver entry point. The raw-dict accessors (`contexts`, `get_context`) added in Step 1 remain for diagnostics / `--json` / `to_dict()` callers. Call sites that *use* the resolved view consume `ResolvedContext`; call sites that *inspect* the raw config consume the dicts.

#### Merge semantics

Two of the four fields on a context override their top-level counterparts non-trivially. The rules are:

- **`server`** — required on every context; no top-level analog.
- **`app`** — replaces `[metadata].id` for the resolved context (no merge to speak of).
- **`domains`** — **full replacement**. When `[contexts.<name>].domains` is declared (any length, including `[]`), the resolver ignores top-level `[domains].list` entirely for that context. No per-context `_policy` field; the top-level `[domains]._policy` does not apply.
- **`env`** — **merge with context-wins**. The resolver layers context env on top of the top-level `[env]`: matching keys take the context value; unmatched top-level keys are inherited. The top-level `[env]._policy` and `[env.computed]` sub-table apply to the *merged* map, not to the context layer in isolation. Per-context `_policy` and `[contexts.<name>.env.computed]` are not honored (the schema accepts `dict[str, Any]` for the value type only).

### CLI verbs

#### Servers (global; manages `~/.config/hop3-cli/servers.toml`)

| Command | Effect |
|---------|--------|
| `hop3 server list` | list configured servers + which is "default" (single-server case) |
| `hop3 server add <name>` | interactive flow: URL, then login |
| `hop3 server remove <name>` | requires `--force` if any context in any reachable `hop3.toml` references it |
| `hop3 server show <name>` | URL, masked token, protected flag, last-used timestamp, `default_app` if set |
| `hop3 server login <name>` | re-auth (token rotation, SSO, etc.) |
| `hop3 server use <name>` | sets a global single-server default in `~/.config/hop3-cli/state.toml` — equivalent of today's "current context" pointer |
| `hop3 server use --default-app <app>` | sets the `default_app` field on the *current* server's record. Lowest-priority fallback in app resolution (source #8, after all context-derived sources). For one-app-per-server users who don't declare `[contexts]`. |

#### Contexts (project-scoped; reads `hop3.toml`, writes `.hop3-local.toml`)

| Command | Effect |
|---------|--------|
| `hop3 context init` | bootstraps a starter `[contexts.*]` block in the project's `hop3.toml` and writes `.hop3-local.toml` (adding it to `.gitignore`). Run inside a project directory. |
| `hop3 context list` | list contexts defined in the nearest `hop3.toml` + which is `[current]`. Warns when two contexts resolve to the same `(server, app)` pair (see §Duplicate-target warning below). |
| `hop3 context use <name>` | writes `[current].context = <name>` to `.hop3-local.toml` (creates file + adds to `.gitignore`) |
| `hop3 context show [name]` | prints the resolved `ResolvedContext(server, app, domains, env)` for a context |
| `hop3 context add <name>` | adds a stub `[contexts.<name>]` block to `hop3.toml` (interactive: server, app, domains) |
| `hop3 context remove <name>` | removes from `hop3.toml`; warns if it was `[current]` |

#### Existing verbs that change behavior

| Verb | Old | New |
|------|-----|-----|
| `hop3 use <app>` | sets the current context's `default_app` (global stickiness) | sets `.hop3-local.toml [current].app` (project-scoped); errors when invoked outside a project. `hop3 use --global` preserves the old behavior (sets a single-server's `default_app`, useful for multi-app users on one server) |
| `hop3 context` (bare) | shows active context + defaults | shows active project context + resolved `(server, app, domains)` |
| `hop3 init` | creates the first global context | creates the first server in `~/.config/hop3-cli/servers.toml`. Run from anywhere — does not write into `hop3.toml`. For project-side bootstrapping, use `hop3 context init` inside a project directory. The two flows are deliberately separate: typical usage is one global `hop3 init`, then many per-project `hop3 context init`. |

#### Reserved context names

The following names are reserved at schema validation time and rejected with an actionable error. They are kept free for CLI keyword use (e.g., `hop3 context show --all`):

- `default`, `current`, `global`, `all`, `none`

This is enforced in `_validate_context_name` in `packages/hop3-server/src/hop3/project/schema.py`. Adding more reserved names later is a breaking change for any project already using them, so the list is deliberately small.

#### Duplicate-target warning

When `hop3 context list` (or the `hop3 deploy` preview from §Deploy preview) sees two contexts resolving to the same `(server, app)` pair, it emits a warning naming both contexts. Never a hard error — legitimate aliasing exists (`prod` and `production` pointing at the same deploy). Implementation lands with Step 5's preview surface.

### Deploy preview (the safety mechanic that motivated this design)

`hop3 deploy` becomes "destructive-ish": it prompts with a plan by default. The plan is what the new resolver knows atomically.

```
$ hop3 deploy
About to deploy:
  Source:   ./myapp (main @ a1b2c3d, dirty)
  Context:  dev
  Server:   hop3-dev.example.com  (server: dev)
  App:      myapp-dev
  Domains:  dev.myapp.example.com
  Addons:   postgres (existing)
  Env vars: 2 keep-existing, 0 new

Proceed? [y/N]
```

Three flags govern the prompt:

- `-y` / `--yes` — skip the prompt (CI, scripting). Already exists, just extended to `deploy`.
- `--dry-run` — print the plan and exit. Analogous to `--why` but shows the *action plan*, not just the *resolution trace*.
- `--force` — bypass the project-mismatch sanity check (see §D14 below) without disabling the prompt itself.

The preview data is computed client-side from the resolved (server, context, app) tuple plus `hop3.toml`. A future iteration can add a server-side `deploy --dry-run` RPC for richer information ("addon X already exists", "two existing apps share this domain"); the client-side version is sufficient for the safety story.

### Project-mismatch sanity check (§D14)

For destructive commands (`deploy`, `restart`, `config set`, `app destroy`):

If the CLI is invoked in a directory whose `hop3.toml [metadata].id` does not match the resolved app *and* the resolved app came from a non-CWD source (env var, global single-server default), the command refuses to run and prints:

```
Refusing to <verb>: resolved app 'otherapp' does not match
project 'myapp' in ./hop3.toml.

  - To <verb> the project you are standing in:
      hop3 <verb>  (after `hop3 context use <name>` to pick a target)
  - To <verb> the resolved app from any directory:
      hop3 <verb> --force

(resolved app came from: <source>)
```

The trailing diagnostic line names the resolution source (`$HOP3_APP`, `--app flag`, `server 'prod' default app`, etc.) so the operator can immediately tell what caused the mismatch. It is supplementary to the two remediation bullets, not a replacement for them.

This is the belt to `[metadata].id`'s suspenders. The resolution chain already prefers the CWD project over the global default, so this guard fires only when an explicit flag or env var contradicts the CWD. In that case, an explicit "yes I mean it" is the right requirement.

### Migration (brutally relentless)

This design accepts no back-compat shims. The migration ships as one breaking release.

| Old | New | Migration |
|-----|-----|-----------|
| `~/.config/hop3-cli/config.toml [contexts.*]` | `~/.config/hop3-cli/servers.toml [servers.*]` | One-shot rewriter on first `hop3` run after the bump: read the old file, write the new file, rename the old to `config.toml.pre-042.bak` for safety. Each `[contexts.*]` becomes `[servers.*]` minus `default_app`. |
| `[contexts.<name>].default_app` | none (gone) | If any context had `default_app` set, the rewriter emits a one-time stderr note: `"server '<name>' had default_app='<x>'. Set this per-project via hop3.toml [contexts.<ctx>].app, or use 'hop3 server use --default-app <x>' if you only use one server."` |
| `.hop3-context` | `.hop3-local.toml [current].context` | **Brutally relentless (Step 7):** the reader is removed outright. Stale `.hop3-context` files have no effect; users re-run `hop3 context use <name>` inside a project tree to write a fresh `.hop3-local.toml` (which auto-gitignores itself). |
| `hop3 use <app>` (sticky global) | `hop3 use <app>` (project-scoped) | Behavior change. If invoked outside a project, fall back to old global behavior with a one-line stderr note: `"set on server 'X' default_app. To pin per-project, run from a project directory."` |
| `hop3 context <verb>` (acted on global contexts) | `hop3 context <verb>` (acts on project contexts) | Behavior change. For one release, the old verbs print: `"'hop3 context' now manages project contexts. For server bindings, use 'hop3 server'."` and exit nonzero. No silent backwards routing. |
| ADR 036 §D7 / §D8 | this ADR §Resolution chains, §CLI verbs | ADR 036 gets a Status note: "D7/D8 superseded by ADR 042". Body left intact for historical record. |

The wrong-app scenario from §What broke becomes: `hop3.toml` declares `[contexts.prod].server = "prod"` and `app = "myapp"`; `.hop3-local.toml` declares `context = "prod"`; `hop3 deploy` does the right thing from any directory in the project tree, and from outside the tree errors with a clear "no project context resolves" message.

## Rejected alternatives

### Option B from the brainstorm — keep "context" as-is, introduce "target"

Earlier proposal: add a new noun `target` for the project-level concept, leave global "context" untouched. Less migration, additive, no rename of existing CLI verbs.

Rejected because:

1. Project experience over the past months consistently flags "context" as the wrong word for "server binding" — it confuses against the broader software meaning where a "context" is the operational mode you are working in (kubectl context, terraform context, gh context). The rename moves the term closer to the meaning operators actually expect.
2. The "two distinct things both deserving of a noun" problem doesn't go away — Option B just gives the worse name to the more-frequently-used concept. Users type `--context` rarely (servers are slow-changing) and would type `--target` constantly (every deploy). Putting the cleaner word on the more-typed concept is correct.
3. Brutal-relentless is on the table. A clean rename now is cheaper than living with an awkward vocabulary indefinitely.

### A single `[contexts]` table, no top-level `[metadata].id` fallback

Considered: drop the `[metadata].id`-as-app-default source, require every project to define at least one context.

Rejected: many small/personal-use projects have one app, one server, no environments. Forcing a `[contexts.default]` block for them is paperwork. `[metadata].id` is the existing universal field; using it as the no-context-defined default is free.

### Storing server bindings inside `hop3.toml`

Considered: let each project declare its own server URLs inline.

Rejected: tokens are credentials. Per-project token storage means git accidents (`hop3.toml` is committed). The split — server bindings (with creds) in `~/.config`, project context (no creds) in `hop3.toml` — keeps secrets out of version control by construction.

### `.hop3-local.toml` as a separate file vs. a section inside `hop3.toml`

Considered: `[local]` section inside `hop3.toml`, gitignore-suppressed via tooling.

Rejected: `hop3.toml` is committed; treating part of it as gitignored leaks complexity. Two files with two purposes (committed shared config, local override) is a well-understood pattern (`.env` / `.env.local`; `terraform.tfvars` / `*.auto.tfvars`).

## Resolved questions

All nine open questions raised during drafting are now decided. The decisions are folded into the section above; this list keeps the rationale alongside the question so future readers can trace the *why*.

1. **`hop3 init` interactive flow.** **Separate verbs.** `hop3 init` (run from anywhere) bootstraps the first server in `~/.config/hop3-cli/servers.toml`. `hop3 context init` (run inside a project) writes a starter `[contexts.*]` block. *Why:* the typical workflow is one global init followed by many per-project setups; bundling them into one verb makes the project-context case feel mandatory and the server-only case feel cluttered.
2. **Server discovery from git.** **Promoted into this ADR's chains.** Source #4 in server resolution, source #4 in context resolution, source #7 in app resolution. *Why:* `git push hop3-prod main` is the load-bearing real-world deploy pattern; the resolver should converge to the same target without re-typing.
3. **Per-context `[env]` merge semantics.** **Merge.** Context env keys override matching top-level keys; unmatched top-level keys are inherited. The schema accepts `dict[str, Any]` for parity with top-level `[env]`. Per-context `_policy` and `[env.computed]` are not honored — those remain a top-level-only concern. *Why:* every multi-environment system from `.envrc` to `terraform.tfvars` does layered merge; replace semantics force boilerplate; explicit policy sentinels are heavy for the rare case.
4. **Per-context `domains` merge semantics.** **Full replacement, no policy.** When `[contexts.<name>].domains` is declared (any length, including `[]`), the resolver ignores the top-level list. The schema keeps the bare `list[str]` shape. *Why:* domains are the load-bearing reverse-proxy input; predictable replacement is easier to reason about than union semantics; the policy machinery from top-level `[domains]` would add complexity for a use case nobody has yet demanded.
5. **Reserved context names.** **Deny-list at schema time.** `default`, `current`, `global`, `all`, `none` are rejected with an actionable error. *Why:* these collide with likely future CLI keywords (`hop3 context show --all`, `hop3 context use default`); cheapest moment to reserve is before any config uses them.
6. **`hop3 server use --default-app`.** **Stored on the server record; lowest-priority fallback in app resolution.** Lives as `default_app` on the server entry in `~/.config/hop3-cli/servers.toml`. Used as source #8 in the app-resolution chain — never beats a context-derived value. *Why:* keeps the credential file's purpose ("how to reach this server") coherent; one-app-per-server users get the ergonomic without forcing them into the `[contexts]` structure.
7. **`hop3 use <app>` semantics.** **Project-scoped by default; `--global` for the old behavior.** Writes `.hop3-local.toml [current].app` when invoked inside a project; errors otherwise. `hop3 use --global <app>` preserves the legacy server-level `default_app` setter. *Why:* the wrong-app footgun that motivated this ADR was *exactly* the global-sticky behavior; inverting the default fixes it; `--global` is a single-flag escape hatch for the rare legitimate case.
8. **Typed-object accessor surface.** **Frozen `ResolvedContext` dataclass.** A new `Hop3Config.resolve_context(name) -> ResolvedContext` accessor (Step 2). Raw-dict accessors (`contexts`, `get_context`) stay as-is for diagnostics and `to_dict()`. *Why:* matches the project's stated preference for frozen dataclasses (per `CLAUDE.md` §Data Structures); catches `ctx.get("serer")` typos at the boundary; keeps the schema/runtime split clean.
9. **Duplicate `(server, app)` linting.** **Warning surface in `hop3 context list` and `hop3 deploy` preview (Step 5).** Never a hard error. *Why:* legitimate aliasing exists (`prod` and `production` as readability aliases for the same target); hard errors would force escape hatches; warnings give signal without breaking valid configs.

## Implementation order

Each step is a separate PR. Order reflects dependencies.

1. **Schema** — `[contexts.*]` parsing in `hop3.toml`. `ContextSection` Pydantic model, reserved-name deny-list (`default`, `current`, `global`, `all`, `none`), HOST_NAME-vs-domains consistency check at the context layer, raw-dict accessors on `Hop3Config`. No runtime behavior change. **(Status: shipped in this branch.)**
2. **Resolver** — the three resolution chains (server, context, app) with all git-remote and `default_app` sources wired in. `Hop3Config.resolve_context(name) -> ResolvedContext` (frozen dataclass) and the underlying server / context resolvers in the CLI. Env merge + domains replace semantics implemented here. Tests for each chain.
3. **Local overlay** — `.hop3-local.toml` reader/writer; `hop3 context init` / `use` / `list` / `show` / `add` / `remove` verbs. The duplicate-target warning in `hop3 context list` lands here as a soft surface (reused by Step 5).
4. **Server namespace** — `hop3 server` verbs (`list` / `add` / `remove` / `show` / `login` / `use`). The rewriter for `~/.config/hop3-cli/config.toml [contexts.*]` → `~/.config/hop3-cli/servers.toml [servers.*]` ships here, plus `hop3 server use --default-app` and the new app-resolution source #8.
5. **Deploy preview** — `hop3 deploy` becomes preview-and-confirm. `-y` / `--dry-run` / `--force` flags; project-mismatch guard (the §D14 piece); duplicate-target warning surfaced in the preview.
6. **Docs and supersession** — mark ADR 036 §D7/§D8 superseded; update `docs/src/reference/cli.md`, `packages/hop3-cli/README.md`. Refresh the `hop3 use` examples to match the new project-scoped semantics. Document the env-merge / domains-replace rules.
7. **Cleanup** — remove the `.hop3-context` reader, the `--local` flag from `hop3 context use`, and every doc/help/comment that mentions the legacy file. No auto-migration (per the brutally-relentless stance — see the migration table). After this step the legacy file is fully retired.

Step 1 lands the schema without changing behavior — a green-field foundation the rest builds on. Step 5 (deploy preview / project-mismatch guard) can land independently of Steps 2–4 if we want the safety guarantee ahead of the multi-context UX; it consumes only the resolved app from Step 1's `[metadata].id` source.
