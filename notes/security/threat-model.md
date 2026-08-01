# Threat model: Hop3

*Drafted by bruce from 255 source files, 6 context documents, and 2 past audit reports. Reviewed against the tree on 2026-07-29 (`feat/webui`); corrections are marked inline where the draft asserted a control that does not exist.*

## System

Hop3 is a single-host Platform as a Service. An operator installs it on a server; app deployers push applications via CLI, web dashboard, or `git push` over SSH. The platform builds the app, provisions backing services (PostgreSQL, MySQL, Redis), configures the reverse proxy, and supervises the runtime process.

**Kind: service.** The hop3-server daemon listens on a TCP port and faces both authenticated app deployers and unauthenticated internet traffic. The CLI and installer are local tools in the same repository but are *not* the adversary's surface: they run on the operator's or developer's own machine with that user's own privileges.

## Assets

| Asset | Value | Protected by |
|-------|-------|--------------|
| `HOP3_SECRET_KEY` | Decrypts every stored addon credential and signs every JWT | Operator custody; file mode on `/etc/default/hop3` |
| Addon credentials (PG/MySQL/Redis passwords) | Access to all tenant databases | Fernet AEAD at rest; env-variable-only subprocess passing. **Not** isolated between apps at runtime: see §Runtime isolation |
| Admin JWT tokens | Full control-plane access (operator-equivalent) | bcrypt password hashing; rate-limited login on **every** transport that verifies a password, drawing on one shared budget; uniform failure responses so accounts cannot be enumerated; revocable tokens; httponly cookie |
| Control-plane database | App names, hostnames, addon bindings, user list | SQLAlchemy parameterisation; filesystem permissions |
| App source code and runtime data | Tenant intellectual property and user data | uWSGI vassal supervision; cgroup limits; filesystem layout. **Not** a security boundary between apps: see §Runtime isolation |
| Server uptime | Availability of all hosted apps | Rate limiting; resource limits; single-worker invariant for rate limiter |

### Runtime isolation: what actually separates two apps

**Nothing does, at the OS level.** Every uWSGI vassal is started with the uid and gid of the process writing its config (`run/uwsgi/worker.py:124-130`), which is `hop3`. All deployed applications therefore run as the same Unix user, share its filesystem access, and can read one another's source trees, runtime data, and addon-credential files.

Per-app UID separation is designed in [ADR 055](../adrs/055-app-runtime-uid-separation.md) but its status is **Proposed**: the ADR states plainly that un-migrated apps "keep running as `hop3` (no worse than today)". Until it ships, treat code execution inside any deployed app as equivalent to code execution as `hop3`, which is the platform's own service account.

What *does* separate apps today is real but narrower: cgroup resource limits ([ADR 046](../adrs/046-declarative-app-resources.md)) bound one app's CPU, memory and PIDs so it cannot starve another; per-app nginx routing keeps traffic addressed correctly; and the `hop3` user is itself unprivileged, so an app cannot reach root except through `hop3-rootd`'s allow-listed operations. That is availability and correctness isolation, not confidentiality isolation.

## Adversaries

| Adversary | Capabilities | Primary target |
|-----------|-------------|----------------|
| **Unauthenticated network attacker** | Can send HTTP requests to the server's listening port. Cannot authenticate. | Bypass auth; brute-force credentials; exploit injection in pre-auth handlers |
| **Authenticated app deployer (other tenant)** | Has a valid Hop3 account and can push apps, create addons, run RPC commands. In the current model this is operator-equivalent: see Invariants. | Escalate to host-level execution; read another app's addon credentials; DoS the server |
| **Dependency attacker** | Controls a package Hop3 pulls at build or runtime. | Inject code into the server process or into built app artifacts |
| **Network-adjacent attacker on the host** | Has a shell account on the same machine (not root, not `hop3`). Can read `/proc`, scan ports. | Read secrets from process argv; connect to unprotected addon ports |
| **Malicious `hop3.toml` author** | Publishes a repo with a crafted `hop3.toml` that a developer clones and deploys. | Exploit CLI-side parsing; inject proxy directives; abuse extension allow-lists |

## Trust boundaries

