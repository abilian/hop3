# ADR 042: CLI Context Model — One Context, One Connection

**Status**: Accepted
**Type**: Feature
**Created**: 2026-05-30
**Updated**: 2026-06-23
**Related-ADRs**: 036, 018, 025, 047

## Context

This ADR revises its own earlier decision *in place*. The original ADR 042 split the overloaded "context" concept into two nouns — a global **server** (URL, token, SSH, SSL, protected) and a project-scoped **context** (a deploy target inside `hop3.toml`). This revision walks that split back to a single noun. ("Server" throughout this document means the remote Hop3 instance, not the retired noun.)

### Why the split existed

One footgun motivated everything. An operator ran `hop3 deploy` inside a project and overwrote an *unrelated* app, because `hop3 use <other-app>` weeks earlier had set a server-wide sticky `default_app` that followed the operator into every directory. The original ADR concluded the cure was to move app selection into project-scoped contexts so the deploy target was pinned by the checkout, not by global state.

### Why we revise it

The footgun is killed by **one rule**: *resolve the app from where you stand* — flag, env, then CWD-rooted files (`.hop3-app`, `hop3.toml`), never from any global or server-level sticky default. The original ADR adopted that rule too; the only non-CWD app sources it kept (the context-derived `[contexts.<current>].app` and the server-level `default_app`) were exactly the two that could mis-resolve. Once the app is CWD-rooted, the wrong-app scenario cannot happen — regardless of how many server nouns exist.

The split, then, bought no extra safety. It cost a second noun (`server`), a second file (`servers.toml`), a second flag (`--server/-s`), and a second verb namespace (`hop3 server`) that users had to learn alongside `hop3 context`. Worse, mid-migration it produced *two disagreeing sources of truth* on real machines. One noun plus the app-from-CWD rule is strictly simpler and exactly as safe.

This decision continues to supersede ADR 036 §D7 (app resolution) and §D8 (sticky state).

## Decision

There is exactly **one** user-facing concept for "which Hop3 server am I talking to": the **context**. A context is a named *connection* — the context *is* the server; there is no second noun.

| Concept | Lives in | Fields | Selected by |
|---------|----------|--------|-------------|
| **Context** | global CLI config (`~/.config/hop3-cli/config.toml`) | `url`, `token`, `ssh_user`, `ssh_port`, `ssh_key`, `ssl_cert`, `verify_ssl`, `protected` | `hop3 context use <name>`, `--context/-c`, `$HOP3_CONTEXT` |

It holds a token, so it is **never committed**. The **app** is a separate axis, resolved entirely from where the operator stands (see below). `hop3.toml` is unchanged for app configuration (domains, env, addons, `[metadata].id`) and carries **no** connection info and **no** `[contexts.*]` deploy-target blocks.

### File layout

| File | Scope | Holds |
|------|-------|-------|
| `~/.config/hop3-cli/config.toml` | global | all contexts (connections) + the global current-context pointer |
| `hop3.toml` | project, committed | app config only — `[metadata].id`, domains, env, addons. **No** connection info, **no** `[contexts.*]`. |
| `.hop3-local.toml` (gitignored) | per-checkout | `[current].context` — the per-tree context override |
| `.hop3-app` (gitignored) | per-checkout | the per-tree app selection written by `hop3 use` |

```toml
# ~/.config/hop3-cli/config.toml — global context (never committed; holds a token)
[contexts.prod]
url = "https://hop3.abilian.com"
token = "<jwt>"
ssh_user = "root"
ssh_port = 22
protected = true        # blocks destructive ops without --confirm/--force
verify_ssl = true
```

`servers.toml` and `state.toml`'s `current_server` pointer are removed. The connection records and the current-context pointer live in `config.toml`; one writer, one source of truth.

### Resolution chains

Two chains, not three. The separate "server" chain is gone.

#### Context (the connection)

1. `--context` / `-c`
2. `$HOP3_CONTEXT`
3. `.hop3-local.toml [current].context` — CWD or any ancestor up to `$HOME`
4. global current context (persisted in `config.toml`)
5. single-context fallback: exactly one context exists
6. error: *"no context; run `hop3 context use <name>` or pass `--context`"*

#### App (always from where you stand)

1. `--app` / `-a`
2. `$HOP3_APP`
3. `.hop3-app` — CWD or any ancestor
4. `hop3.toml [cli].app` — CWD or any ancestor
5. `hop3.toml [metadata].id` — CWD or any ancestor
6. error

No context-derived app. No server-level `default_app` fallback. This drops the original ADR's two non-CWD app sources — the context-derived `[contexts.<current>].app` and the server-level `default_app` — which were the only sources that could ever produce the wrong-app footgun.

The committed `hop3.toml [cli].app` pins the app in version control; `hop3 use <app>` writes the gitignored per-tree `.hop3-app` override, which the App chain reads at step 3 and which therefore wins over the committed `[cli].app`. The two coexist deliberately: `[cli].app` is the shared default in the repo, `.hop3-app` is the local operator's per-checkout choice.

