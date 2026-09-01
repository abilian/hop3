# ADR 056: App admin credentials: bootstrap, storage, and retrieval

- **Status**: Accepted
- **Type**: Architecture
- **Created**: 2026-07-17
- **Related-ADRs**: [046](./046-declarative-app-resources.md) (declarative app resources: generated secrets), [049](./049-catalog-distribution.md) (catalog distribution), [048](./048-server-config-and-secret-storage.md) (server config and secret storage), [054](./054-email-transport-and-notifications.md) (email is outbound-only)

## Context

Installing an application is more than starting its process. Most real applications gate everything behind a login. A freshly installed instance has no account to log in with. A platform that advertises one-command installs but drops the operator at a login wall with no credentials has staged the app and left the install unfinished.

The catalog recipes show three broken answers to this, all variants of one missing capability. Some hardcode a placeholder password (`ADMIN_PASSWORD = "changeme"`, `KC_BOOTSTRAP_ADMIN_PASSWORD = "changeme"`), which is insecure and leaves the operator unaware that a change is needed. A few generate a random password inline (`$(head -c 16 /dev/urandom)`), yet they never communicate it and regenerate it on every redeploy, so the account stays unusable. Bugsink creates no account at all. The shape common to all three is one capability: this app has an initial admin credential, so generate it, create the account, and tell the operator durably.

The platform already owns the pieces. [ADR 046](./046-declarative-app-resources.md) gives CSPRNG-backed, generated-once secrets that are stable across redeploy (`[env] X = { generate = "password" }`) and a one-shot `display` at deploy. Three things are missing: (1) a model of the account those pieces belong to, (2) a durable place to keep the credential so the operator can retrieve it after the deploy log scrolls past, and (3) an operator email to use when an app's admin identity is an email address.

## Motivation

The catalog advertises a curated set of apps as working. One-command install is the headline. An install that ends at an unenterable login page fails that promise for every app with a login, which is most of them. The `changeme` recipes make it worse: they ship a weak, well-known password to production and give the operator no signal to rotate it. Building the capability once at the platform level lets every admin-bearing app drop in the same way, which is the system-validation goal that motivates packaging apps at all.

## Decision

The operator owns the box and is already authenticated to it, so the initial admin credential is a bootstrap convenience for the operator. That framing makes retrieval on demand correct: the operator is entitled to see the credential of their own app. This ADR settles what "provide the initial admin account" means for a single-server PaaS, following the way [ADR 054](./054-email-transport-and-notifications.md) settles email.

### Operator identity

The platform gains a single notion of the operator's email, the real address of the person running the server, as a server-config value `OPERATOR_EMAIL`, read from `hop3-server.toml` alongside `ADMIN_DOMAIN`. It defaults to `ACME_EMAIL`, which is already the operator's real, validated address (the installer rejects `@example.com` placeholders for it and preserves it across redeploy), so on an existing install the value is already present. The installer accepts `--operator-email` / `HOP3_OPERATOR_EMAIL` to set it independently, persisted idempotently and preserved across redeploy, with the same real-address validation ACME applies.

`OPERATOR_EMAIL` is a server-identity fact alongside `ADMIN_DOMAIN`, describing who to reach. The dashboard login `User.email` is a separate concept, a login identity. The two may hold the same address, and app-admin bootstrap draws on the operator contact. Recipes reference it through the existing `[env]` app-fact mechanism: `{ key = "operator_email" }` resolves to `OPERATOR_EMAIL`, failing loud when a recipe requires it and it is unset.

### The admin email is the operator's real address

An application whose admin identity is an email uses `OPERATOR_EMAIL` directly. It serves as both the account identity and the destination for the app's admin mail, and replies land in the operator's real inbox with no new infrastructure.

Hop3 provides no `admin@<app-domain>` address that forwards to the operator. [ADR 054](./054-email-transport-and-notifications.md) fixes Hop3 email as outbound-only: Hop3 is never an MX, hosts no mailbox, and has no virtual-alias or recipient-forwarding machinery. A forwarding address would require an inbound mail subsystem that the platform excludes by design. The operator's real address serves the same purpose and is available today. A per-app inbound address, should it ever be wanted, is a separate decision that reopens ADR 054.