| Boundary | What crosses it | Validated where |
|----------|----------------|-----------------|
| **Unauthenticated HTTP → authenticated session** | Login credentials, magic-link tokens, JWT bearer tokens | `auth.py` rate limiter + bcrypt verify; `rpc.py` `_check_authentication` via `current_identity`; JWT signature validation |
| **App deployer → host** | `hop3.toml` fields, tarball contents, app commands, env values, addon names, git push data | Input validators (`validate_service_name`, `validate_app_name`, `validate_hostname_list`); archive member-by-member validation; Postgres extension allow-list; command dispatch only over authenticated RPC |
| **hop3 user → root** | JSON-RPC requests over Unix socket to `hop3-rootd` | `SO_PEERCRED` UID check (kernel-enforced); per-op typed validators inside rootd; binary allow-list (`exec.py`); append-only audit log |
| **SSH git push → app deploy** | Git objects pushed to bare repo, triggering post-receive hook | SSH `authorized_keys` forced command; app name extracted from repo path and validated; `git archive` extraction (not checkout) |

## Entry points

| Surface | Reachable by | Notes |
|---------|-------------|-------|
| `POST /rpc` (JSON-RPC) | Unauthenticated network attacker (commands gated by auth) | ~190 registered command classes; auth checked before command existence revealed. "Gated by auth" is true of all but the handful with `requires_auth = False`: see the next row and `test_rate_limited_commands.py` for the current list |
| `auth get-token` via `POST /rpc` | Unauthenticated network attacker | **The primary CLI login path**, and the only pre-auth command that verifies a credential. Rate-limited 5/min/IP against the same budget as the web form; all failure modes return one identical, bcrypt-timed response. Listing only the transport above is what let this go unthrottled until 2026-07-29 |
| `POST /auth/login` | Unauthenticated network attacker | Rate-limited: 5/min/IP (shared budget with `auth get-token`); bcrypt verify |
| `GET /auth/magic/{token}` | Unauthenticated network attacker (token-bearing) | Rate-limited; token validated separately from bearer path |
| `POST /auth/logout` | **Unauthenticated** (no guard on the handler) | Reached from a form in `base.html`. Was a `GET` until 2026-08-01, which `samesite=lax` made CSRF-able (forced logout) and which was the one exception to the every-mutation-is-a-POST invariant below |
| `GET /dashboard/*` | Authenticated user (cookie or bearer) | Reads; no ownership check (single-tenant model) |
| `POST /dashboard/apps/*`, `/dashboard/backups/*` | Authenticated user (cookie or bearer) | Mutations; samesite=lax blocks cross-site POSTs |
| `GET /api/stream/{id}` | Authenticated user (cookie or bearer) | SSE streaming; timeout-bounded |
| `GET /api/stream/{id}/status` | Authenticated user | Stream status polling |
| `GET /dashboard/catalog/*` | Authenticated user | Guarded by `auth_guard` at controller level |
| `GET /dashboard/catalog/icons/{app_id}` | **Unauthenticated** | Deliberate `guards=[]` override (`catalog.py:78`), carrying an `# AUDIT:` marker; the catalog is public by design. Path containment via `find_icon()`, raster-only extension allow-list |
| `GET /auth/login` | Unauthenticated | The login page itself |
| `GET /static/*` | Unauthenticated | Static assets only |
| SSH `git push` to `hop3@host:app` | App deployer with SSH key in `authorized_keys` | Triggers post-receive hook → `git-hook` command |
| Unix socket `/run/hop3-rootd/socket` | `hop3` user (local only) | `SO_PEERCRED` UID gate; mode 0660 `root:hop3` |
| `hop3-cli` / `hop3-tui` on workstation | Local user (owns the shell) | Self-injection is not modelled; threats are hostile remote server, malicious `hop3.toml` |
| `hop3-install` / `hop3-deploy-server` | Operator (root on target host) | Operator is fully trusted; validates `--branch`, `--host`, `--user` against regex |
| Environment variables | Operator (sets at install); process environment | `HOP3_SECRET_KEY`, `HOP3_UNSAFE` (gated), `HOP3_DEBUG`, `HOP3_TRUSTED_PROXIES` |
| `hop3.toml` (app config) | App deployer authors; server parses at deploy | Pydantic schema validation; `HOP3_SKIP_CONFIG_VALIDATION` disabled in production |
| `~/.config/hop3-cli/config.toml` | CLI user; atomic-write 0600 | Contains JWT bearer token |

