# ADR 061: Standard Roles and Control-Plane Authorization

- **Status**: Proposed
- **Type**: Architecture
- **Created**: 2026-09-22
- **Related-ADRs**: [010](./010-security-and-resilience.md) (security umbrella), [014](./014-authentication-bootstrap.md) (authentication bootstrap), [050](./050-waf-l7-lewaf.md) (WAF; its deferred `auth` gate), [062](./062-authenticated-access-gate.md) (the access gate, which names these roles)

## Context

Hop3 authenticates every control-plane call and authorizes almost none of them. The RPC dispatcher verifies the caller's token and stops there. A handful of commands, all in user management and email, call `require_admin()` from inside their own body. Every app, addon, env, domain and backup command runs for any authenticated caller. The dashboard behaves the same way. Its controllers check that a user is signed in and never check a role.

The security model records the consequence: a Hop3 account is an operator-equivalent credential (`notes/security/security-model.md` §1.4). That was an acceptable description of a server with one user. It stops being acceptable once an account exists for a narrower purpose. The access gate ([ADR 062](./062-authenticated-access-gate.md)) creates that purpose: someone who may *see* an app must not be able to deploy it, destroy it or read its secrets. Without authorization on the control plane, an account created to pass a gate can run `env show` on every app on the server.

The data model already carries roles: `Role` and a user-role association table. In practice only one role name, `admin`, is ever created. The names are free-form strings. Nothing enforces anything against them except the scattered `require_admin()` calls.

## Decision

### 1. A fixed set of standard roles

Hop3 defines four roles. They belong to the platform: no command creates, renames or deletes one.

| Role | Control plane | Passes an access gate |
|---|---|---|
| `admin` | Everything, including users, role grants and server-wide settings (email, certificates, named networks, WAF state). | Yes |
| `deployer` | App lifecycle, configuration and addons for every app: deploy, destroy, `env`, `addon`, `domain`, `backup`, logs. No user or server administration. | Yes |
| `viewer` | Read-only state: which apps exist, their status, processes and domains. No command whose output can carry a secret (`env show`, logs, addon credentials, backup contents). | Yes |
| `member` | None. The account can sign in to the web UI and nothing else. | Yes |

The roles are **totally ordered**: `admin > deployer > viewer > member`. Each includes everything the roles below it grant. A command declares the *minimum* role it needs; a gate declares the minimum role it admits.

Custom roles are out of scope. With a standard vocabulary, a recipe written against one server means the same thing on every other. An operator can take in a fixed ladder at a glance. Custom roles are the last resort for a need these four cannot express. No such need has been shown.

### 2. Every account has exactly one server role

A user holds one server role, stored on the user. There is no "no role" state. `member` is the floor: a new account is `member` unless created with a higher one. This replaces the free-form `Role` table and its association table, which modelled a many-to-many relation the platform never needed.

Only an `admin` can change another account's role. The last active `admin` cannot be demoted or disabled.

### 3. Authorization lives in the dispatcher and denies by default

Each command class declares `min_role`, beside the `requires_auth` and `destructive` attributes it already carries. The RPC dispatcher reads the caller's role and refuses the call before the command runs. No command body decides authorization for itself; the existing `require_admin()` calls become `min_role = Role.ADMIN` declarations.

The base-class default is `admin`. A command added without a declaration is therefore admin-only, which fails safe. Review sees it too. A test compares each registered command's effective minimum role with a checked-in table. Any change to who can run what then shows up in a diff.

The dispatcher reads the caller's role from the database on every request. The token never supplies it. A demotion or a disabled account takes effect on the next call, without revoking outstanding tokens. A token whose subject names no account is refused, however it was signed. Test harnesses obtain their tokens the way `hop3 login --ssh` does, for an account that exists. The existing token scopes (`authenticated`, `admin`) carry no authorization meaning.

`auth get-token` refuses a `member`. The account can run no command, so a token for it could do nothing, and would look like a broken one. Once per-app grants exist (§5), a `member` who holds one can obtain a token.

A denied call returns an ordinary structured RPC error naming the command, the role it needs and the caller's role. It is distinct from the unauthenticated error, so a client can tell "sign in" from "ask an admin".

### 4. The dashboard uses the same rule

Every dashboard route declares a minimum role through the same mechanism: pages that read state need `viewer`, forms that change it need the role the equivalent RPC command needs. A `member` who signs in sees their profile and nothing else.

### 5. Designed for per-app roles

Per-app roles are the next step. The design above is chosen so they extend it:

- A **grant** will pair a user, a standard role and an app. The server role from §2 is the grant whose scope is the whole server.
- A user's **effective role for an app** is the higher of their server role and their grant for that app. A `member` granted `deployer` on one app can deploy that app and nothing else.
- The dispatcher already resolves the app a command targets (`--app` is always a flag), so the check moves from "caller's role" to "caller's effective role for this app" in one place.
- The role names do not change: the same four words work at both scopes.

Per-app roles still need a grant table and a migration deciding who holds which apps on an existing server. This ADR provides neither.

### 6. What the roles do not cover

Three paths reach the control plane without passing through the dispatcher's check, and the roles say nothing about them:

- **Build steps run recipe code as `hop3`.** A `before-build` hook or a package-manager install script executes with the control plane's identity, which reaches rootd and can read the key that signs tokens. A `deployer` can therefore mint an `admin` token through a recipe, and the two roles are equivalent until builds drop to the app user ([ADR 055](./055-app-runtime-uid-separation.md), open question 6). `viewer` and `member` hold either way: neither can start a build.
- **`git push` is authorized by SSH key.** The post-receive hook runs `hop3-server git-hook` under the `hop3` user's forced command, with no token and no account. Holding a key in `hop3`'s `authorized_keys` is permission to deploy any app. Mapping keys to accounts belongs with per-app grants.
- **Commands run on the host through `hop3-server`** call command classes directly. They need a shell on the server, which is outside this model.

### 7. Migration

Existing users with the `admin` role become `admin`. Every other existing user becomes `deployer`, which preserves the access they have today. The migration drops the `Role` and association tables.

## Consequences

### Positive

- A Hop3 account stops being operator-equivalent by construction. The statement in the security model becomes "an account can do what its role grants".
- One enforcement point. A command cannot forget to check. The checked-in table puts the whole policy in one reviewable file.
- The access gate has an account to admit that holds no control-plane authority (`member`).

### Negative

- Every command needs a correct `min_role`. The admin-only default makes a missed one fail closed, so the mistake surfaces as a denied call. Someone still has to diagnose it.
- A per-request role lookup adds one indexed read to every RPC call.
- A fixed ladder cannot express "may read logs but not deploy". That is the price of a standard vocabulary. Custom roles stay available as a later extension for this reason.

## Alternatives considered

**Operator-defined roles with per-command permissions.** Buys arbitrary policies. Costs a permission vocabulary to design, document and keep stable across releases. Recipes also stop being portable: a recipe naming `editors` means nothing on a server without it. The choice turns on a real need the four standard roles cannot express.

**Keep checks inside commands.** Buys no dispatcher change. Costs the property that matters: a new command is open unless its author remembers. This is how the current gap arose.

**Carry the role in the token.** Buys a stateless check. Costs revocation: a demoted user keeps their old authority until the token expires. The choice turns on whether the per-request lookup ever shows up as a measurable cost.

## Open questions

1. **Which read commands belong to `viewer`.** The line is "no output that can carry a secret". Logs are the hard case: most are harmless and some print connection strings. This ADR puts logs at `deployer`; the per-command table is where that is decided and reviewed.