### The recipe declares an `[admin]` contract

An app that needs an initial admin account declares it in a first-class `[admin]` section. The flat key/value `[env]` space cannot express which variable is the username, which is the password, whether an email is required, and how the account is created. The account is a relationship among those, and a dedicated section lets the platform drive bootstrap generically, so each recipe stops hardcoding it.

```toml
[admin]
username = "admin"                                  # omit when the app keys admins by email
email    = "operator"                               # "operator" uses OPERATOR_EMAIL, or a literal address
password = { generate = "password", length = 24 }   # always generated
create   = "..."                                    # optional; idempotent command, receives HOP3_ADMIN_* in env
```

The platform generates the password once (reusing the ADR 046 generator), resolves the email (`operator` maps to `OPERATOR_EMAIL`, failing loud when it is required and unset), and injects a canonical, namespaced triple `HOP3_ADMIN_USER` / `HOP3_ADMIN_EMAIL` / `HOP3_ADMIN_PASSWORD` into the app's runtime environment. Each recipe adapts that canonical triple to whatever its app expects: Django `DJANGO_SUPERUSER_*`, Keycloak `KC_BOOTSTRAP_ADMIN_*`, or an entrypoint that reads a single `CREATE_SUPERUSER=email:password` variable. One platform contract then covers every app, and generating the password on the platform side clears the committed `changeme` values.

### Bootstrap runs as a builder-agnostic post-deploy step

The account-creation command runs after the app has started, as a dedicated post-deploy step in the deploy orchestration. A `before-run` hook is unsuitable here because `before-run` does not execute on the Docker-Compose deploy path, so a `before-run`-based bootstrap would silently skip Docker-deployed apps. A silent skip is a fail-loud violation. The post-deploy step covers every builder uniformly: it runs in the app's environment for native and uWSGI apps and inside the container for Docker apps.

The step runs once, guarded by a per-app marker. The `create` command must itself be idempotent (create-if-absent), so a redeploy neither recreates nor duplicates the account. A `create` that fails aborts the deploy loudly, because a running app the operator cannot enter is a failed install.

### The credential is stored, encrypted, for retrieval

The generated password is persisted in a per-app, Fernet-encrypted record (`AppAdminCredential`, holding the username, email, encrypted password, and creation time), mirroring the addon-credential store and reusing the same encryptor keyed from `HOP3_SECRET_KEY`. This record is the source of truth for retrieval: a durable, queryable home for the credential that outlives the one-shot deploy print. It cascade-deletes with the app.

