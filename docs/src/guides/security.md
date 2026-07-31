# Security

This page is for the person running a Hop3 server. It describes what the platform protects on your behalf, what stays your responsibility, and the handful of settings that matter most.

Two companion documents:

- [Security Policy](../reference/policies/security-policy.md) — how to report a vulnerability, and what we commit to in return.
- [Security Model](../developers/security-model.md) — the developer-facing view: trust boundaries, reviewed code patterns, and how to run a security review. Read that one if you are auditing the code rather than operating it.

## The account model: accounts are operator-equivalent

**Any Hop3 account can act on any application on the server.** There is no per-application ownership. An account you create to let a colleague deploy one app can also stop, reconfigure, back up, or destroy every other app on that server, and can read every addon's credentials.

This is the current design. Hop3 targets a single server run by a single team, and the control plane is single-tenant.

What follows from it:

- **Treat every account as an administrator account**, whatever its scope. Hand them out on that basis.
- **Do not use one Hop3 server to host applications for parties who should not see each other's data.** Give them separate servers.
- Application *runtimes* are isolated from each other — separate Unix users, separate process supervision, resource limits, separate proxy routing. The shared surface is the control plane, not the running apps.

Per-application ownership is planned for a future release. Until it ships, the rule above is the one to provision by.

## What Hop3 protects for you

| Area | What the platform does |
|------|------------------------|
| **Addon credentials** | Encrypted at rest in the control-plane database with Fernet AEAD, keyed from `HOP3_SECRET_KEY` via PBKDF2-HMAC-SHA256 (600 000 iterations, per-install salt). A stolen database backup is useless without the key. |
| **Passwords** | Hashed with bcrypt. Never stored or logged in the clear. |
| **Sessions** | Signed JWTs, 24 h default lifetime (`HOP3_TOKEN_EXPIRY_HOURS`), revocable — logout writes the token id to a revocation list. |
| **Login endpoints** | Rate-limited to 5 attempts per minute per client IP, on both password login and magic-link redemption. |
| **Secrets in transit to subprocesses** | Database and service passwords are passed by environment variable or stdin, never on a command line where `ps` and `/proc` would expose them. |
| **Uploaded archives** | Deploy tarballs are validated member by member before extraction — path traversal, symlink and hardlink entries, and decompression bombs are all rejected. |
| **Privileged operations** | Firewall changes, proxy reloads and mounts run through `hop3-rootd`, a small root daemon reachable only over a local socket with a kernel-enforced caller check, restricted to an allow-list of binaries, with an append-only audit log. |
| **Network exposure** | An L3/L4 firewall plus an optional L7 web application firewall (OWASP Core Rule Set) in front of applications that enable it. |

## What stays your responsibility

**Host hardening.** SSH configuration, OS patching, and the host firewall are yours. See [Security Hardening](administration.md#security-hardening) in the administrator manual.

**`HOP3_SECRET_KEY` custody.** This one key decrypts every stored addon credential.

- Back it up, separately from your database backups. Lose it and every service credential must be regenerated.
- Keep it out of version control and off world-readable paths. The installer writes it to `/etc/default/hop3` with restricted permissions; if you manage it yourself, match that.
- Use a different key on every installation.
- To rotate it: change the key, then run `hop3 admin reencrypt-credentials` (`--dry-run` first). There is no automatic rotation.

**Database file confidentiality.** Secrets are encrypted inside their rows, which protects them even from someone reading the database directly. The rest of the file — application names, hostnames, configuration — is not encrypted. Use filesystem permissions and, if you need it, full-disk encryption.

**TLS.** Production should terminate TLS. Configure ACME (Let's Encrypt) with a valid contact address; the self-signed fallback exists so a server is never unencrypted, not as a production answer.

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

Stated plainly, so you can plan around them:

- **No multi-factor authentication.** The design is written down but not built. If you reach the server over an SSH tunnel — the intended pattern — your SSH key is a second factor in practice.
- **No control-plane audit log.** Privileged root operations are audited; logins, token issuance and application changes are not yet recorded in a structured, queryable form.
- **No hardware-backed key storage.** No HSM, TPM or cloud KMS integration. Operators who need it integrate at the OS level.
- **No isolation between accounts**, as described above.

## Reporting a vulnerability

Please report privately to **security@abilian.com** rather than opening a public issue. We acknowledge within two business days, keep you informed, credit you unless you prefer otherwise, and will not pursue legal action for good-faith research. Full terms are in the [Security Policy](../reference/policies/security-policy.md).
