# ADR 048: Server Configuration and Secret Storage

- **Status**: Accepted
- **Type**: Architecture
- **Created**: 2026-06-17
- **Related-ADRs**: [027](./027-config-system-refactoring.md) (config loader; this ADR adds the secrets carve-out to its env-vs-file precedence), [041](./041-privileged-operations-agent.md) (privileged-operations agent; this is the `hop3-server.toml` schema ADR it defers, and rootd's read access is covered below), [011](./011-encryption.md) (application-data encryption), [042](./042-cli-context-model.md) (CLI-side config, distinct from server-side), [043](./043-unified-testing-architecture.md) (unified testing architecture; the test-fixture impact is a consequence below)

## Context

A Hop3 server keeps its configuration and secrets in several places, settled per-secret over time rather than by a single rule. The result is an inconsistent surface with a known fragility.

Today secrets live in four locations:

- `/etc/default/hop3`: systemd `EnvironmentFile`, `root:root 0600`: `HOP3_SECRET_KEY`, `ACME_ENGINE`, `ACME_EMAIL`.
- `/home/hop3/hop3-server.toml`: `hop3:hop3 0600`: `HOP3_SECRET_KEY` (a second copy), the PostgreSQL and MySQL superuser passwords, `ADMIN_DOMAIN`.
- `/etc/hop3/redis-pass` and `/etc/hop3/s3-env`: `root:hop3 0640`: the Redis password and the MinIO credentials.
- `/etc/hop3/ssl/` (and per-domain `/home/hop3/ssl/<domain>/`): TLS certificates and private keys, consumed by nginx.

Three problems follow:

1. **The four backing-service admin secrets are stored two different ways.** PostgreSQL and MySQL superuser passwords sit inline in `hop3-server.toml`; the Redis and S3 secrets sit in dedicated `/etc/hop3` files. There is no reason for the split: the `/etc/hop3` pattern (root-owned, group-readable, never on a process argv) is the more defensible one, and the SQL passwords do not follow it.

2. **`HOP3_SECRET_KEY` has two sources.** The running service reads it from `/etc/default/hop3` (systemd injects it; env wins in the loader); an SSH-invoked CLI runs as `su - hop3` and cannot read that `root:root 0600` file, so it reads the copy in `hop3-server.toml`. The installer writes the same value to both and "reconciles" them. A partial or interrupted install desyncs the two: token minting still reports success, but every subsequent RPC fails authentication.

3. **The precedence and placement rules are unwritten.** [ADR 027](./027-config-system-refactoring.md) resolved the general env-over-file precedence (the environment always wins) but did not carve out secrets, which is the concern this ADR addresses; [ADR 041](./041-privileged-operations-agent.md) explicitly defers the `hop3-server.toml` schema to a future ADR. There is no taxonomy that says what belongs where.

Two facts constrain any design. First, two distinct principals read server secrets: the **service** (systemd starts it as root, then drops to `User=hop3`) and the **SSH-invoked CLI** (`su - hop3`, never root). Second, the platform is single-server and self-hosted; an external secrets manager or at-rest encryption of the control plane is disproportionate ([ADR 011](./011-encryption.md) already governs application-data encryption, a separate concern).

## Decision

### Principles

1. **Secrets are not configuration.** A secret (a credential, key, or token) lives in a dedicated, narrowly-permissioned file. Non-secret configuration lives in `hop3-server.toml`. The two never mix in one file.
2. **One secret, one source.** No secret is written to more than one location. Every reader of a given secret reads the same file.
3. **Location follows the reader; ownership follows least privilege.** A secret both written by root (the installer) and read by the `hop3` principal is `root:hop3 0640`: root owns it, the `hop3` group reads it, nothing else can. A secret only the `hop3` user touches is `hop3:hop3 0600`.
4. **Secrets never reach an argv.** They are passed to child processes through the environment or a credential file (`PGPASSWORD`, `MYSQL_PWD`, `REDISCLI_AUTH`, `MC_HOST_*`), never as command-line arguments visible in `/proc/<pid>/cmdline`. This ratifies existing practice (documented in `security.md §3.4`) as a standing rule that future code must continue to uphold.

### Storage layout

| Tier | Location | Owner / mode | Contents | Reader |
|------|----------|--------------|----------|--------|
| **Secrets** | `/etc/hop3/<name>` (one file per concern) | `root:hop3` `0640` | JWT signing key; PostgreSQL, MySQL, Redis, S3 admin credentials | the `hop3` group: i.e. both the service and the `su - hop3` CLI, plus root |
| **TLS material** | `/etc/hop3/ssl/` (system) and `/home/hop3/ssl/<domain>/` (per app) | key `0640`/`0600`, cert `0644` | certificates and private keys | nginx |
| **Server config** | `/home/hop3/hop3-server.toml` | `hop3:hop3` `0600` | non-secret settings: `ADMIN_DOMAIN`, `ACME_ENGINE`, `ACME_EMAIL`, proxy type, timeouts, and operator additions | the `hop3`-user server (via the config loader) |
| **Unit environment** | `/etc/default/hop3` | `root:root` `0600` | only the non-secret environment systemd must inject for the unit | systemd (as root, before privilege drop) |

The backing-service admin secrets become uniform: all four are `/etc/hop3` files under the same owner, mode, and reader path. Redis (`redis-pass`) and S3 (`s3-env`) already follow this; PostgreSQL and MySQL join them. `hop3-server.toml` carries no secret.

The secret files are named canonically (one concern per file) so the layout is fixed rather than reinvented per install:

| Concern | File |
|---------|------|
| JWT signing key | `/etc/hop3/secret-key` |
| PostgreSQL superuser password | `/etc/hop3/postgres-pass` |
| MySQL superuser password | `/etc/hop3/mysql-pass` |
| Redis password | `/etc/hop3/redis-pass` (existing) |
| S3 / MinIO credentials | `/etc/hop3/s3-env` (existing) |

**Credential-encryption salt.** `HOP3_CREDENTIAL_SALT` (the v2 Fernet KDF salt, `core/credentials.py`) is a key-derivation *parameter*. By default it is derived deterministically from the signing key (`sha256(domain ‖ secret_key)`), so the platform writes no salt file: the single-source signing key already makes it stable across restarts. The environment-variable override remains an operator escape hatch for those who want a salt independent of the signing key; when set, it is itself a secret and lives in the secrets tier (`/etc/hop3/credential-salt`), read the same way as the signing key. No separate salt is provisioned by default.

`/etc/default/hop3` holds no secret. The signing key moves to the secrets tier and the ACME settings move to `hop3-server.toml` (non-secret config), so nothing the platform manages needs to be injected as environment. The systemd `EnvironmentFile` is therefore optional: it exists only to carry an environment-shaped, non-secret override (for example, a non-default `HOP3_ROOT`), and on a standard install it is empty or absent. It is never a parallel home for settings that belong in `hop3-server.toml`.

`hop3-server.toml` is genuine TOML, even where its `KEY = "value"` lines resemble a flat key-value file. The server parses it with a TOML loader; the historical `KEY = "value"` form the installer emits is valid TOML, but the installer serialises through a TOML writer rather than string interpolation, so a value that needs quoting or escaping cannot produce a file the loader rejects. Operator-added settings must likewise remain valid TOML.

### Configuration precedence

This adopts the precedence [ADR 027](./027-config-system-refactoring.md) resolved, and adds the secrets carve-out below. Non-secret configuration resolves, highest first:

1. an explicit process environment variable,
2. the value in `hop3-server.toml`,
3. the built-in default.

Secrets do not participate in this chain: each secret has exactly one file (principle 2), read directly by its consumer. Because no secret is injected into the environment by the platform, a stray environment variable cannot silently shadow a secret on disk: the shadowing that let an operator's on-disk `ACME_ENGINE` be overridden by the unit environment cannot occur, because non-secret settings such as `ACME_ENGINE` live only in `hop3-server.toml` and the platform writes no competing environment copy.

### One source for the signing key

The JWT signing key has a single file under the secrets tier, `root:hop3 0640`, read identically by the running service and by the `su - hop3` CLI through `hop3`-group membership. There is no second copy in `hop3-server.toml` or `/etc/default/hop3` to reconcile, and therefore no desync mode in which freshly minted tokens are rejected.

### Migration

Existing installs are converted by moving each misplaced secret to its tier and removing the duplicates, preserving the secret's current value (never minting a new one: rotation is an explicit, separate operation). The installer is the single writer of every secret file and of `hop3-server.toml`; it reuses an existing value when present and rewrites a file only to add what is missing, so the conversion is idempotent and a redeploy neither rotates a credential nor discards an operator's setting.

When a secret exists in two legacy locations with **different** values (the desync a partial install can leave for the signing key) the value the running service currently uses wins, because that is the one already in effect (minting tokens, encrypting credentials). For the signing key that is the `/etc/default/hop3` copy (the service reads the environment first; the `hop3-server.toml` copy is the CLI's fallback). The conversion logs the discrepancy rather than silently picking one, so the operator sees that a divergence existed.

## Consequences

- The four backing-service admin secrets share one location, owner, mode, and reader path; "where is credential X?" has one answer.
- The signing-key desync failure mode is structurally removed: one file, one value, both readers.
- The environment-shadows-file surprise is removed for non-secret settings: each has a single authoritative home and no platform-written environment shadow.
- `hop3-server.toml` becomes safe to read, diff, and hand-edit as plain configuration: it contains no credential.
- Consumers that read SQL passwords from `hop3-server.toml` (the PostgreSQL and MySQL admin connectors) and the signing-key reader change their source to the secrets tier; this is an internal change behind the existing accessors.
- Test fixtures change with it. Suites that synthesise server state today by setting `HOP3_SECRET_KEY` / `POSTGRES_SUPERUSER_PASSWORD` / `MYSQL_SUPERUSER_PASSWORD` as environment variables or inline in `hop3-server.toml` must instead create the corresponding secret files (or their temp-dir equivalents); the signing-key reader reads its file rather than the config loader; and the Docker e2e path provisions the secrets directory. This is the bulk of the migration's surface and is in scope under [ADR 043](./043-unified-testing-architecture.md)'s layers.
- `hop3-rootd` ([ADR 041](./041-privileged-operations-agent.md)) needs no new accommodation: it runs as root and reads any `root:hop3 0640` secret trivially. The secrets tier is chosen so the unprivileged `hop3` principal can read it; the privileged daemon is strictly a superset.
- Backups must include `/etc/hop3/` recursively: this captures the control-plane secrets *and* the system TLS material under `/etc/hop3/ssl/` (per-app TLS lives under `/home/hop3/ssl/<domain>/` and is captured with the app's home). A `hop3-server.toml`-only copy is no longer sufficient, which is the correct expectation for a secret store kept separate from config.

## Rejected alternatives

- **Everything in `hop3-server.toml`.** Keeps one file but violates principle 1 (secrets beside config) and forces a choice between `hop3:hop3 0600` (the systemd-as-root path and root tooling read it awkwardly) and weaker permissions on a file that also holds plain config. Mixing trust levels in one file is the source of the current fragility.
- **Everything in the unit environment (`/etc/default/hop3`).** The `su - hop3` CLI cannot read a root-only file, which is exactly what created the two-source signing key; widening that file to group-readable would put every secret in one bag and still couple secrets to systemd.
- **A secrets manager or at-rest encryption of the control plane.** Disproportionate for a single-server, self-hosted PaaS, and orthogonal to the placement problem this ADR settles. Application-data encryption remains the subject of [ADR 011](./011-encryption.md).