### Other listening surfaces on the same host

Opt-in, so absent from a default install, but present on any host where the operator enabled them, and reachable by every app, since all apps share the `hop3` account (§Runtime isolation).

| Surface | Enabled by | Binds | Notes |
|---------|-----------|-------|-------|
| Postfix submission endpoint | `--with email` | Loopback only ([ADR 054](../adrs/054-email-transport-and-notifications.md)) | Relays for local processes only, never an open relay. Any local process can submit; the envelope sender is whatever the submitting app presents, so sender attribution between apps rests on the app, not on the OS identity |
| MinIO (S3 addon) | `--with s3` | `--address :9000`, console `:9001` on **all interfaces**, though the platform addresses it as `http://127.0.0.1:9000` | Root credentials in `MINIO_CREDENTIALS_FILE`. See the note below on the firewall |
| LeWAF proxy (per WAF-enabled app) | `[waf]` in `hop3.toml` ([ADR 050](../adrs/050-waf-l7-lewaf.md)) | `127.0.0.1` | Request-parsing layer between nginx and uWSGI; itself an input-handling surface, running OWASP CRS |
| App-declared fixed ports | `[ports]` in `hop3.toml` ([ADR 045](../adrs/045-fixed-port-registry.md)) | Per app | Registry prevents two apps claiming the same port; exposure is governed by the firewall |

**The firewall does not default-deny.** `hop3-rootd`'s nftables input chain is created with `policy=accept` and only *adds* accept rules; the comment at `nft/table.py:64` states that deny "is the operator's main-chain responsibility". So a service bound to all interfaces is reachable from the network unless the operator has their own default-deny policy. This matters for the MinIO row above and is worth settling explicitly rather than inferring.

## Invariants

1. **No unauthenticated access to mutating operations.** Every RPC command that changes state requires a valid JWT: `Command.requires_auth` defaults to `True` (`commands/_base.py:58`), and `rpc.py` returns the 401 *before* the "command not found" response, so command existence is not revealed pre-auth.

   The unauthenticated surface is `/` (redirect), `GET|POST /auth/login`, `POST /auth/logout`, `GET /auth/magic/{token}`, `/static/*`, `GET /dashboard/catalog/icons/{app_id}`, and `POST /rpc` itself (which must be reachable to answer 401). Guards are declared per controller, not globally, so **this list is enumerated by hand and can go stale**: verify it with `grep -rn "guards=" packages/hop3-server/src/hop3/server/controllers/` rather than trusting it. A new controller that forgets `guards=[auth_guard]` is unauthenticated by default; that is the failure mode to watch for, not a violation of the list above.

