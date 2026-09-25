# Security

This page is for the person running a Hop3 server. It describes what the platform protects on your behalf, what stays your responsibility, and the handful of settings that matter most.

Two companion documents:

- [Security Policy](../reference/policies/security-policy.md): how to report a vulnerability, and what we commit to in return.
- [Security Model](../developers/security-model.md): the developer-facing view: trust boundaries, reviewed code patterns, and how to run a security review. Read that one when auditing the code; this page covers operation.

## The account model: four roles

Every account holds one role, and each role includes everything the roles below it grant:

| Role | What it can do |
|---|---|
| `admin` | Everything, including users, roles and server-wide settings: email, certificates, named networks, WAF state. |
| `deployer` | Deploy, configure and destroy every application; manage their addons, domains and backups; read their logs. No user or server administration. |
| `viewer` | See which applications exist, their status, processes and domains. Nothing that can show a secret: no environment values, logs, credentials or backups. |
| `member` | Sign in to the web interface and see their own profile. They get neither a CLI token nor a dashboard page, and run no command. |

A new account is a `member` unless you give it a role, at creation (`hop3 user add alice alice@example.com --stdin --role deployer`) or later (`hop3 user set-role alice deployer`). Hop3 reads the role on every request, so a change takes effect on the next one, with no token to revoke.

What the roles do not cover yet:

- **Treat a `deployer` as an administrator.** A deployment runs the application's build steps (its `before-build` hook, its package manager's install scripts) with the control plane's own privileges, so a deployer can reach everything an admin can. This changes when builds run as the application's own user.
- **Roles apply to the whole server.** A deployer can act on every application; there is no per-application ownership yet. Do not host applications for parties who should not see each other's data on the same server.
- **`git push` deploys with an SSH key, not an account.** A key in the `hop3` user's `authorized_keys` can deploy any application, whatever role its holder has.
- **Application runtimes share a Unix account.** Applications are separated by process supervision, resource limits and proxy routing, but every native application runs as the `hop3` user, so one application's code can read another's files. Per-application users are planned.

## What Hop3 protects for you

| Area | What the platform does |
|------|------------------------|
| **Addon credentials** | Encrypted at rest in the control-plane database with Fernet AEAD, keyed from `HOP3_SECRET_KEY` via PBKDF2-HMAC-SHA256 (600 000 iterations, per-install salt). A stolen database backup is useless without the key. |
| **Passwords** | Hashed with bcrypt. Never stored or logged in the clear. |
| **Sessions** | Signed JWTs, 24 h default lifetime (`HOP3_TOKEN_EXPIRY_HOURS`), revocable: logout writes the token id to a revocation list. |
| **Login endpoints** | Rate-limited to 5 attempts per minute per client IP, on both password login and magic-link redemption. |
| **Secrets in transit to subprocesses** | Database and service passwords are passed by environment variable or stdin, never on a command line where `ps` and `/proc` would expose them. |
| **Uploaded archives** | Deploy tarballs are validated member by member before extraction: path traversal, symlink and hardlink entries, and decompression bombs are all rejected. |
| **Privileged operations** | Firewall changes, proxy reloads and mounts run through `hop3-rootd`, a small root daemon reachable only over a local socket with a kernel-enforced caller check, restricted to an allow-list of binaries, with an append-only audit log. |
| **Network exposure** | An L3/L4 firewall plus an optional L7 web application firewall (OWASP Core Rule Set) in front of applications that enable it. |
| **Apps with no login of their own** | `[access] require = "auth"` puts an app behind a Hop3 sign-in, with a minimum role and anonymous public paths ([reference](../reference/config.md#access-sign-in-gate)). The app is told who is asking in headers a client cannot forge. |

## What stays your responsibility

**Host hardening.** SSH configuration, OS patching, and the host firewall are yours. See [Security Hardening](administration.md#security-hardening) in the administrator manual.

**`HOP3_SECRET_KEY` custody.** This one key decrypts every stored addon credential.

- Back it up, separately from your database backups. Lose it and every service credential must be regenerated.
- Keep it out of version control and off world-readable paths. The installer writes it to `/etc/default/hop3` with restricted permissions; if you manage it yourself, match that.
- Use a different key on every installation.
- To rotate it: change the key, then run `hop3 admin reencrypt-credentials` (`--dry-run` first). There is no automatic rotation.

**Database file confidentiality.** Secrets are encrypted inside their rows, which protects them even from someone reading the database directly. The rest of the file (application names, hostnames, configuration) is not encrypted. Use filesystem permissions and, if you need it, full-disk encryption.

**TLS.** Production should terminate TLS. Configure ACME (Let's Encrypt) with a valid contact address; the self-signed fallback exists only to keep a server from going live unencrypted.

**Account hygiene.** Given the account model above, the shortest path to a secure deployment is few accounts, promptly removed when no longer needed.

## Settings to check before going live

```bash
# 1. A unique, strong secret key is set
grep HOP3_SECRET_KEY /etc/default/hop3

# 2. The test-mode auth bypass is off (it must be absent or false)
grep -i HOP3_UNSAFE /etc/default/hop3 /home/hop3/hop3-server.toml

# 3. Authentication is actually enforced — this must return 401
curl -X POST http://your-server/rpc \
  -H "Content-Type: application/json" \
  -d '{"method":"cli","params":{"cli_args":["app","list"],"extra_args":{}}}'
```

`HOP3_UNSAFE` disables authentication entirely and exists only for automated tests in isolated containers. Two interlocks guard it: enabling it also requires `HOP3_UNSAFE_ACK=yes-I-understand`, and in production mode it is forced off at startup regardless. Never rely on those interlocks as a substitute for checking.

## What Hop3 does not do

- **No multi-factor authentication.** The design is written down but not built. If you reach the server over an SSH tunnel (the intended pattern), your SSH key is a second factor in practice.
- **No control-plane audit log.** Privileged root operations are audited; logins, token issuance and application changes are not yet recorded in a structured, queryable form.
- **No hardware-backed key storage.** No HSM, TPM or cloud KMS integration. Operators who need it integrate at the OS level.
- **No isolation between accounts**, as described above.

## Reporting a vulnerability

Please report privately to **security@abilian.com** rather than opening a public issue. We acknowledge within two business days, keep you informed, credit you unless you prefer otherwise, and will not pursue legal action for good-faith research. Full terms are in the [Security Policy](../reference/policies/security-policy.md).
