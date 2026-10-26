# ADR 042: CLI Context Model: Contexts Are Servers, Checkouts Are Bound

- **Status**: Accepted
- **Type**: Feature
- **Created**: 2026-05-30
- **Updated**: 2026-10-23
- **Related-ADRs**: [014](./014-authentication-bootstrap.md), [018](./018-cli-architecture.md), [019](./019-cli-commands.md), [025](./025-cli-user-experience.md), [031](./031-project-terminology.md), [036](./036-cli-ergonomics.md), [047](./047-cli-invocation-context.md), [061](./061-standard-roles-and-rpc-authorization.md)

> **Revised five times.** The original split deploy targets into a global *server* (connection) and a project-scoped *context*. The first revision collapsed both into one global *connection* called "context". The second made a *context* a deploy **environment** in the committed `hop3.toml`, project-only, so project-less commands grew a separate `--server` flag. The third gave a context two scopes, a global named server (`config.toml`) and a project environment (`hop3.toml`), behind one `--context` selector. The fourth required every target to have a name and separated a context's two addresses: where commands go, and where a token is minted. The fifth removes the two scopes: one word for a server connection and for a deployment of a project made `hop3 context` behave differently in each directory and the resolution chain hard to follow. A context is now only a server you can reach, global and personal. What is local is the **binding** that says which context a checkout uses, and it is never committed. `hop3.toml` describes the app and never says where it is deployed.

## Context

A real deployment story is **one codebase, many environments** (`dev`, `demo`, `prod`), each a distinct app instance, often on a different server, with its own domains and (non-secret) configuration. A developer switches between them many times a day.

The third and fourth revisions expressed this with `[contexts.<name>]` blocks in `hop3.toml`, holding a `server` address, and a same-named global context in `config.toml`. Using them showed four problems:

1. **One word, two things.** A global context is a connection: an address and a token. A project context is a deployment: which server, under which app name, with which domains. `staging` and `prod` may share a server, and one server holds many projects. Under one name, `hop3 context use` wrote one of two files depending on the directory, `add` accepted `--app` in one scope only, `rename` worked in one scope only, and three functions disagreed on which context was current.
2. **Where to deploy does not belong in the committed file.** Selecting the environment in `hop3.toml` means a commit for each switch, ten a day. Context names are each developer's own, and server addresses are infrastructure that the app does not need to know.
3. **Selection fell through silently.** A `HOP3_CONTEXT` or overlay naming a removed context sent the command to the default server, and a checkout with no selection used the global current context: the `kubectl` accident, where the context selected in another terminal an hour ago is the one a deploy reaches.
4. **Nothing marked production.** Every server was one typo away from a mutating command.

The precedents split the same way. Docker and hcloud keep one global pointer and leave per-directory selection to the shell (`DOCKER_HOST` in an `.envrc`), where nobody sees it. Vercel, Netlify and Supabase `link` a checkout to a project in a gitignored directory. Terraform records the selected workspace in `.terraform/environment`, uncommitted. Kamal and Fly name the destination on each command. Hop3 takes the per-checkout, uncommitted binding, and makes it visible on every command.

`hop3.toml` holds no secrets, and that does not change: every secret lives server-side, per app instance, set by the platform, an addon or `hop3 env set`.

## Decision

Four rules.

**A. `hop3.toml` is the app.** The CLI reads the nearest `hop3.toml` at or above the working directory implicitly, as `uv` reads `pyproject.toml`. It never records where the app is deployed: no server address, no selected environment.

**B. Where a command goes is decided, in order, by:**

1. `--context` / `-c <name>`;
2. `$HOP3_CONTEXT` (an `.envrc` or `.env` that sets it is a visible, per-directory choice), or the context named `env` that `HOP3_API_URL` / `HOP3_DEV_MODE` declare;
3. inside a project, the checkout's **binding**;
4. outside a project, the **global current context**.

Each named selection resolves or aborts. A name that matches no context stops the command, whichever step supplied it.

**C. Every command that reaches a server says where it goes and why**, in one line on stderr before it acts: the context, its address, and the step of B that chose it ("bound in this checkout", "from `HOP3_CONTEXT`"). `--why` expands it into the full trace.

**D. A protected server is never reached by accident.** For a command that changes something (any command above the `viewer` role, [ADR 061](./061-standard-roles-and-rpc-authorization.md)), a protected server is selected only by step 1 or 2 of B, never by a binding or the global current context, and the command asks for the app's name, typed, after printing the server and the app. `--yes` skips the prompt only together with `-c` or `HOP3_CONTEXT`, so a CI job names its target in its own script. Read-only commands are unaffected.