The password is also injected as `HOP3_ADMIN_PASSWORD`, alongside the identity vars, so the create step and the app can consume it at runtime. It is then an ordinary app environment variable, stored the way every app env var is stored (plaintext at rest until ADR 024's at-rest encryption lands, and included in backups). The [Security Implications](#security-implications) section covers what the encrypted record does and does not buy here.

### Reaching the credential

The operator reaches the credential two ways, both showing the same data.

- **Once at install**, as a structured block at the end of the first successful deploy, after the build log, showing the login URL, the email, and the password, emitted identically for the CLI and the dashboard. A per-credential `surfaced` flag makes this fire on the first deploy that succeeds, so an install whose creating deploy failed and was retried still shows the block once, and a later redeploy leaves the password unprinted.
- **On demand**, via `hop3 app credentials --app <name>` (a full reveal, recorded in an audit line) and a dashboard credentials card that reveals on click.

Retrieval on demand supplies the durability a one-shot display lacks. It is correct because the operator owns the box and is entitled to the initial admin password of their own app.

### The stored value is the initial credential, and says so

The record holds the password the platform set. When the user later changes it inside the app, the stored value becomes stale. Every surface labels it as the initial credential and shows when it was set, so the operator can tell a possibly-stale value from a current one. Consistent with ADR 046's generate-once rule, a redeploy leaves the password unchanged.

Changing the password happens inside the app. Hop3 has no generic way to set an existing app account's password: the create hooks are create-if-absent, and re-applying a stored value on every deploy would clobber a user's own in-app change. A managed reset would need a per-recipe "set password" hook distinct from `create`, and until that exists rotation lives in the app.

## Consequences

### Positive

- The `changeme` recipes converge on one declarative pattern: a recipe states that it has an admin account and how to create it, and the platform generates, injects, records, and surfaces the credential. This is the system-validation payoff, folding many insecure per-app credentials into one mechanism, and it sets up the migration of the remaining hardcoded-credential recipes.
- An installed app is ready to log into, with the credential shown once at install and retrievable afterward.
- The committed weak passwords leave the recipes and version control.

### Negative

- The platform takes on a new class of stored secret (app-admin passwords) and a new operator-facing reveal surface. Both follow the existing encryption-at-rest and audit conventions.
- The stored password is only the initial one. When a user changes it in-app, retrieval shows a stale value, and Hop3 offers no managed reset.
- Docker apps that need account creation self-bootstrap in their entrypoint from the injected env, because recipe commands do not run on the compose path. A platform-run `[admin].create` for Docker apps is listed under Future Work; declaring it on one today aborts the deploy with an explicit message.

### Neutral

- Hop3 stays out of inbound email, per-app mailboxes, and address forwarding; the operator's real address carries the admin-email need.
- An app that manages its own accounts (SSO-only, no local admin, or a first-run web installer) omits `[admin]`. The contract is opt-in and absent by default.

## Security Implications

- **Authorization is coarse.** The reveal is an authenticated operator action, recorded in an audit line, and any authenticated operator can reveal any app's credential. This matches the posture of `hop3 env show --show-secrets` and `hop3 app destroy`. A finer, app-scoped authorization model is out of scope here and would apply platform-wide.
- **At-rest confidentiality equals that of any app secret.** The password lives Fernet-encrypted in `AppAdminCredential` and also plaintext as the `HOP3_ADMIN_PASSWORD` env var, the same as every app env var (plaintext at rest until ADR 024, present in backups). The encrypted record therefore buys retrieval durability and a queryable home, while the confidentiality boundary stays the operator's control of the host. Read access to the database or a backup already grants full compromise, and injected addon passwords carry the same exposure.
- **The password is CSPRNG-generated (ADR 046) and never committed to a recipe**, which removes the `changeme` values from version control.
- **A failed account-create aborts the deploy** so the platform never reports a successful install of an app the operator cannot enter.

## Alternatives Considered

- **An `[env]` flag for the credential.** A `credential = true` marker on a generated `[env]` value plus a `before-run` step could carry the password. It cannot express the account relationship (which var is the user, which the password, whether an email is required), leaves email resolution and account creation ad hoc per recipe, and inherits the Docker `before-run` gap. The `[admin]` section is largely sugar over the same ADR 046 primitives with that relationship made explicit.
- **A per-app `admin@<app-domain>` forwarding address.** Rejected because it requires an inbound mail subsystem that ADR 054 excludes (Hop3 as MX, an internet-facing smtpd, virtual-alias forwarding, abuse handling). The operator's real address covers the need with no new infrastructure.
- **Setting the app's password on every deploy from the stored value.** This would make `admin-reset` effective for create-only apps, but it would also overwrite a password the user changed inside the app on the next redeploy. Rotation is left to the app.

## Future Work

- A managed password reset, via a per-recipe `[admin].reset` (set-password) hook distinct from `create`.
- The in-container bootstrap path for Docker-Compose apps, so `[admin].create` covers them too.
- Migration of the remaining hardcoded-credential recipes (nextcloud, keycloak, limesurvey, miniflux, listmonk, grafana, directus, radicale) onto `[admin]`.
- An installer `--operator-email` flag surfaced through the deploy tooling; `OPERATOR_EMAIL` falls back to `ACME_EMAIL` until then.
