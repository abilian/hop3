# ADR 042: CLI Context Model — Servers and Project Contexts

**Status**: Accepted
**Type**: Feature (breaking)
**Created**: 2026-05-30
**Related-ADRs**: 036 (supersedes D7 + D8), 018, 025, 047 (invocation-context transport)
**Supersedes**: ADR 036 §D7 (app resolution chain), §D8 (sticky state: contexts and default app)

## Context

### What broke

An operator ran `hop3 deploy` inside a project directory. The system packaged the local code and overwrote an *unrelated* app, because `hop3 use <other-app>` had been run weeks earlier in a different shell, setting a context-wide sticky default that followed the operator into every directory.

Two surface mitigations address the symptom (a `--why` flag that prints the resolution and exits; preferring `[metadata].id` over the global context default), but the underlying conflation remains. The post-mortem surfaces three deeper problems:

1. **"Context" is overloaded.** It bundles {server URL, auth token, SSH access, SSL settings, default_app}. The first four describe *which server I connect to*; the last describes *what I'm doing on it*. These should not share a noun or a record.
2. **There is no first-class "this project, on this server, called this name".** The common case — one codebase deployed to dev/staging/prod, possibly across two servers — has no native shape in the configuration. Users patch around it with sticky `hop3 use` (the trap above) or per-command `--app`/`--context`.
3. **The local-checkout overlay is anaemic.** `.hop3-context` holds a single context name and nothing else — no symmetric override for an app, a domain, or anything else a developer working across branches/environments needs.

### Why now

Pre-1.0, with explicit license to make breaking changes. Carrying the conflated `context` noun into 1.0 hardens a known footgun and a known UX dead-end; one coordinated breaking change now is far cheaper than patching around the conflation indefinitely.

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

Holds *all* the fields currently on `Context` (`api_url`, `api_token`, `ssh_user`, `ssh_port`, `ssh_key`, `ssl_cert`, `verify_ssl`, `protected`). The `default_app` field is removed — its functions move to project contexts and the resolution chain.

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

Every key under `[contexts.<name>]` other than `server` is optional and inherits from the top-level sections (`[domains]`, `[env]`, `[addons]`, …) when absent. Most projects need only `server` and `app`.

#### Local overlay — `.hop3-local.toml` (gitignored)

```toml
[current]
context = "dev"             # which [contexts.*] block I'm working in right now
```

`hop3 init` writes this file with a sensible default and appends it to `.gitignore`. It replaces the `.hop3-context` one-liner, which is retired outright (see §Migration).

### Resolution chains

Three things resolve through layered chains: server, context, app. A `git remote get-url hop3-<env>` source feeds all three, so `git push hop3-prod main` and `hop3 deploy --context prod` reach the same target without duplication.

#### Server resolution

1. `--server <name>` flag
2. `$HOP3_SERVER`
3. The server named by the resolved current context (`[contexts.<current>].server`)
4. Git remote: a `hop3-<name>` remote parsing as `hop3@<host>:<app>` whose `<host>` matches a known server URL
5. Single-server fallback: if exactly one server is defined
6. Error: "no server resolves; run `hop3 server use <name>` or pass `--server`"

#### Context resolution

1. `--context <name>` flag
2. `$HOP3_CONTEXT`
3. `.hop3-local.toml [current].context` in CWD or any ancestor up to `$HOME`
4. Git remote: exactly one `hop3-<name>` remote whose `<name>` matches a declared `[contexts.<name>]`
5. If `hop3.toml` defines exactly one `[contexts.*]` block, use it
6. None — fall back to the `[metadata].id`-only path (single-app project, no deploy targets defined)

#### App resolution (extends ADR 036 §D7)

1. `--app` / `-a` flag
2. `$HOP3_APP`
3. `.hop3-app` file in CWD or any ancestor
4. `hop3.toml [cli].app` in CWD or any ancestor
5. **`hop3.toml [contexts.<current>].app`** (NEW — only when a context resolves)
6. `hop3.toml [metadata].id` in CWD or any ancestor
7. Git remote: parse the `<app>` portion of `hop3-<resolved-context>`'s URL
8. Server-level fallback: `default_app` on the resolved server's record
9. Error

Source #5 is the load-bearing addition: it makes "same codebase, deployed as `foo-dev` to one place and `foo-prod` to another" work without sticky global state. The git-remote sources are integration glue for `git push hop3-prod`; they never override an explicit declaration. Server-level `default_app` (#8) is the lowest-priority fallback and never beats a context-derived value.