### Contexts: servers you can reach

A context is global and personal, exactly as in Docker and hcloud. It lives only in `config.toml`:

| Field | Meaning | Example |
|-------|---------|---------|
| `server` | the address every command connects to (the only required field) | `https://hop3.example.com` |
| `bootstrap` | `ssh://` route used **only** to mint a token | `ssh://root@hop3.example.com` |

A context never holds an app, domains or environment. Its token lives in the credential store, keyed by the canonical server address; a connection is plumbing, never a managed object (there is no `hop3 server` noun).

Every target has a name. A login given no `--context` records the reserved name `default`; pointing that name at a *different* address without asking for it is refused, because "I replaced my server" and "I have two servers now" are indistinguishable from here. `env` is reserved for the target the environment declares.

A login creates or updates a context. It makes it the global current context only when none is current, and otherwise prints the `hop3 context use` that would. Authenticating never changes where commands go.

### The binding: which context this checkout uses

A **project** is a directory with a `hop3.toml`, git repository or not. Its binding is `[local].context` in `.hop3-local.toml`, next to that `hop3.toml`, and added to `.gitignore` when written. It is set only by an explicit command, and nothing else writes it.

**In a project with no binding, every command that reaches a server is refused** unless `-c` or `HOP3_CONTEXT` names the context: the global current context is never used inside a project. The refusal names the fix: "This checkout is not bound to a context: `hop3 context use <name>` (known: dev, demo, prod), or pass `-c`." This applies to project-less commands as well (`hop3 apps` run inside a project), so there is one rule and nothing to remember about which commands follow it.

A checkout may be bound to a protected server. Rule D still applies: a change needs `-c` or `HOP3_CONTEXT` and the typed app name, and the binding prompt says so.

### Per-context differences in `hop3.toml`

The app may differ between deployments in three things only: where it goes and what it is called there (`app`, `domains`, `env`). The build, the run commands, the addons and the volumes are the project's, so a staging deploy tests the build that prod will run. These differences live in `hop3.toml`, merged over the base configuration:

- `domains`, when present, *fully replaces* top-level `[domains]`; when absent, top-level is inherited. `domains` and `HOST_NAME` stay mutually exclusive.
- `env` merges **over** top-level `[env]`, key by key.
- `app` names the instance; without it, the app is `[metadata].id`.

The blocks are sections of `hop3.toml`, keyed by context name:

```toml
[metadata]
id = "myapp"

[contexts.demo]
app = "myapp-demo"
[contexts.demo.domains]
list = ["demo.myapp.com"]
[contexts.demo.env]
LOG_LEVEL = "debug"

[contexts.prod]
[contexts.prod.domains]
list = ["myapp.com", "www.myapp.com"]
```

`hop3 deploy` in a checkout bound to `demo` deploys `myapp-demo` with its domains and env, to whatever server the developer's `demo` context names. The name is the only link between the block and a context, so a team names its contexts alike (`dev`, `demo`, `prod`), and the file holds no address. In a project that declares blocks, a context matching none of them is refused, naming the declared ones: otherwise a typo would deploy the base configuration under the base name. A project without blocks deploys its base configuration to any context.

### Protection belongs to the server

A server is marked protected once, on the server (`PROTECTED = true` in `hop3-server.toml`), so the mark covers everyone who reaches it, from any checkout and any machine, without each person flagging it in their own config. The CLI sends the step of B that selected the context with each call (`context_source`), and the server refuses a command above the viewer role when that step is a binding or the global current context, or when the source is missing (a CLI older than this revision). A command named explicitly is answered with a request for confirmation; the CLI asks for the app's name, typed (the context's name for a command without an app), and sends the call again with `protected_confirmed`. Enforcement on the server means a stale or edited client configuration cannot bypass it.

The role is the measure of "changes something" because every command already declares one ([ADR 061](./061-standard-roles-and-rpc-authorization.md)). It also catches the few admin commands that only read (`user list`), which then need the same explicit selection.

The CLI remembers the mark on the context once a server has answered with it, and `hop3 context use` mentions it before binding a checkout to that context. The mark it remembers only warns; the server decides.

### File layout