**Git-remote-driven resolution is dropped.** The original wove `hop3-<env>` git remotes into all three chains so that `git push hop3-prod` and `hop3 deploy --context prod` resolved to the same target. That coupling existed to serve the project-scoped contexts it fed, and goes with them. Git push-to-deploy survives as a deploy *mechanism*; what is removed is inferring a *context* or *app* from a remote's name. Out of scope for this revision — it can return alongside a future `[environments]` feature (see Rejected alternatives).

### CLI verbs

A single `hop3 context` namespace manages connections.

| Command | Effect |
|---------|--------|
| `hop3 context list` | list configured contexts + which is current |
| `hop3 context show [name]` | URL, masked token, SSH/SSL settings, protected flag |
| `hop3 context use <name>` | set the global current context |
| `hop3 context add <name> --url <url> [--token ..] [--ssh-user ..] [--protected]` | register a context |
| `hop3 context remove <name>` | delete a context |
| `hop3 context rename <old> <new>` | rename a context |
| `hop3 context login <name>` | (re-)authenticate (token rotation, SSO, …) |
| `hop3 init` | bootstrap the **first** context over SSH (role unchanged) |

App selection stays project-scoped and never global-sticky:

| Command / flag | Effect |
|----------------|--------|
| `--app` / `-a` | pick an app for one command |
| `hop3 use <app>` | write the gitignored `.hop3-app` in the project root (the file the App chain reads at step 3); errors outside a project |

**Removed:** the entire `hop3 server` verb namespace and the `--server` / `-s` flag (with `$HOP3_SERVER`).

#### Obsoleted commands

- `hop3 server use --default-app` — obsolete; `default_app` is gone.
- The duplicate-target warning (`hop3 context list` / deploy preview warning on a duplicate `(server, app)` pair) — obsolete; with one noun there is no `(server, app)` pair to collide.
- `hop3 context init` (per-project bootstrap, distinct from global `hop3 init`) — folded into `hop3 init`; there is no project-scoped context to bootstrap.

#### Reserved names

`current`, `all`, `none` stay reserved for CLI keyword use (e.g. `hop3 context show --all`) and are rejected by the name validator. Two names the original reserved are now **un-reserved**: `default` (sensible and already in use) and `global` (the `--global` flag and `hop3 server use` that motivated reserving it are gone). Un-reserving these requires removing them from `_RESERVED_CONTEXT_NAMES` in **both** `packages/hop3-cli/src/hop3_cli/core/context_names.py` and `packages/hop3-server/src/hop3/project/schema.py` (the two validators are deliberately kept in sync), and updating the drift test that pins the two sets equal — flipping only the CLI side would break the drift test and let a name through that the server still rejects at deploy time.

### Deploy preview & project-mismatch guard

Both are kept. `hop3 deploy` stays preview-and-confirm. The deploy preview now shows a `Context:` line and no `Server:` line (`deploy_preview.py` drops the `Server:` line and the `plan.server` field):

```
$ hop3 deploy
About to deploy:
  Source:   ./myapp (main @ a1b2c3d, dirty)
  Context:  prod
  App:      myapp
  Domains:  myapp.example.com
  Addons:   postgres (existing)
  Env vars: 2 keep-existing, 0 new

Proceed? [y/N]
```

The preview's governing flags are unchanged from the original: `-y` / `--yes` skips the prompt (CI, scripting), `--dry-run` prints the plan and exits, and `--force` bypasses the project-mismatch check without disabling the prompt.

The project-mismatch guard is **preserved unchanged** from the original's Project-mismatch sanity check — including the destructive-command set (`deploy`, `restart`, `config set`, `app destroy`) and the `--force` bypass. It fires when the resolved app comes from a non-CWD source (flag/env) and disagrees with `hop3.toml [metadata].id` in the directory. Its inputs (`app`, `app_source`, `cwd`, `cwd_app_id`) are exactly those ADR 047 carries in the per-call invocation context, so the same refusal can run server-side. The guard operates on the app-from-CWD rule, which this revision keeps intact.

Per-context merge semantics (domains full-replacement, env context-wins) and the `ResolvedContext` typed surface are moot — with no `[contexts.*]` blocks there is nothing to merge; the `Domains:` and `Env vars:` preview lines come straight from `hop3.toml`.

### Migration

One breaking release, no compat shims — the same stance the original ADR took. A one-shot rewriter runs on first launch and drains every legacy shape into `config.toml`. Because the original ADR 042 shipped only partially, three shapes coexist on real machines and the rewriter must handle all three:

| Old | New | Migration |
|-----|-----|-----------|
| legacy `config.toml [contexts.*]` (fields `api_url` / `api_token`) | `config.toml [contexts.*]` (fields `url` / `token`) | Rename `api_url` → `url`, `api_token` → `token`. A machine on the legacy CLI may have *only* this shape (no `servers.toml`), so the rewriter reads it directly. Back up as `config.toml.pre-042r.bak`. Reuses/extends `migrate_legacy_records`, which already performs the `api_url`→`url` / `api_token`→`token` normalization. |
| `servers.toml [servers.*]` (fields `url` / `token`) | `config.toml [contexts.*]` | Each `[servers.*]` → a context, **dropping** `default_app`. If a same-name/same-URL context already exists, **merge** (prefer the record that has a token) — never duplicate. Back up as `servers.toml.pre-042r.bak`, then delete `servers.toml`. |
| current-pointer (today in *both* `state.toml current_server` and legacy `config.toml current_context`) | `config.toml` global current-context pointer | Consolidate into the single pointer. The three-source merge in `_known_server_records` is deleted. Back up `state.toml` as `state.toml.pre-042r.bak`, then remove `current_server`. |
| `hop3 server <verb>`, `--server` / `-s`, `$HOP3_SERVER` | `hop3 context <verb>`, `--context` / `-c` | Removed. For one release the old invocations print a one-line redirect to `hop3 context` and exit nonzero — no silent routing. |
| `.hop3-context` | `.hop3-local.toml [current].context` | `.hop3-context` retired; `.hop3-local.toml` kept, now selecting a *connection*. |

`hop3 context login` is **new** to the context namespace and must be ported from `server_cmd.py:server_login`; `hop3 context rename` (currently context-only) is retained. The two handlers merge into one `hop3 context` namespace.

`default_app` is simply discarded by the rewriter (app is CWD-rooted now), so the original's "one-time stderr note" affordance for guiding users to a moved field is intentionally dropped — there is nowhere to guide to.

The code-deletion inventory for removing the two non-CWD app sources is deferred to an implementation ticket but is concretely: `resolve_app`'s `config` parameter and the `_known_server_records` call (`resolution.py`), the `AppSource.SERVER_DEFAULT` and `AppSource.CONTEXT_APP` enum members and their entries in `_CWD_ROOTED_APP_SOURCES`, `_extract_app_keys`'s context handling, and the `resolved_context` param threaded through `resolve_app` / `_resolve_from_hop3_toml`.

## Rejected alternatives

This revision supersedes the four rejected alternatives the original ADR weighed; two are re-carried below (with the noun collapse folded in), and the original's "context vs target naming" alternative is mooted by this wholesale noun re-decision.

**Keep the server/context split (the original ADR 042).** Two nouns, two files, two flags, two verb namespaces. Rejected: the split's sole justification was the wrong-app footgun, which the app-from-CWD rule kills on its own (see §Context). The extra noun bought no safety, doubled the surface users had to learn, and — mid-migration — produced two disagreeing sources of truth on real machines. We are pre-1.0 with license to make the breaking change; collapsing now is cheaper than carrying the conflated surface into 1.0.

**Per-repo multi-environment via `hop3.toml [contexts.*]`.** Deploy one codebase as `foo-dev`/`foo-prod` from committed deploy-target blocks. Rejected as YAGNI: it reintroduces the project-scoped app override (the `[contexts.<current>].app` source we just dropped) and a committed file that points at named connections. Multi-environment-per-repo is out of scope; if the need is ever genuinely real it returns as an explicit, separate `[environments]` feature, decoupled from the connection noun — never as a second core noun.

**`.hop3-local.toml` as a `[local]` section inside `hop3.toml`.** Rejected, unchanged from the original: `.hop3-local.toml` survives as a separate gitignored file. Folding it into the committed `hop3.toml` would put a per-checkout connection pointer into version control; keeping it separate and gitignored keeps per-tree state out of commits by construction.

**Server bindings inside `hop3.toml`.** Rejected, unchanged from the original: tokens are credentials and `hop3.toml` is committed. Keeping connections in `~/.config` and app config in `hop3.toml` keeps secrets out of version control by construction.

## Consequences

### Positive

- One noun, one flag (`--context`), one verb namespace, one global file — versus two of each in the split.
- One source of truth for connections; no merge of legacy/early/canonical shapes, no mid-migration disagreement.
- The wrong-app footgun stays closed via the app-from-CWD rule alone.
- `hop3.toml` is purely app config — no credentials, no connection drift between commits and `~/.config`.

### Negative

- Breaking change: `hop3 server`, `--server`, `$HOP3_SERVER`, and `servers.toml` are gone; scripts and muscle memory must move to `hop3 context`. One redirect release softens the landing.
- No built-in "same codebase, different app per environment". Operators who relied on per-context `app` override use `--app`/`$HOP3_APP` or `.hop3-app`, or wait for a future explicit `[environments]` feature (see Rejected alternatives).
- Migration deletes `servers.toml` after rewriting; the one-shot rewriter must be correct on first run (a `.pre-042r.bak` backup is taken before any deletion).