2. **No credential in argv.** Any subprocess that receives a secret gets it via environment variable or stdin: `MYSQL_PWD`, `PGPASSWORD`, `REDISCLI_AUTH`, `--password-stdin`.

   **Enforced since 2026-08-01.** `tests/a_unit/test_no_credentials_in_argv.py` scans `packages/*/src` for the argv forms and fails the build on a match. It is repo-wide on purpose: this invariant has drifted before (the May 2026 round found `MYSQL_PWD` applied in the server plugin but missed in the installer's connection-verify helper) and the drift is always sister-site, one call site fixed and its twin in another package left alone, which no per-package check can see.

3. **Password verification is rate limited on every transport that offers it, and its failures are uniform.** One `AUTH_RATE_LIMITER` instance backs both `POST /auth/login` and the RPC `auth get-token`; a second instance would be a second budget, so the sharing is the control. Unknown user, disabled account and wrong password return one identical response and cost the same bcrypt time (`burn_password_check`).

   **Partly enforced.** `test_rate_limited_commands.py` fails when a new `requires_auth = False` command neither declares `rate_limited = True` nor is listed as verifying no credential, so a new *command* cannot drift. A new *controller* route that checks a password can still forget the limiter: routes are not enumerable the same way. See security-model.md §3.8, §3.9.

4. **No deployer-controlled string interpolated into SQL identifiers without validation.** `validate_service_name` gates addon names before they reach `CREATE DATABASE` / `GRANT`. `psycopg2.sql.Identifier` plus an allow-list gates Postgres extensions. Redis db numbers are sequentially allocated, not derived from input.

5. **`HOP3_UNSAFE` cannot be active in production.** `enforce_unsafe_mode_policy()` runs at startup: forces the flag off when `MODE=production`, requires `HOP3_UNSAFE_ACK=yes-I-understand` otherwise.

6. **rootd executes only allow-listed binaries, only for callers with UID `hop3` (or root).** `SO_PEERCRED` check enforced by kernel; binary path frozenset in `exec.py`; per-op validators run inside rootd before execution.

7. **Deploy tarballs are validated member by member.** Path traversal, symlink entries, hardlink entries, and decompression bombs are rejected before extraction.

8. **Addon credentials are encrypted at rest.** Fernet AEAD with PBKDF2-HMAC-SHA256 (600k iterations, per-install salt). Stored as versioned tokens in the database; a DB backup is useless without `HOP3_SECRET_KEY`.

9. **The control plane is single-tenant.** An authenticated account is operator-equivalent and can act on any app. This is a design decision for 0.7, not an invariant to enforce. Treat cross-tenant access *over the RPC and dashboard surfaces* as the model rather than a vulnerability.

   Do not extend this to the runtime. That two accounts share the control plane is decided; that two *apps* share a Unix account is an unfinished migration ([ADR 055](../adrs/055-app-runtime-uid-separation.md), Proposed) with a scheduled fix. A finding that one app's code can read another's data is a live exposure against the intended design, not an instance of invariant 9: see §Runtime isolation.

## Out of scope

| Risk | Reason |
|------|--------|
| **Post-host-compromise** ("attacker is already root") | Operator compromise precedes anything Hop3 can defend against on this layer |
| **Self-injection on developer workstation** (crafted `hop3.toml` that runs commands on the CLI user's own machine) | The user owns their shell; no privilege boundary is crossed |
| **Key custody beyond the process environment** (HSM, TPM, cloud KMS) | Explicit non-goal; operators integrate at OS level |
| **Automated key rotation** | Manual procedure documented; rotation is `hop3 admin reencrypt-credentials` |
| **Database file encryption** | Secrets are encrypted inside rows; file-level confidentiality is the operator's job |
| **Multi-node tenancy isolation** | Hop3 is single-host; tenants who don't trust each other get separate servers |
| **Control-plane separation between accounts** | Single-tenant by design for 0.7; multi-tenant ownership is planned |
| **Control-plane audit log** | rootd audits privileged operations; RPC-layer audit is planned for 0.8 |
| **CSRF token on dashboard** | `samesite=lax` blocks cross-site POSTs and every mutation is a POST; a route-map test now fails on any state-changing GET, so the property this rests on is enforced rather than periodically re-checked |
| **Multi-factor authentication** | Designed (ADR 012), not implemented; SSH key via tunnel pattern is a second factor in practice |
| **Compliance certifications** (GDPR, ISO 27001) | Hop3 ships primitives; operators certify their deployments |
| **Third-party app security** | Hop3 deploys and routes apps; their internal security is the deployer's responsibility |

## In scope, currently unmitigated

Distinct from the table above: these are risks the model *does* accept as real, with no control in place yet. They are listed so an audit reports them as findings rather than closing them against a scope exclusion.

| Exposure | State |
|----------|-------|
| **One app's code can read every other app's source, data and addon credentials** | All apps run as `hop3`. Fix designed in [ADR 055](../adrs/055-app-runtime-uid-separation.md) (Proposed), not scheduled. See §Runtime isolation |
| **Services bound to all interfaces are not firewalled off by default** | The nftables input chain is `policy=accept` and additive; default-deny is left to the operator. MinIO binds `:9000`/`:9001` while the platform addresses it as loopback. Whether that pairing is intended has not been settled |

## Always reported anyway

Committed secrets, injection into a shell or SQL or a template, memory unsafety,
hand-rolled cryptography, and authentication that can be skipped outright. These
are defects whether or not this model has an adversary who reaches them, because
threat models are wrong and systems get repurposed.