| File | Scope | Holds | Secret? |
|------|-------|-------|---------|
| `hop3.toml` | committed, shared | the app: base config and per-deployment `app`/`domains`/`env` | **no** |
| `~/.config/hop3-cli/config.toml` | per-developer | contexts (`server`, `bootstrap`), `[cli].default_context` (the global current context), preferences, aliases | no |
| `~/.config/hop3-cli/credentials.toml` | per-developer | tokens keyed by server address | **yes** (local) |
| `.hop3-local.toml` (gitignored) | per-checkout | `[local].context`: the binding | no |
| `.hop3-app` (gitignored) | per-checkout | per-tree app pin written by `hop3 use` | no |
| the environment | per-shell | `HOP3_CONTEXT`; `HOP3_API_URL` / `HOP3_DEV_MODE`, the context named `env` | no |

## Transport: everyday, bootstrap, rescue

[ADR 014](./014-authentication-bootstrap.md) establishes that **SSH access is authentication**: whoever can reach the machine can mint an administrator token, so no password need be exchanged to get started. That is a statement about *authority*. It was read as one about *transport*: a login recorded its SSH target as the connection, so every later `hop3 apps`, `hop3 logs` and `hop3 status` opened a root shell, once per invocation, to list applications.

The two roles separate:

| Role | Address | When |
|------|---------|------|
| everyday | `server` (`https://<admin domain>`) | every command |
| bootstrap | `bootstrap` (`ssh://user@host`) | minting a token, unattended |
| rescue | `bootstrap`, forced with `--via-ssh` | when the everyday route is what broke |

A bootstrap login asks the server for its own public address, because only the server knows how it is fronted: a client holds an SSH target, which says nothing about the reverse proxy or the certificate. When the answer is a URL this machine can verify, that becomes `server` and the SSH target is kept as `bootstrap`. Everyday work then travels over the authenticated HTTP API; the root key is needed only when a token expires.

**The tunnel remains, and says why.** A server with no admin domain has no HTTPS endpoint, an untrusted certificate cannot be used silently, and a server older than the question cannot answer it. Each falls back to `ssh://` as the everyday address *and names the reason*: a silent fallback would leave an operator with a working CLI, unaware that every command opens a root shell they never chose. The same missing admin domain also makes the web dashboard unreachable (its session cookie is `Secure`), so the two consequences share one explanation and one fix.

**Renewal follows the route.** Gating unattended renewal on the *connection* being `ssh://` tied it to routing everything through a root shell. A context that talks HTTPS all day still knows a route home, and renews through it without asking.

## Resolution

Resolution stays **client-side**, in one resolver that runs before any command dispatches and returns the context, its server, the app and the reason. Every message, the line of rule C, the warning before a destructive command and `--why` print its answer, so no two displays can disagree.

The CLI then reads the per-deployment block for the selected context, looks up the token for the context's server, computes the effective config, and applies it. The server is never asked to interpret the per-deployment blocks; the schema accepts them so that a `git push` deploy of the same file validates, and the deployer ignores them.

**App resolution** is project-rooted:

1. `--app` / `-a`
2. `$HOP3_APP`
3. `.hop3-app` (per-tree pin)
4. `hop3.toml [cli].app`
5. the selected deployment's `app`
6. `hop3.toml [metadata].id`

The binding sits next to the `hop3.toml` it belongs to, so it cannot leak in from an ancestor directory. A context selected by `$HOP3_CONTEXT` is ambient: when the app it resolves differs from the project you stand in, the project-mismatch guard ([ADR 047](./047-cli-invocation-context.md)) fires.

`hop3.toml` is secret-free *by convention*, backed by a **committed-credential tripwire** that fails the upload loud on an obvious secret: an env value matching a known secret shape (`sk_live_…`, `ghp_…`, `AKIA…`, a connection string, high-entropy material). Per-deployment `domains` run the same host-safety checks (the wildcard/catch-all ban) as top-level domains.

## CLI verbs

`hop3 context` manages global contexts and the binding. It never edits `hop3.toml`.

- `hop3 context`: the context a command here would use, and which step of B chose it.
- `hop3 context list / show [name]`: read contexts.
- `hop3 context add <name> --server X [--bootstrap ssh://…] / remove / rename`: edit contexts in `config.toml`.
- `hop3 context use <name>`: inside a project, bind this checkout; outside one, set the global current context. `--global` sets the global current context from inside a project. The command asks before writing, naming the scope, the file and the address: "Bind this checkout (`~/p/myapp`) to `demo` (`https://demo.example.com`)? [y/N]", or "Set the global context to `demo`? [y/N]". `-y`/`--yes` skips the question; without a terminal and without `--yes`, it refuses. Binding to a protected server says that changes still need `-c`.
- `hop3 context unset`: remove the binding, or the global current context, by the same scope rule and with the same question.
- `hop3 login <user>@<host> [--context <name>]`: authenticate to a server, store its token, and create or update the context. With `--context <name>` and no target, it signs in again through the SSH route that context records. `hop3 login --browser [<target>]` mints a credential for the browser instead.