#### Typed resolver surface

The resolver exposes a single typed object rather than a raw dict:

```python
@dataclass(frozen=True, slots=True)
class ResolvedContext:
    name: str            # the context name (or "" when no context resolved)
    server: str          # server alias (key into ~/.config/hop3-cli/servers.toml)
    app: str             # resolved app name
    domains: list[str]   # final hostname list (see §Merge semantics)
    env: dict[str, str]  # final env-var map (see §Merge semantics)
```

`Hop3Config.resolve_context(name) -> ResolvedContext` is the entry point. The raw-dict accessors (`contexts`, `get_context`) remain for diagnostics / `--json` / `to_dict()`. Call sites that *use* the resolved view consume `ResolvedContext`; those that *inspect* raw config consume the dicts. (A frozen dataclass matches `CLAUDE.md` §Data Structures and catches typo'd-key access at the boundary.)

#### Merge semantics

- **`server`** — required on every context; no top-level analog.
- **`app`** — replaces `[metadata].id` for the resolved context.
- **`domains`** — **full replacement.** When `[contexts.<name>].domains` is declared (any length, including `[]`), the resolver ignores top-level `[domains].list` for that context. No per-context `_policy`. Predictable replacement is easier to reason about for the load-bearing reverse-proxy input than union semantics.
- **`env`** — **merge, context-wins.** Context env layers on top of top-level `[env]`: matching keys take the context value, unmatched top-level keys are inherited. The top-level `[env]._policy` and `[env.computed]` apply to the *merged* map; per-context `_policy`/`computed` are not honored. Layered merge is what every multi-environment system does; replace would force boilerplate.

### CLI verbs

#### Servers (global; manages `~/.config/hop3-cli/servers.toml`)

| Command | Effect |
|---------|--------|
| `hop3 server list` | list configured servers + which is default (single-server case) |
| `hop3 server add <name>` | interactive flow: URL, then login |
| `hop3 server remove <name>` | requires `--force` if any reachable `hop3.toml` context references it |
| `hop3 server show <name>` | URL, masked token, protected flag, last-used, `default_app` if set |
| `hop3 server login <name>` | re-auth (token rotation, SSO, …) |
| `hop3 server use <name>` | set a global single-server default in `state.toml` |
| `hop3 server use --default-app <app>` | set `default_app` on the current server's record — the lowest-priority app-resolution fallback (#8), for one-app-per-server users who skip `[contexts]` |

#### Contexts (project-scoped; reads `hop3.toml`, writes `.hop3-local.toml`)

| Command | Effect |
|---------|--------|
| `hop3 context init` | bootstrap a starter `[contexts.*]` block in the project's `hop3.toml` and write `.hop3-local.toml` (gitignored). Run inside a project. |
| `hop3 context list` | list contexts in the nearest `hop3.toml` + which is `[current]`. Warns on duplicate `(server, app)` targets (see below). |
| `hop3 context use <name>` | write `[current].context = <name>` to `.hop3-local.toml` |
| `hop3 context show [name]` | print the resolved `ResolvedContext(server, app, domains, env)` |
| `hop3 context add <name>` | add a stub `[contexts.<name>]` block (interactive: server, app, domains) |
| `hop3 context remove <name>` | remove from `hop3.toml`; warn if it was `[current]` |

#### Existing verbs that change behavior

| Verb | Old | New |
|------|-----|-----|
| `hop3 use <app>` | sets the current context's `default_app` (global stickiness) | sets `.hop3-local.toml [current].app` (project-scoped); errors outside a project. `hop3 use --global` preserves the old server-level behavior |
| `hop3 context` (bare) | shows active context + defaults | shows active project context + resolved `(server, app, domains)` |
| `hop3 init` | creates the first global context | creates the first server in `servers.toml`; run from anywhere. Project bootstrapping is the separate `hop3 context init` — typical usage is one global `init`, then many per-project `context init` |

#### Reserved context names

`default`, `current`, `global`, `all`, `none` are rejected at schema-validation time with an actionable error, keeping them free for CLI keyword use (e.g. `hop3 context show --all`). Enforced in the context-name validator. The list is deliberately small — adding to it later is a breaking change for any project already using the name.

#### Duplicate-target warning

When `hop3 context list` (or the deploy preview) sees two contexts resolving to the same `(server, app)` pair, it warns and names both. Never a hard error — legitimate aliasing exists (`prod` and `production` for the same deploy).

### Deploy preview (the safety mechanic that motivated this design)

`hop3 deploy` becomes preview-and-confirm: it prints the plan the resolver knows atomically, then prompts.

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

- `-y` / `--yes` — skip it (CI, scripting).
- `--dry-run` — print the plan and exit (the *action plan*, vs `--why`'s *resolution trace*).
- `--force` — bypass the project-mismatch check (§D14) without disabling the prompt.

The preview is computed client-side from the resolved tuple + `hop3.toml`. A future server-side `deploy --dry-run` RPC can enrich it ("addon X already exists", domain collisions); the client-side version is enough for the safety story.

### Project-mismatch sanity check (§D14)

For destructive commands (`deploy`, `restart`, `config set`, `app destroy`): if the CLI runs in a directory whose `hop3.toml [metadata].id` does not match the resolved app *and* the resolved app came from a non-CWD source (env var, global default), the command refuses and prints:

```
Refusing to <verb>: resolved app 'otherapp' does not match
project 'myapp' in ./hop3.toml.

  - To <verb> the project you are standing in:
      hop3 <verb>  (after `hop3 context use <name>` to pick a target)
  - To <verb> the resolved app from any directory:
      hop3 <verb> --force

(resolved app came from: <source>)
```

The trailing line names the resolution source so the operator sees what caused the mismatch. This is the belt to `[metadata].id`'s suspenders: the chain already prefers the CWD project, so the guard fires only when an explicit flag or env var contradicts the CWD — exactly when "yes I mean it" is the right requirement.

The guard is specified here as a client-side check; ADR 047 carries this check's inputs (`app`, `app_source`, `cwd`, `cwd_app_id`) in the per-call invocation context, which lets the same refusal run server-side so the guarantee holds regardless of which client issued the call.

### Migration (brutally relentless)

No back-compat shims; one breaking release.

| Old | New | Migration |
|-----|-----|-----------|
| `config.toml [contexts.*]` | `servers.toml [servers.*]` | One-shot rewriter on first run: read old, write new, back up old as `config.toml.pre-042.bak`. Each `[contexts.*]` → `[servers.*]` minus `default_app`. |
| `[contexts.<name>].default_app` | none | If set, the rewriter emits a one-time stderr note pointing to `[contexts.<ctx>].app` or `hop3 server use --default-app`. |
| `.hop3-context` | `.hop3-local.toml [current].context` | Reader removed outright. Stale files have no effect; re-run `hop3 context use <name>` to write a fresh `.hop3-local.toml`. |
| `hop3 use <app>` (sticky global) | project-scoped | Behavior change. Outside a project, falls back to old global behavior with a one-line stderr note. |
| `hop3 context <verb>` (global) | project-scoped | Behavior change. For one release the old verbs print a redirect to `hop3 server` and exit nonzero — no silent routing. |
| ADR 036 §D7 / §D8 | this ADR | ADR 036 gets a Status note; body left intact for the record. |

The wrong-app scenario from §What broke becomes: `hop3.toml` declares `[contexts.prod]`, `.hop3-local.toml` declares `context = "prod"`, and `hop3 deploy` does the right thing from anywhere in the tree — and from outside it errors with "no project context resolves".

## Rejected alternatives

**Keep "context" as-is, introduce "target" for the project concept.** Less migration, additive, no verb renames. Rejected: "context" is already the wrong word for "server binding" (it clashes with the kubectl/terraform/gh meaning), and this option puts the worse name on the *more-typed* concept — users type `--context` rarely but would type `--target` constantly. A clean rename pre-1.0 is cheaper than living with awkward vocabulary.

**A single `[contexts]` table, no `[metadata].id` fallback.** Require every project to define a context. Rejected: many one-app projects have no environments; forcing a `[contexts.default]` block is paperwork. `[metadata].id` already exists and is free to reuse as the no-context default.

**Server bindings inside `hop3.toml`.** Rejected: tokens are credentials and `hop3.toml` is committed. Keeping server bindings (with creds) in `~/.config` and project context (no creds) in `hop3.toml` keeps secrets out of version control by construction.

**`.hop3-local.toml` as a `[local]` section inside `hop3.toml`.** Rejected: treating part of a committed file as gitignored leaks complexity. Two files with two purposes is a well-understood pattern (`.env` / `.env.local`).
