# How the CLI picks its server: a review of `hop3 context`

Input for the 0.8 discussion of `hop3 context`, which is hard to use. This note maps what the code does today: the commands, the order that decides which server a command goes to, where the state lives, where the docs disagree, and the confusion that results. It proposes no redesign beyond one line per problem.

Paths are relative to `packages/hop3-cli/src/hop3_cli/`. The findings come from reading the code (2026-10-23). Only the logout bug (5.1) was reproduced in a test and fixed; the others need a test before anyone relies on them.

## 1. What chooses the target

**Global flags** (`commands/flags.py`), stripped from argv wherever they appear: `--context`/`-c <name>`, `--app`/`-a <name>`, `--via-ssh`, `--why`. `--context=x` is not parsed. There is no `--server` flag.

**`hop3 context`** (`commands/local/context_cmd.py`). Its scope is global with `--global`/`-g`, or when no `hop3.toml` exists at or above the working directory; otherwise it is the project.

- Bare, `list`, `show [name]`: read only.
- `add <name> --server X [--bootstrap ssh://…] [--app] [--domain]… [--env K=V]…` writes `[contexts.<name>]`: into `hop3.toml` in a project, into `config.toml` globally, where it keeps only the server and bootstrap and refuses `--app`, `--domain` and `--env`.
- `remove`: either scope. Removing a global context clears `default_context` if it named it.
- `rename`: project only.
- `use <name>`: in a project, writes `.hop3-local.toml [local].context`. With `--global`, or outside a project, sets `[cli].default_context` (since b623d2c2) and warns when the environment outranks it. Inside a project, `use <global-name>` exits 2 and suggests `--global`.

**`hop3 use [app] | --clear`** (`use_cmd.py`) writes or deletes `./.hop3-app`. It selects the app, not the server.

**`hop3 login`** (`login_cmd.py`) dispatches on its arguments in this order: a `URL?token=` positional; `--browser`/`--web`; `--token [--url]`; a positional `user@host`, or `--ssh` (the old spelling); `--context N` with no target, through N's recorded bootstrap route (since b623d2c2); otherwise the password form. Every form ends in `record_server_login`, which stores the token in the credential store, writes `[contexts.<--context or "default">]` (server, bootstrap), and **always makes that context the default**. It refuses to repoint `default` at another address when no context was named.

**`hop3 init --ssh T [--context N] [--url] [--username] [--email]`** (`init_cmd.py`) creates an admin user, then calls the same `record_server_login`.

**`hop3 settings set server|token`** (`settings_cmd.py`) writes top-level `api_url`/`api_token` in `config.toml`, with a deprecation warning.

**Environment variables:**

- `HOP3_CONTEXT`: names the context.
- `HOP3_API_URL`: the server URL itself (the `env` pseudo-context).
- `HOP3_DEV_MODE`: localhost:8000, above `HOP3_API_URL`.
- `HOP3_API_TOKEN`: the token, when non-empty.
- `HOP3_APP`: the app.
- `HOP3_CONFIG_DIR`: moves the config and credential files.
- Any `HOP3_<KEY>` overrides config key `<key>` through `Config.get` (for example `HOP3_SSH_USER`).
- `HOP3_SSH_KEY`, `HOP3_SSH_PORT`, `HOP3_SSH_OPTIONS`: the SSH transport only.

## 2. The resolution order, as implemented

**The context name** (`core/resolution.py`, `resolve_context`):

1. `--context`
2. `$HOP3_CONTEXT`
3. the nearest `.hop3-local.toml`, up to `$HOME`
4. the single `[contexts.*]` block of the nearest `hop3.toml`
5. none

**Name to server** (`main.py`, `_context_address`): the project's `hop3.toml` first, then `config.toml`.

**The active server** (`main.py`, `_wire_active_server`): an explicit `--context` must resolve, or the command exits 3, and it aborts when `HOP3_API_URL` or `HOP3_DEV_MODE` points elsewhere. Otherwise: the ambient context's server, then `default_context`'s server, then the legacy `[cli].default_server`, then the only server in the credential store when there is exactly one (`_resolve_ambient_server`).

**The connection URL** (`config.py`, `Config.get_api_url`): `HOP3_DEV_MODE`, `HOP3_API_URL`, the active server, `default_context`'s server (added 2026-10-23, see 5.1), the legacy `default_server`, the legacy `contexts[name].url`. The token (`get_api_token`) is `HOP3_API_TOKEN`, else the credential store entry for that URL.

**The app** (`core/resolution.py`): `--app`, `$HOP3_APP`, `.hop3-app`, `[cli].app`, `[contexts.<selected>].app`, `[metadata].id`. `core/project_guard.py` applies to destructive commands only. `core/alias_registry.py` holds command aliases and plays no part in targeting.

## 3. Where the state lives

- **`config.toml`** (`~/.config/hop3-cli/`, `core/paths.py`): `[contexts.<n>] server, bootstrap?`, `[cli] default_context`, `[aliases]`, preferences, and possibly dead `api_url`/`api_token` keys.
- **`credentials.toml`** (mode 0600): `[servers."<canonical address>"] token`, keyed by URL with the user kept (`core/credential_store.py`).
- **`.hop3-local.toml`** in a project: `[local] context` (the older `[current]` is still read), added to `.gitignore` automatically (`core/local_overlay.py`).
- **A project context** in `hop3.toml`: `server, bootstrap?, app?, domains.list, env`.
- A global context holds only an address and an optional bootstrap route: no token, and no user beyond what the URL carries.
- **Migrations run at every launch** (`main.py`): v1 folds `servers.toml`/`state.toml` into `config.toml [contexts]`; v2 moves tokens into the credential store; v3 renames `default_server` to a named context and drops `current_context`.