`--yes` skips a confirmation. `--force` overrides a safety check, and implies `--yes` as everywhere in the CLI.

## Migration

- **Project `[contexts.<name>]` blocks with `server` or `bootstrap`.** Those two keys are refused, with the command that replaces them: `hop3 context add <name> --server <address>`, and the key removed from `hop3.toml`. The rest of the block (`app`, `domains`, `env`) keeps its meaning. No `hop3.toml` in this repository or in the catalog declares `[contexts]`.
- **Checkouts that relied on the global current context.** Refused after the upgrade, with the refusal of the binding section as the fix. `CHANGES.md` states the change.
- **The single-context fallback** (one `[contexts.*]` block selected without a binding) goes: it is a selection nobody made.
- `.hop3-local.toml` keeps its format; its legacy `[current].context` key is still read for one release.
- `config.toml` is already in the global shape (third migration stage) and needs nothing.

Pre-1.0: one breaking release, no compatibility shim.

## Consequences

**Positive**

- A context means one thing everywhere: a server you can reach. `hop3 context` behaves the same in every directory, except for which pointer `use` writes, and it says which before writing.
- Switching environments ten times a day touches no committed file.
- No command inside a project reaches a server nobody chose for that checkout, and every command says where it went.
- Production needs its name on the command line or in the environment, and the app's name typed, for every change, enforced by the server.
- One resolver answers "where does this go" for every command and every message.
- No secrets in any committed or config file; tokens live only in the credential store.
- Everyday work runs over the authenticated HTTP API, so a root key is needed to mint a token and to rescue a broken route, not to list applications.

**Negative**

- One `hop3 context use` per checkout, once, before its first command.
- The binding is per checkout: a fresh clone, or a `git clean -fdx`, needs it again. The refusal says so.
- Existing checkouts are refused after the upgrade until bound.
- A protected server costs a prompt or a flag on every change, which is the point, and a server-side setting to maintain.
- A context carries two addresses; an operator who reads only `server` will not see how renewal happens.
- A server with no admin domain keeps the SSH tunnel for everything, so the privilege reduction lands only where TLS is configured.

## Rejected alternatives

- **Selecting the environment in `hop3.toml`** (`default-target`, or a per-environment file chosen there). Every switch is a commit, many a day.
- **Keying the per-deployment blocks by server address.** It writes the server into `hop3.toml`, which rule A excludes; it cannot tell two deployments on one server apart; and one server has several spellings (`https://`, `ssh://`).
- **Overlay files (`hop3.<name>.toml`, merged over `hop3.toml`), for now.** They show each deployment as its own file, which a review rule or CODEOWNERS can guard, at the cost of a second place to look and a merge rule to document. No team has asked to guard prod's configuration separately; an overlay file could later be read as one more block, so sections close no door.
- **Contexts at two scopes, project and global (the third and fourth revisions).** One word for a connection and a deployment; the commands behaved differently per directory.
- **Falling back to the global current context inside an unbound project.** The context selected in another terminal reaches this project unannounced.
- **Separate `use` and `bind` verbs.** Two verbs for one act; `use` asking before it writes, and naming its scope, shows the same thing.
- **Per-directory selection only through `.envrc` (`HOP3_CONTEXT`).** Kept as step 2 of B, but not the only way: it depends on a shell hook the user may not have.
- **Contexts project-only, with a separate `--server` for project-less commands (the second revision).** It forced users to learn which flag applied to which command.
- **Credentials inside `hop3.toml`.** Tokens are secrets and `hop3.toml` is committed.
- **A rich `hop3 server` noun with its own verb namespace.** A context already is the name for a server; a connection (the token) is plumbing.
- **Vault-style shared secrets now.** Per-app server-side storage already scopes secrets per environment; cross-environment sharing matters only at fleet scale.
- **Deriving a context name from the host.** A name like `prod.example.com` cannot be a TOML key without quoting, and shortening to the first label collides across domains.
- **Keeping `ssh://` as the everyday transport and accepting the privilege.** It makes a root key a prerequisite for read-only work, spawns a process per invocation, and routes around the API's own authentication and rate limiting.
- **Refusing to record a target when the server has no HTTPS endpoint.** It would make a domain mandatory to use Hop3 at all. The tunnel stays available and the degraded mode is named.