## 4. Where the docs disagree with the code

| Docs | Code |
|---|---|
| `docs/src/reference/cli.md` quick start: `export HOP3_API_URL`, then `hop3 auth login` | That variable outranks every context, and `--context` then aborts |
| `cli.md`, `cheat-sheet.md`: `--why` shows the app, context and alias trace | Only the app trace is printed, and `--why` skips the `--context` check |
| `cli.md`: the app resolution chain | Leaves out `[contexts.<selected>].app` and lists a "git remote" step that does not exist |
| `cli.md`, `cheat-sheet.md`: "sticky context (`hop3 use`)" | `use` writes `.hop3-app` for the directory |
| `cli.md` quotes the error "no context; run `hop3 context use`" | No such message exists in the CLI |
| `cli.md`: `context remove` needs `--force` when resources depend on it | There is no such check |
| `cli.md` environment-variable table | Lists only `HOP3_CONTEXT` |
| `cli.md`, `cheat-sheet.md`, `user-guide.md`, `CONTEXT_HELP` (`commands/local/help_text.py`) | Teach `--ssh`, which the login help calls the old spelling |
| `INIT_HELP`: `--context` "suggests a hop3.toml context name" | It creates a global context and makes it the default (5.3) |
| ADR 042 | The copies in `notes/adrs/` and `docs/src/developers/adrs/` differ |

## 5. Confusion, with the evidence

**5.1 Fixed: the commands the CLI runs itself could not see the default context.** `Config.get_api_url` read the legacy `default_server` and never `default_context`, the only record a login writes since the v3 migration. `main` resolves `default_context`, but only after the local commands have been dispatched. So since 0.7.4, `hop3 logout` after any login answered "Not logged in" and kept the token, and `login --token` or `--browser` without `--url` found no server. `get_api_url` now reads `default_context`; `test_logout_after_login_finds_the_server` reloads the config from disk between the login and the logout, as two processes would, and fails without the fix. The older logout test seeded the retired `set_default_server`, which is why nothing caught it.

**5.2 A selection that names nothing falls through.** When `HOP3_CONTEXT` or a `.hop3-local.toml` names a context that does not exist, or was removed, the ambient lookup returns None and the command goes to the default context's server, without a word. An explicit `--context` aborts in the same case. *Every named selection should resolve or abort.*

**5.3 `init --context N` has dead code.** The global flag parser consumes `--context` first (the comment in `login_cmd.py` says so), so `init_cmd.py`'s own `--context` handling never runs and its "declare it in hop3.toml" hint never prints. Meanwhile `record_server_login` writes a global context N and makes it the default. *Delete the dead code and correct the help.*

**5.4 Two "current context" functions disagree.** `Config.get_current_context_name` ignores `.hop3-local.toml` and the single-context fallback, yet it labels the destroy warning (`commands/destructive.py`), the output scope prefix (`main.py`) and the unauthenticated message (`ui/messages.py`). In a project pinned to `staging`, a destroy says "Acting on <staging server> (context 'default')". Bare `hop3 context` and `list` mark only the overlay, so with one declared context they print "No context selected" while commands use it. *One resolver for every display.*

**5.5 A login changes the default as a side effect.** Every login makes its context the default, `login --context staging` included. `login --context N` with no target reads only *global* bootstrap routes, so for a context declared only in the project it falls back to the password prompt. *Separate authenticating from choosing the default.*

**5.6 One word, several concepts.** "Context" names a project's deploy environment, a global named server, the `env` pseudo-context and the `default` pseudo-context. Around it, `server` is a key and `bootstrap` a route; `--url` (`login`, `init`) and `--server` (`context add`) mean the same thing; "target" is the word in prose; "alias" means command aliases. `hop3 use` selects the app and `hop3 context use` the server: three verbs for two scopes. *Name the scopes differently.*

**5.7 The environment outranks stored state without saying so.** `HOP3_API_URL` beats every ambient selection with no error, and warns only at login. `HOP3_DEV_MODE` beats `HOP3_API_URL`. `HOP3_API_TOKEN` is sent to whatever server was resolved, whichever it is.

**5.8 Error messages point at dead ends.** The "not configured" message (`ui/messages.py`) recommends `hop3 init`, which its own help says one rarely needs, and `settings set server/token`, which write keys `get_api_url` never reads outside developer mode. The same dead keys appear in `login_cmd.py` and in `settings show`. `context rename` outside a project says contexts exist only "inside a project", which the global scope contradicts. None of these messages mentions `context use --global`. *One current "next step" message.*

**5.9 Only `login` and `init` can store a token.** `context add` records an address without a credential. Until b623d2c2, only a login could set the default context.

## 6. What b623d2c2 changed (2026-10-17)

- `context use --global <name>`, and `context use` outside a project, set `default_context`.
- `login --context <name>` without a target signs in over the SSH route that context records.
- `ssh_target_from_address` moved to `core/ssh_target.py`.
- `cli.md`, the `notes/` copy of ADR 042, and the tests were updated.

## 7. Where to start

Most of section 5 comes from one gap: the CLI has no single answer to "which server will this command reach, and why". Three functions answer it (`get_api_url`, `_wire_active_server`, `get_current_context_name`), at different points in `main`, and they disagree. A single resolver, run before any command dispatches, used by every command and every message, and refusing a selection it cannot resolve, would remove 5.1, 5.2 and 5.4 and give `--why` its context trace. The renaming in 5.6 and the login side effect in 5.5 are interface decisions to take on top of it.
