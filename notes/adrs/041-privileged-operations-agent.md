# ADR 041: Privileged Operations Agent (hop3-rootd)

- **Status**: Accepted
- **Type**: Architecture
- **Created**: 2026-04-24
- **Related-ADRs**: [010](./010-security-and-resilience.md) (security and resilience), [017](./017-agent-based-architecture.md) (agent-based architecture), [020](./020-pluggable-architecture.md) (pluggable architecture), [036](./036-cli-ergonomics.md) (CLI ergonomics), [040](./040-network-firewall-and-port-exposure.md) (network firewall and per-app port exposure), [045](./045-fixed-port-registry.md) (fixed-port registry (the `[[ports]]` mechanism that drives rootd's firewall ops), [046](./046-declarative-app-resources.md) (declarative app resources) the cgroup/mount ops)

## Context

`hop3-server` runs as the unprivileged `hop3` system user: non-root.

Without this ADR, the hop3 user holds a small sudoers fragment (`/etc/sudoers.d/hop3`, written by the installer) granting NOPASSWD access to exactly four nginx commands: `systemctl reload nginx`, `systemctl restart nginx`, `nginx -s reload`, `nginx -t`. Hop3-server's proxy plugins shell out via `sudo -n`. This is the only sudo path that works in production. (Caddy, Traefik, and PostgreSQL plugins have similar `sudo -n` calls in their code, but their NOPASSWD entries are never granted by the installer; those calls fail silently and the plugins' fallback paths handle the failure: effectively dead code in production.)

**The goal of this ADR**: the hop3 user is a *strict non-sudoer*. The four nginx entries are retired (their work moves into hop3-rootd's `nginx.reload` and `nginx.validate_config` ops). The installer no longer creates `/etc/sudoers.d/hop3`. Hop3-server holds no elevated privileges of any kind: every kernel-boundary operation goes through hop3-rootd. The impact of a hop3-server compromise is bounded to "what the hop3 user can do" with no escalation path.

The discipline holds for everything except nginx reload because Hop3 has either pushed root-needing work to install time (the installer runs as root once) or sidestepped it. The package-installation story is the clearest example: `[build].packages` declarations are honoured *not* by running `apt install` at deploy time but by deriving an installer baseline from the catalogue at server-setup time and pre-installing the union. This works because package installation is monotonically additive and because the catalogue is known at install time. The same workaround does not generalise.

[ADR 040](./040-network-firewall-and-port-exposure.md) introduces declarative per-app port exposure. The runtime mutation of host firewall state (nftables / ufw / iptables: all of which need `CAP_NET_ADMIN`, effectively root) cannot be pushed to install time:

- Pre-opening every port the catalogue might ever request is unacceptable as an attack-surface decision.
- It does not scale to user-supplied apps the catalogue does not know about.
- It violates least-surface as a principle.

So the firewall feature forces a runtime privilege-separation step. Given such a step, the existing nginx-reload sudoers fragment is the next thing to retire: the same daemon handles both, and they are addressed together.

[ADR 040](./040-network-firewall-and-port-exposure.md)'s draft sketches a "sudoers fragment for a tightly-scoped command" approach for firewall ops too. While workable for one feature, it has known weaknesses: every invocation is a setuid escalation, the validation surface is "whatever the wrapper script parses", the sudoers file becomes a TOFU asset, and the model does not generalise to other privileged operations Hop3 will eventually need (certificate issuance, optional runtime package installation, systemd unit management).

A separate observation, made while drafting [ADR 040](./040-network-firewall-and-port-exposure.md): the cloud-provider firewall case (Hetzner Cloud Firewall, Scaleway Security Group, AWS Security Group) is **architecturally simpler than the local-firewall case**, because the cloud provider exposes a control-plane API that hop3-server can call directly with operator-supplied credentials. No privilege-escalation gymnastics; the kernel boundary is replaced by a network boundary, and the auth boundary is a token rather than a UID.

This ADR proposes that we make the local case look like the cloud case: introduce a small root-running daemon that exposes a control-plane API to hop3-server over a Unix socket. The daemon is the kernel-boundary executor for privileged operations Hop3 performs at runtime. From hop3-server's perspective, "the local box" and "the cloud" become two equally-shaped backends behind a single `Firewall` plugin protocol.

## Decision

Introduce **`hop3-rootd`**, a small Python daemon that runs as root and exposes a narrow set of high-level privileged operations to `hop3-server` (running as the `hop3` user) via a Unix socket. The daemon is the kernel-boundary executor for runtime privileged actions; hop3-server never invokes `sudo` directly and never holds elevated capabilities.

### 1. Capability executor

The daemon exposes **typed intents**. Each operation has a fixed argument schema, validated server-side. The daemon owns the translation from intent to privileged actions; the caller never composes a shell command and the daemon never accepts one.

Concretely, `hop3-rootd` rejects:

- arbitrary command execution (no `exec` op);
- raw nftables / ufw / iptables strings;
- file paths chosen by the caller (paths are derived from a small allow-list of locations rooted in `/run/hop3-rootd/`, `/var/lib/hop3-rootd/`, `/var/log/hop3-rootd/`).

It accepts:

- structured operations like `firewall.add_rule({port, protocol, source, app_name, description})`;
- structured queries like `firewall.list_rules()`;
- a small set of well-defined intents that grow operation-by-operation in subsequent revisions.

This bounds the attack surface to "what the daemon's API has been designed for". Each new operation is a separate threat-modelling exercise. The daemon never grows an `exec_arbitrary_command` op.

#### No authorization layer

Rootd does not include a policy file or per-op authorization. SO_PEERCRED admits the hop3 user; structural validation rejects malformed requests; that is the entire authorization model.

A per-op policy layer would be theatre against a compromised hop3-server: SO_PEERCRED only authenticates "you're the hop3 user", and any "app A is requesting this rule" claim a compromised hop3-server makes is unverifiable. Rootd has no way to distinguish "hop3-server doing the right thing for app A" from "compromised hop3-server doing the wrong thing while claiming to act for app A".

The threat model is therefore named explicitly: **hop3-server compromise = total compromise**. A compromised hop3-server already has access to all app source, all `[env]` secrets, all addon credentials, and the SQLite database with auth tokens; the marginal damage from "attacker can also call rootd's ops" is small compared to what's already lost.

So: **no policy file**. Rootd accepts any well-formed request from the hop3 user. Validation is structural. The "did you mean this?" prompt lives in the deploy CLI and web UI: see section 9.

If a future operator needs an emergency lockdown, the mechanism is `systemctl stop hop3-rootd` (which preserves existing rules but blocks new grants until restart). Adding a richer policy mechanism later if real demand surfaces is straightforward; building the muscle now for a feature that probably won't be used adds review surface for no real win.

### 2. Baseline operation scope

The daemon exposes these operations:

```
firewall.add_rule(spec) -> Rule
firewall.remove_rule(rule_id) -> None
firewall.list_rules({app_name?}) -> list[Rule]

nginx.reload() -> None
nginx.validate_config() -> ValidationResult

daemon.health() -> HealthStatus
daemon.handshake() -> {protocol_version, daemon_version, accepted}
```

**Why nginx is in the baseline set**: hop3-server already shells out via `sudo -n systemctl reload nginx` (and three sister commands) for normal deploys. The `/etc/sudoers.d/hop3` fragment that grants this is the *existing* privilege escalation that rootd is positioned to retire. A firewall-only daemon would leave two privilege paths on every host (rootd plus the sudoers fragment); routing nginx through rootd collapses them to one.

**Why postgres reload is *not* a rootd op**: the existing postgres-plugin code mutates `/etc/postgresql/<v>/main/pg_hba.conf` and `postgresql.conf` at addon-provisioning time, then calls `sudo -n systemctl reload postgresql`. This fails silently in production: hop3 can't write the config files, the operation is wrapped in a try/except, and the sudo NOPASSWD entry isn't even granted in the installer's sudoers fragment. The right answer is to move the config mutation to install time (where the installer runs as root) and make the addon's runtime code pure SQL: `CREATE USER`, `CREATE DATABASE`, `GRANT`. After that rework, the postgres addon needs zero privileged operations and never enters rootd. This is a separate installer task.

**Why caddy / traefik reload are follow-on, copying the work to two more proxy plugins inflates the initial scope. The state for those proxies is broken anyway: their sudo-based reload calls fail silently because the installer never granted NOPASSWD entries for them, leaving operators reliant on each proxy's own config-file watcher (caddy) or on manual reload (traefik). Routing their reloads through rootd is deferred to a follow-on release, which leaves caddy / traefik users no worse off in the interim.

**Future operations (informative)**: `package.ensure_installed`, `cert.request` / `cert.renew`, `systemd.reload(unit)`, `namespace.create_for_app(...)`: each is a separate ADR revision with its own threat model. Section 16 is the running list.

### 3. IPC: JSON over a Unix socket

The daemon listens on `/run/hop3-rootd/socket`, owned by root, mode `0660`, group `hop3`. Any process running as the `hop3` user can connect; processes under any other UID are rejected at accept time.

**Caller authentication** uses `SO_PEERCRED`: the kernel-provided peer-credentials mechanism. The daemon reads the connecting peer's UID directly from the socket and admits only `hop3` (and optionally `root`, for diagnostic / admin tools). No tokens, passwords, or shared secrets. The kernel's UID enforcement is the entire auth model.

**Wire framing** is line-delimited JSON: one JSON object per line, terminated with `\n`. Both sides write `json.dumps(obj) + "\n"` and read with `socket.makefile().readline()`. No length prefix, no streaming, no chunking. All payloads are small (≤2KB even with verbose audit context); JSON objects don't contain literal newlines (the JSON encoder escapes them).

**Request envelope**:
```json
{"v": 1, "id": "<uuid4>", "op": "firewall.add_rule", "args": {...}}
```

**Response envelope (success)**:
```json
{"v": 1, "id": "<uuid4>", "ok": true, "result": {...}}
```

**Response envelope (error)**:
```json
{"v": 1, "id": "<uuid4>", "ok": false, "error": {"code": "...", "message": "..."}}
```

Field semantics:

- `v`: protocol version (integer, currently `1`). Required on every message. Mismatch on a non-handshake message → connection closed with `protocol_version_mismatch`.
- `id`: UUID4 string supplied by hop3-server, echoed verbatim. Used to correlate request ↔ response in the audit log. The daemon does not generate or validate ids beyond "must be a non-empty string"; hop3-server is responsible for uniqueness within its context.
- `op`: request only. String, dotted form (`firewall.add_rule`).
- `args`: request only. Object. Op-specific; validated per-op.
- `ok`: response only. Boolean.
- `result`: response only. Op-specific success payload. Always an object (`{}` for ops with no data). Mutually exclusive with `error`.
- `error`: response only. Object with `code` (machine-readable) and `message` (human-readable). Mutually exclusive with `result`.

**Error codes** (fixed enum):

| code | meaning |
|---|---|
| `protocol_version_mismatch` | client `v` doesn't match daemon's protocol version |
| `unknown_op` | the requested `op` doesn't exist |
| `malformed_request` | request can't be parsed (missing fields, wrong types) |
| `validation_failed` | `args` failed structural validation; `message` describes the field |
| `state_conflict` | e.g., remove non-existent rule, add an already-present rule |
| `kernel_error` | nftables / nginx invocation failed; `message` carries stderr |
| `lockdown_active` | reserved for a future emergency-lockdown mechanism |
| `internal_error` | catch-all for daemon bugs; `message` is opaque to clients |

New codes are added per op as ops are added. Adding a new code is part of the protocol contract and is documented in the daemon's `protocol.py`.

**Handshake**. The first request on every connection is `daemon.handshake({client_version, client_protocol_version})`. Response carries `{daemon_version, protocol_version, accepted: true}`. Mismatch returns `protocol_version_mismatch` with a concrete remediation message ("upgrade hop3-rootd to >= 0.7.0"); hop3-server fails the deploy with a "version mismatch: re-run hop3-install server" diagnostic. No further messages on that connection.

The choice of plain JSON-over-UDS rather than gRPC, D-Bus, or HTTP is deliberate: minimal dependencies (stdlib only), trivial to test, easy to read on the wire (`nc -U /run/hop3-rootd/socket` from a root shell), easy to audit. The protocol is conservative on purpose; anything we add later is a separate decision.

### 4. Schema for the firewall op

[ADR 045](./045-fixed-port-registry.md) settles the developer-facing schema in `hop3.toml`: a `[[ports]]` array whose entries declare the fixed host ports an app binds directly.

```toml
[[ports]]
number = 8448         # the fixed host port
protocol = "tcp"      # "tcp" | "udp"
name = "federation"   # optional label, useful for the audit log + prompt
```

The bind address is implicit: apps bind loopback (`127.0.0.1`) internally per Hop3 convention; the firewall handles external traffic. There is no `bind = "0.0.0.0"` knob. "Exposed" means "all interfaces" by definition. [ADR 045](./045-fixed-port-registry.md) owns the registry side: a host-wide `PortClaim` table enforces "exactly one app per `(number, protocol)`", and on a successful deploy `open_fixed_ports` calls `firewall.add_rule` via the rootd client (storing the returned `rule_id`), while teardown's `release_fixed_ports` calls `firewall.remove_rule`. This ADR owns the rootd ops those calls land on.

Translating to rootd's `firewall.add_rule(spec)`:

```json
{
  "port": 8448,                        // or "port_range": [49152, 65535]
  "protocol": "tcp",                   // "tcp" | "udp"
  "source": "any",                     // "any" or IPv4 CIDR (v1)
  "app_name": "matrix-1",              // who owns this rule
  "description": "matrix federation"   // optional, for audit log + prompt
}
```

Rootd's structural validation:

- `port`: int, 1-65535. Privileged ports (<1024) accepted: no policy gating per the no-policy decision. XOR with `port_range`.
- `port_range`: array of two ints, `start <= end`, `end <= 65535`, `end - start <= 16384` (per [ADR 040](./040-network-firewall-and-port-exposure.md) cap to prevent denial-of-firewall via a million-rule explosion).
- `protocol`: literal `"tcp"` or `"udp"`. Reject anything else with `validation_failed`.
- `source`: `"any"` or a parseable IPv4 CIDR (use stdlib `ipaddress.ip_network`). IPv4 only: IPv6 CIDR rejected with a clear "IPv6 sources not supported" error.
- `app_name`: non-empty string, matches `^[a-z][a-z0-9-]{0,62}$` (defense in depth: caller is hop3-server which validates upstream).
- `description`: optional string, ≤200 chars, no control characters.

Response: a `Rule` object:

```json
{
  "rule_id": "rule-7f3a-...",          // UUID4, daemon-generated
  "spec": { ... },                     // echoed request, normalized
  "applied_at": "2026-04-24T15:30:00Z",
  "nft_handle": 47,                    // nftables' own handle
  "table": "inet hop3"                 // dedicated table, see §6
}
```

`rule_id` is the rootd-stable identifier; callers use it for `remove_rule(rule_id)`. `nft_handle` is an implementation detail surfaced for diagnostics: it changes across reloads, so callers shouldn't store it.

`firewall.list_rules({app_name?})` returns `{"rules": [<Rule>, ...]}` with optional filtering.

**IPv6**: destinations are auto-handled (nftables `inet` family covers v4 + v6 simultaneously: adding a TCP/8448 accept rule allows both IPv4 and IPv6 inbound traffic to that port). Source filtering on IPv6 CIDRs is not supported; for typical "expose to the internet" (`source = "any"`), v6 just works.

#### Validation discipline (three layers, intentionally redundant)

1. **`Hop3TomlSchema` in hop3-server**: Pydantic schema for `[[ports]]` entries ([ADR 045](./045-fixed-port-registry.md)), via a `PortEntry` model. Fails the deploy at `hop3.toml` parse time if the app's declaration is malformed. Same place where `TestValidation`'s `status_in` lives.
2. **hop3-server's CompositeFirewall plugin**: Translates a `[[ports]]` entry → rootd request. Catches "port already held by another app" via the `PortClaim` registry (see §5 and [ADR 045](./045-fixed-port-registry.md)).
3. **rootd-side validator**: Re-validates the wire format. Defense in depth: catches anything that slipped past hop3-server, plus catches a hypothetical second client.

The redundancy is deliberate. Each layer has a different threat model: layer 1 catches developer typos with the best error messages; layer 2 catches cross-app conflicts only the server can know about; layer 3 catches hop3-server bugs (or compromise) before they touch the kernel.

#### Cloud-API alignment

The schema is a deliberately-narrow subset of cloud-provider firewall APIs (Hetzner, AWS SG, DigitalOcean, Scaleway). Common fields map 1:1 (protocol, port, source CIDR, description). Intentional omissions:

- **`direction` is implicit `in`**: no outbound rules.
- **`source` is single-valued**: multi-source rules are expressed as multiple rootd `add_rule` calls. Cloud-side translation may compose them into a single rule with a source list (Hetzner allows this); rootd-internally they're separate rules.
- **Protocols restricted to tcp/udp**: ICMP/ESP/GRE rejected. None of our catalog apps need them.

Cloud-firewall plugins translate between rootd's typed shape and the provider's wire format: a thin function (≤20 lines per provider). No impedance mismatch.

### 5. Plugin architecture: `Firewall` protocol

Hop3-server sees a single `Firewall` protocol; the cloud-vs-local distinction is hidden by the plugin layer:

```python
class Firewall(Protocol):
    def grant(self, spec: PortSpec) -> Grant: ...
    def revoke(self, grant_id: str) -> None: ...
    def list(self) -> list[Grant]: ...

class LocalNftablesFirewall:
    """Talks to hop3-rootd via /run/hop3-rootd/socket."""
    def grant(self, spec): return self._rpc("firewall.add_rule", spec)

class HetznerCloudFirewall:
    """Talks to api.hetzner.cloud with the operator's token."""
    def grant(self, spec): return self._http_post("/firewalls/.../rules", spec)

class CompositeFirewall:
    """Apply to all backends; all-or-nothing on grant, best-effort on revoke."""
```

**CompositeFirewall failure semantics**:

- **Grant**: applied in declared backend order (`local-nftables`, then `hetzner-cloud`). On any failure, previously-applied backends are revoked in reverse order; the original error is raised. **All-or-nothing.** A partial grant is never observable by the caller.
- **Revoke**: applied in reverse declared order. On failure, log loudly and **continue** to the next backend, then raise after all attempts. **Best-effort.** A partial revoke is worse than refusing, because leaving a "cloud-permitted but locally-blocked" port is the safer state (the port becomes unreachable, which matches operator intent).

#### Backend selection

The operator declares backends explicitly in `/home/hop3/hop3-server.toml`:

```toml
HOP3_FIREWALL_BACKENDS = "local-nftables,hetzner-cloud"
HETZNER_FIREWALL_TOKEN = "..."
HETZNER_FIREWALL_ID = "1234567"
```

Default if unset: `"local-nftables"`. The installer can suggest enabling `hetzner-cloud` at install time when it detects Hetzner cloud-metadata; no runtime auto-detection. Missing required credentials for a declared backend (`HETZNER_FIREWALL_TOKEN` unset while `hetzner-cloud` is in the list) → hop3-server fails at startup with a clear diagnostic. **No silent downgrade.**

Credentials in `hop3-server.toml` are read at hop3-server startup only. Rotation requires `sudo systemctl restart hop3-server`. Lazy reload is rejected as adding subtle behavior without enough payoff. The whole `hop3-server.toml` schema deserves its own ADR: sectioning, validation, doc-vs-reality alignment (the current administration guide describes a sectioned format that doesn't match the actual flat-key loader). This ADR extends the existing flat-key format with new keys; the broader redesign is deferred to that ADR.

### 6. Reconciliation, the dedicated table, the operator contract

#### How rootd identifies "its" rules

Rootd creates and exclusively owns an nftables table named `hop3` in the `inet` family: `nft add table inet hop3`. All rootd-managed rules go in this table. Foreign rules in other tables (`inet filter`, distro defaults, anything else) are by definition not rootd-managed: rootd never reads or writes them.

This gives a clean namespace separation. Survives reload (the table is persistent until explicitly deleted). nftables natively supports multiple independent tables: this is what they're for. The alternative approaches (per-rule comment markers, kernel-handle-as-id) are more brittle.

This also implies **nftables-only support**. ufw is a frontend over iptables/nftables; modern Debian's ufw uses nftables underneath. Fedora's firewalld uses nftables underneath. nftables-direct is the lowest common denominator and the best-defined API. ufw / firewalld as alternative implementations are a follow-on if real demand surfaces.

#### Startup reconciliation

On startup, rootd reads `state.json`, queries the kernel for rules in `inet hop3`, then reconciles:

- **Rule in state AND in kernel, same spec** → no-op, log a "verified" line.
- **Rule in state, NOT in kernel** → re-apply (kernel was reloaded or rules flushed). Log loudly.
- **Rule in kernel (in `inet hop3`), NOT in state** → remove it. It's "ours" by virtue of being in our table; if state doesn't know about it, it's stale from a previous run that crashed before persisting state.
- **Rule in state with one spec, in kernel with a different spec** → kernel wins, state is updated to match. Log a warning. (Rare; indicates manual intervention.)
- **`state.json` missing or corrupt** → daemon refuses to start. Operator must intervene (rename it aside, restart). The conservative default: never silently drop rules.

Anything outside the `inet hop3` table is invisible to rootd. Operator's `inet filter` rules, distro defaults, anything else: never touched, never inspected.

**No periodic reconciliation.** Drift causes are narrow (kernel reload at host reboot (handled at startup; `nft flush`-by-mistake) operator intervention; package update touching nftables: rare). Periodic checks add a timer thread, more state mutation, more code paths to test. If real drift becomes a problem, periodic is one config flag away.

#### The operator contract

**Hop3 manages the server; the operator manages Hop3.** The operator's legitimate actions are: install, upgrade, configure (edit `/home/hop3/hop3-server.toml`), start/stop services, audit logs and rules. Direct manual mutation of state Hop3 manages (e.g., editing `/etc/postgresql/.../pg_hba.conf` while postgres is a Hop3-managed addon, or running `nft flush table inet hop3` while rootd is alive) is unsupported. Caveat emptor.

This principle simplifies everything downstream: rootd's reconciliation is more aggressive than it would otherwise need to be (rules in our table not in our state get removed, no questions asked); future ops (nginx config, certbot, package install) follow the same discipline; the audit log doesn't need to handle "what if the operator did X out-of-band" branches.

### 7. Concurrency and atomicity

#### Concurrency: single-threaded daemon, multi-connection accept

The daemon accepts multiple connections concurrently (via `select` / `epoll`) but processes requests one at a time from a single FIFO queue. No concurrency *within* the daemon; no shared-state locking required.

- Firewall and nginx ops are fast (sub-second each). Serial throughput is sufficient for realistic Hop3 workloads (deploys are one-at-a-time in the common case; even with N=2 concurrent deploys, worst-case queue depth is ~1 second).
- `nft` itself is essentially serial: concurrent `nft add rule` invocations can race at the netlink layer even with `CAP_NET_ADMIN`. Serializing at the daemon level matches the underlying kernel constraint.
- Single-threaded processing makes the daemon's correctness story simple to audit. No locks in a privileged daemon is a real audit-cost win.

If contention becomes a problem in some future high-throughput scenario, upgrading to per-resource locking (firewall lock vs nginx lock) is mechanical. The protocol surface doesn't change.

#### Atomicity: state-first, apply-second, rollback on failure

When `firewall.add_rule(spec)` is called:

1. Generate a `rule_id` (UUID4).
2. Append `{rule_id, spec, status: "pending"}` to in-memory state.
3. Persist `state.json`.
4. Run `nft add rule …`.
5. On success: mark state row `status: "applied"`, persist again. Return `rule_id`.
6. On failure: delete the state row, persist, return `kernel_error` with stderr.

The daemon's view of the world is always a superset of reality (we may know about a rule we couldn't apply, but never the reverse). On startup reconciliation, applied-state rules missing from the kernel are re-applied.

For `firewall.remove_rule`, mirror image: mark state `status: "removing"`, run `nft delete rule …`, on success delete state row, on failure revert state to `applied`.

For `nginx.reload`: nginx itself does graceful reload. Daemon shells out, captures the result, returns. No daemon state tracked for nginx ops.

**Multi-rule semantics**: rootd exposes single-rule ops only. If a caller wants 5 rules added atomically, it makes 5 calls and rolls back its own state on the first failure. A `firewall.add_rules([...])` batch op with all-or-nothing semantics is deferred.

### 8. Failure-mode coupling with the deployer

When `hop3 deploy myapp` runs, the firewall step runs *after* the app is built and started. If grant fails, the app is RUNNING but ports aren't open: a "deployed but degraded" state.

**Rule: the deploy fails and the app is rolled back.**

1. CompositeFirewall already gives all-or-nothing at the firewall level (any partial grants get revoked).
2. Hop3-server then stops the app (sends SIGTERM to the uwsgi vassal, removes from `uwsgi-enabled/`).
3. Nginx config is removed (the app's vhost file under `/home/hop3/nginx/`).
4. App's ORM state goes back to whatever it was before (or `STOPPED` if first deploy).
5. Build artifacts (nix store, venv, source tree) are **not** rolled back: those are accumulating state. Failed deploys leave them on disk for the next attempt.

The operator's mental model: "deploy failed; the app isn't running; firewall is unchanged; my source is on disk; retry is safe."

**Why this is stricter than nginx-reload's existing soft-failure**: nginx reload failure is benign (old config still serves). Firewall failure is fundamental: the app's *contract* (these ports are reachable) is broken. They deserve different handling.

Build artifacts are not garbage-collected eagerly; they accumulate until the operator runs `hop3 app destroy` or some future cleanup command.

### 9. CLI deploy-time prompt

Confirmation lives in the CLI and web UI. Before `hop3 deploy` actually invokes rootd, it shows a summary of privileged changes about to happen.

#### When the prompt fires

**Only when the privileged-op set differs from the previous deploy of this app** (delta-only). Routine code updates with no `[[ports]]` changes proceed silently. First deploy of an app with `[[ports]]` declarations triggers the prompt for the full set. Re-deploy with one port added → prompts for the addition. Re-deploy with one port removed → prompts for the revoke.

Diff is computed by comparing the new app's `[[ports]]` set against the rules currently held for that app in rootd's state (via `firewall.list_rules({app_name})`).

Nginx reload doesn't trigger the prompt: it's part of every web deploy and would create noise.

#### Summary format

```
$ hop3 deploy matrix
Deploying matrix from /home/me/matrix.
  Build: nix-gen (matrix-synapse@2.13.1)

This deploy will change the firewall:
  + open  tcp/8448 on 0.0.0.0      (matrix federation)
  + open  udp/49152-65535 on 0.0.0.0  (matrix TURN media relay)
  - close tcp/9418 on 0.0.0.0      (was: previous git-protocol port)

Backends affected: local-nftables, hetzner-cloud.

Proceed? [y/N]:
```

#### Non-interactive flows

- `hop3 deploy --yes matrix` (or `-y`) skips the prompt, proceeds (per [ADR 036](./036-cli-ergonomics.md)'s `-y` flag).
- `HOP3_NO_INPUT=1` env var equivalent (per [ADR 036](./036-cli-ergonomics.md)).
- If the operator says `n`: deploy aborts before any privileged action; exit code **10** ("confirmation declined", per [ADR 036](./036-cli-ergonomics.md) D16). Build artifacts stay on disk; nothing else changes.
- `--no-input` mode that *would* have prompted → fails immediately with exit code **13** ("input required, none available") and a message naming the flag/env var to set.
- Ctrl-C during prompt → exit **130** (SIGINT, per D16).

#### Where the prompt runs

In the CLI client. The flow:

1. `hop3 deploy` calls a **dry-run RPC** that returns the proposed grant-set delta.
2. CLI computes and prints the summary, prompts y/N locally.
3. On `y`, CLI sends the **actual deploy RPC** with `confirmed=true`.

The dry-run RPC is read-only; the deploy RPC is the only mutating call. Cleaner than keeping a deploy session open mid-execution.

### 10. Systemd units and hardening

The daemon ships with two systemd units: a `.service` and a `.socket`. The socket unit holds the bound `/run/hop3-rootd/socket` across daemon restarts: clients see at most a brief pause on `Restart=on-failure`.

#### `hop3-rootd.socket`

```ini
[Unit]
Description=Hop3 privileged operations daemon: socket
PartOf=hop3-rootd.service

[Socket]
ListenStream=/run/hop3-rootd/socket
SocketMode=0660
SocketUser=root
SocketGroup=hop3
RemoveOnStop=true

[Install]
WantedBy=sockets.target
```

#### `hop3-rootd.service`

```ini
[Unit]
Description=Hop3 privileged operations daemon
Documentation=https://github.com/abilian/hop3/blob/main/notes/adrs/041-privileged-operations-agent.md
Requires=hop3-rootd.socket
After=hop3-rootd.socket network.target

[Service]
Type=notify
ExecStart=/opt/hop3-rootd/bin/hop3-rootd
Restart=on-failure
RestartSec=2s

# --- Capability scoping ---
# nft needs CAP_NET_ADMIN; nothing else.
User=root
CapabilityBoundingSet=CAP_NET_ADMIN
AmbientCapabilities=CAP_NET_ADMIN
NoNewPrivileges=true

# --- Filesystem isolation ---
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/hop3-rootd /var/log/hop3-rootd
PrivateTmp=true
PrivateDevices=true
PrivateMounts=true

# --- Kernel surface ---
ProtectKernelModules=true
ProtectKernelTunables=true
ProtectKernelLogs=true
ProtectClock=true
ProtectHostname=true
ProtectProc=invisible
ProtectControlGroups=true
LockPersonality=true
MemoryDenyWriteExecute=true
RestrictNamespaces=true
RestrictRealtime=true
RestrictSUIDSGID=true

# --- Network surface ---
RestrictAddressFamilies=AF_UNIX AF_NETLINK
IPAddressDeny=any
# (no IPAddressAllow: rootd never makes outbound network calls; cloud
# providers are reached only by hop3-server.)

# --- Syscall filter ---
SystemCallFilter=@system-service @network-io
SystemCallFilter=~@privileged @resources @debug @cpu-emulation @keyring
SystemCallErrorNumber=EPERM
SystemCallArchitectures=native

# --- Resource limits ---
MemoryMax=128M
TasksMax=16
LimitNOFILE=1024

# --- Directories ---
RuntimeDirectory=hop3-rootd
RuntimeDirectoryMode=0755
StateDirectory=hop3-rootd
StateDirectoryMode=0700
LogsDirectory=hop3-rootd
LogsDirectoryMode=0700

[Install]
WantedBy=multi-user.target
```

Rationale for the less-obvious knobs:

- `User=root` is required (nftables needs `CAP_NET_ADMIN`, which can't be granted to a non-root user without it being on the daemon binary: and we don't want a setuid Python daemon).
- `CapabilityBoundingSet=CAP_NET_ADMIN` drops all other root capabilities. The daemon can't load kernel modules, can't read arbitrary files, can't bind privileged ports for new sockets. Just nftables.
- `AmbientCapabilities=CAP_NET_ADMIN` propagates that one capability to the `nft` subprocess so it can do its job.
- `NoNewPrivileges=true` blocks any setuid/setgid escalation in subprocesses. Defense against bugs in the subprocess wrapper.
- `ProtectSystem=strict` makes everything read-only except `ReadWritePaths`. Rootd can only write to its own state and log directories.
- `RestrictAddressFamilies=AF_UNIX AF_NETLINK` blocks the daemon from creating TCP/UDP sockets at all. AF_UNIX for IPC, AF_NETLINK for nftables.
- `IPAddressDeny=any` belt-and-suspenders: even if AF_INET sockets were created, all packets are dropped. Rootd never talks to anything except the kernel and hop3-server.
- `SystemCallFilter=@system-service @network-io` is the seccomp filter. The deny-list strips dangerous classes (`@privileged` for `setuid`/`mount`, `@resources` for `setrlimit`/`setpriority`).
- `MemoryMax=128M` caps process memory. The daemon should fit comfortably under 32M; 128M is generous headroom.
- `TasksMax=16`: single-threaded plus subprocess shell-outs. 16 is plenty; 200+ would indicate a bug.

Some directives need systemd 244+ (released 2019). Hop3's installer targets Debian 12 (systemd 252) and Fedora 38+ (systemd 254+), well past that.

### 11. Versioning

**Lockstep versioning, strict handshake.** hop3-server, hop3-cli, hop3-installer, hop3-tui already release together at the same version; hop3-rootd joins the set. All binaries are versioned `0.6.0`, `0.7.0`, etc.

The handshake (§3) is exact-match: hop3-server sends `{client_version, protocol_version}`; rootd accepts iff `protocol_version` matches. Skew → connection rejected. Hop3-server surfaces "version mismatch: re-run `hop3-install server`".

The installer's atomic upgrade flow replaces both binaries in the same step (stop services → install new files → start services). The window where mismatch can occur is the seconds between stopping one service and starting the new one; in practice the handshake fails on the first deploy attempt during that window, which is acceptable.

`protocol_version` is a single integer (start at `1`). It bumps when the wire protocol changes incompatibly. Adding new ops doesn't bump it (hop3-server gates new-op usage by `client_version`).

### 12. Sudoers fragment retirement (migration)

The existing `/etc/sudoers.d/hop3` fragment grants the hop3 user NOPASSWD access to four nginx commands. Because rootd routes nginx reload, the fragment is retired in the same release that introduces rootd.

**On fresh install** (`hop3-install server` on a new host): the installer drops the fragment-creation step (`server_installer/nginx.py::setup_sudoers` becomes a no-op). hop3-rootd is installed; hop3-server uses it for nginx ops from day one.

**On upgrade** (existing host moving to the version that introduces rootd):

1. Installer detects existing `/etc/sudoers.d/hop3`.
2. Logs notice: "migrating nginx-reload from sudoers fragment to hop3-rootd".
3. Installs hop3-rootd binaries, units, state directory.
4. Stops `hop3-server`.
5. Starts `hop3-rootd`, waits for ready notify.
6. Deletes `/etc/sudoers.d/hop3`.
7. Starts `hop3-server` on the new code (which uses rootd for nginx).

If the upgrade fails between steps 5 and 7, the system is in a clean state: hop3-rootd running, sudoers fragment still present, hop3-server stopped. Operator can roll back hop3-server's binary or retry the upgrade. Step 6 is the point of no return; placing it after step 5 ensures rootd is up and tested before we remove the fallback.

Caddy and Traefik proxy plugins are not addressed by this migration. Their sudo-based reload calls have no working NOPASSWD entries (those NOPASSWD lines were never in the installer's sudoers fragment); the calls fail silently with a warning, and operators rely on each proxy's own mechanism (caddy's file watcher, traefik's file provider). A follow-on release retires those calls in favour of rootd ops, at which point caddy / traefik installations gain the same single-trust-boundary property as nginx.

### 13. State, restart, observability

#### State file

Persistent state at `/var/lib/hop3-rootd/state.json` (mode 0600, root-owned):

```json
{
  "version": 1,
  "rules": [
    {
      "rule_id": "rule-7f3a-...",
      "spec": {...},
      "applied_at": "2026-04-24T15:30:00Z",
      "status": "applied"
    },
    ...
  ]
}
```

The daemon updates the file atomically (write to `state.json.tmp`, fsync, rename). Corrupt or missing → daemon refuses to start.

#### Logging

**Two log streams.**

1. **Operational logs → journald** via systemd's automatic capture. Captures every request, every response, every error, structured. `journalctl -u hop3-rootd` is the operator's first stop. Retention managed by journald's own config.
2. **Append-only audit log → `/var/log/hop3-rootd/audit.log`** (mode 0640, group hop3: directly readable by hop3-server). One JSON line per request:
   ```json
   {"ts":"2026-04-24T15:30:00Z","request_id":"...","op":"firewall.add_rule",
    "args":{...},"outcome":"applied","duration_ms":12,"caller_uid":1000}
   ```

The audit log is hop3-readable so `hop3 firewall history` (a hop3-server CLI command) can read it directly without going through rootd. Daemon writes; hop3-server reads.

**Logrotate** at `/etc/logrotate.d/hop3-rootd`: daily rotation, 90-day retention, gzip after one day. SIGUSR1 to the daemon to reopen the file. 90 days matches typical compliance requirements; operator can edit.

#### Restart safety

`Restart=on-failure`, `RestartSec=2s` in the systemd unit. The `.socket` unit holds the bound socket so in-flight clients see at most a short pause. State persists; on restart, reconciliation re-syncs with the kernel.

If `state.json` is missing or corrupt at startup, the daemon refuses to start. Operator must intervene: rename the corrupt file aside, restart. The conservative default: never silently drop the daemon's view of the world.

### 14. Distribution and install

`hop3-installer` (root, install-time) installs:

- The `hop3-rootd` Python package under `/opt/hop3-rootd/` (sibling of where hop3-server lives: pure stdlib, no external deps).
- Systemd units: `/etc/systemd/system/hop3-rootd.service`, `/etc/systemd/system/hop3-rootd.socket`.
- Logrotate config: `/etc/logrotate.d/hop3-rootd`.
- Initial state: `/var/lib/hop3-rootd/state.json` with `{"version":1,"rules":[]}`.
- Initial nftables table: `nft add table inet hop3` (empty).

**Fresh install order**:

1. System packages (apt/dnf), including `nftables`.
2. hop3 user/group created.
3. hop3-rootd files dropped.
4. Initial state and table created.
5. `systemctl daemon-reload && systemctl enable --now hop3-rootd.socket hop3-rootd.service`.
6. hop3-server installed.
7. hop3-server config (`/home/hop3/hop3-server.toml`) written with `HOP3_FIREWALL_BACKENDS = "local-nftables"` (default).
8. `systemctl enable --now hop3-server`.

**Upgrade order** (from the previous Hop3 version that didn't have rootd):

1. System packages updated.
2. `systemctl stop hop3-server` (stop in-flight RPCs).
3. `systemctl stop hop3-rootd` if it exists (no clients left).
4. New binaries replace old ones.
5. State migration if `state.json` schema changed (rare).
6. `systemctl start hop3-rootd`, wait for ready notify.
7. Delete `/etc/sudoers.d/hop3` (per §12).
8. `systemctl start hop3-server`.

Top-down stop, bottom-up start: same as any service-with-dependency.

### 15. Test infrastructure

Four test layers, mirroring hop3-server's existing convention:

#### a_unit (no privileges, no nft)

`packages/hop3-rootd/tests/a_unit/`: pure Python, runs anywhere.

- **Protocol** (`test_protocol.py`): JSON framing roundtrips, handshake variants, error envelope shapes, request_id echoing.
- **Validation** (`test_validation.py`): each field: port bounds, port_range cap, protocol literal, source CIDR parse + IPv6 rejection, app_name regex, description length.
- **Dispatcher** (`test_dispatcher.py`): given a parsed request, the right op handler is invoked; unknown op returns `unknown_op`; well-formed but invalid args return `validation_failed`.
- **Audit log writer** (`test_audit.py`): JSON-line format, atomic write, SIGUSR1 file reopen.

#### a_unit op-mock

Same directory, specific to `firewall.*` and `nginx.*`. The subprocess wrapper from `exec.py` is mocked so calls to `nft` / `nginx` are captured and asserted against without invoking the real tools.

#### b_integration (root + real nftables)

`packages/hop3-rootd/tests/b_integration/`. Skipped unless running as root with `nft` available. Operates only on the `inet hop3` table: never touches anything else. Creates, exercises, tears down per-test.

Skipped in unprivileged CI; runs in the Docker test target (which is already root inside the container).

#### c_system (full stack via deployment_target)

`packages/hop3-server/tests/c_system/test_firewall.py`: extends the existing `deployment_target` fixture. Container is built with hop3-rootd installed; both services start; tests deploy an app with `[[ports]]` declarations via the RPC interface; assertions cover kernel state and audit log.

The `deployment_target` fixture is updated to:

- Install `nftables` and `iproute2` in the container build.
- Start `hop3-rootd.service` before `hop3-server.service`.
- Provide a `hop3_rootd_state(target)` helper returning parsed `state.json` and `nft list table inet hop3` for assertions.

#### Skipping discipline

```python
@pytest.fixture
def root_with_nftables():
    if os.geteuid() != 0:
        pytest.skip("requires root")
    if shutil.which("nft") is None:
        pytest.skip("requires nftables")
    yield
```

Skipped tests are visible in `pytest -v` output. No silent passes.

#### Test isolation

`b_integration` tests are serial within a worker (each creates and tears down its own table; pytest-xdist parallelism would conflict). `c_system` tests inherit `deployment_target`'s per-test isolation: already correct.

### 16. Future operations (informative)

The architecture is designed so future privileged operations slot in without protocol or trust changes. Likely next entries, in rough order of need:

1. **`package.ensure_installed(name, version?)`**: retires the installer-baseline workaround for runtime package needs.
2. **`cert.request(domain)` / `cert.renew(domain)`**: drives certbot / acme.sh from hop3-server lifecycle events.
3. **`systemd.reload(unit)` / `systemd.restart(unit)`**: replaces the caddy / traefik sudoers fallback; clean lifecycle for systemd-managed app units if/when those become a deployer option.
4. **`namespace.create_for_app(...)`**: only relevant if Hop3 ever introduces per-app network namespaces (a much larger change; out of scope for now, but the daemon would be the right place).

Each addition is a separate ADR revision with its own threat model and expanded error-code taxonomy. None belong to the baseline scope. (The first such additions (`cgroup.*` and `mount.*` for [ADR 046](./046-declarative-app-resources.md)) are specified in §18; the `proxy.*` addon-exposure family for [ADR 040](./040-network-firewall-and-port-exposure.md) is specified in §19.)

### 17. Connection to [ADR 017](./017-agent-based-architecture.md) (agent-based architecture)

[ADR 017](./017-agent-based-architecture.md) describes an agent abstraction with three phases: a self-healing watchdog (Phase 1), extraction into a `LocalAgent` class (Phase 2), and multi-node coordination (Phase 3). There is a real question about whether `hop3-rootd` *is* the LocalAgent.

**Decision: they are separate daemons with separate responsibilities.**

- [ADR 017](./017-agent-based-architecture.md)'s LocalAgent is mostly *unprivileged* work: poll uwsgi state, hit HTTP healthchecks, write to the audit log, decide that an app is dead, ask the deployer to restart it. None of this needs root. It runs as the `hop3` user (probably inside hop3-server, possibly as a sidecar process).
- `hop3-rootd` is purely about crossing the kernel privilege boundary. Its trust budget is "as small as possible". Adding "decide which apps are unhealthy" to that budget is a strict downgrade.

The two daemons compose: when [ADR 017](./017-agent-based-architecture.md)'s watchdog decides an app needs a privileged action (e.g., reload nginx because the app's config changed), it asks hop3-server, which asks hop3-rootd. The trust boundary is in exactly one place.

For [ADR 017](./017-agent-based-architecture.md) Phase 3 (multi-node), each node ships its own `hop3-rootd` and its own watchdog. The coordinator talks to a node's watchdog; the watchdog's privileged calls go through that node's rootd. The mental model ("control plane talks to per-node agents") applies at both levels.

### 18. Amendment: `cgroup.*` and `mount.*` op families ([ADR 046](./046-declarative-app-resources.md))

Native `[limits]` enforcement and native `[[volumes]]` ([ADR 046](./046-declarative-app-resources.md)) need privileged kernel operations beyond `firewall.*` / `nginx.*` / `daemon.*`. Per §16 they are introduced as **one** amendment: the two families share a trust budget, a validation surface, and a state discipline, and amending the hardened unit twice independently would risk one change silently weakening the other's threat model.

**Op families** (registered, dispatched, and audited like the other ops; kernel failures map to `kernel_error`):

- **`cgroup.*`** (native `[limits]`, [ADR 046](./046-declarative-app-resources.md) §3): `ensure_slice`, `set_limits`, `attach_pids`, `remove`, `read`. A per-app cgroup v2 leaf at `hop3.slice/hop3-app-<name>.scope` carries `memory.max` (with `memory.swap.max=0`, so a cap is a real cap), `cpu.max`, and `pids.max`; `attach_pids` migrates the app's PIDs in; `remove` kills the subtree then rmdirs (a stronger reap surface than `/proc` scanning, including a Nix-store `exec`'d daemon); `read` exposes usage and the `oom_kill` count for `hop3 app status`.
- **`mount.*`** (native `[[volumes]]`, [ADR 046](./046-declarative-app-resources.md) §2): `tmpfs`, `bind`, `unmount`, `list`. `tmpfs` is a sized RAM scratch mount; `bind` attaches an operator-allow-listed host source (default-deny, realpath-checked); both invoke `mount(8)` / `umount(8)` from the exec allow-list. `list` is the teardown-verification surface.

**One contract, hence one amendment:**

- *One path-allow-list.* rootd derives `APP_ROOT` from the hop3 user's home and validates `app_name` (the existing validator); every mountpoint/leaf must canonicalize under `<APP_ROOT>/<app>/src` resp. `hop3.slice/hop3-app-<app>.scope`. Callers pass `app_name` and a *relative* target, never an absolute path (§1).
- *One state discipline.* Cgroup leaves and mounts join `state.json` under the same atomic-write + startup-reconcile model as firewall rules (parsed optionally, so older state still loads); a host that cannot enforce degrades loudly rather than crashing the daemon, mirroring the nft-missing path.
- *One bind allow-list.* rootd holds its own copy (`/var/lib/hop3-rootd/bind-allowlist`, default-deny) as the third validation layer (§4), kept in sync by the installer with the server-side `HOP3_BIND_VOLUME_ALLOWLIST`. This allow-list is the real control on `mount.bind` and is conservative by default; an installer-time check confirms the host provides cgroup v2.

**Unit-hardening threat model.** These ops are incompatible with two of §10's sandbox directives. Writing the cgroup hierarchy requires `ProtectControlGroups` unset (or `hop3.slice` delegated via `Delegate=`), with `ReadWritePaths` scoped to exactly that subtree. Mounting into the app's namespace requires `CAP_SYS_ADMIN` and the host mount namespace (no `PrivateMounts`; `MountFlags=shared`) (essential, because a mount made in rootd's *private* namespace is invisible to the Emperor-spawned app process: a "mounted successfully" report over an empty dir, i.e. silent success, which this architecture forbids. Reconciling §10's hardening with these requirements is a single forward constraint, threat-modelled as one change: the hardened unit keeps `CAP_SYS_ADMIN` and a shared mount namespace and leaves the cgroup subtree writable. This is a materially larger kernel surface than `CAP_NET_ADMIN`-only, accepted only with that scoping and the §1 framing) a hop3-server compromise is already total compromise of the hop3 user, and rootd's job is to not *widen* it.

**Guard discipline and fallback.** A realization is gated on its op: a guard that refuses a resource the platform cannot realize stays until the matching op is live, so no app deploys *looking* capped or persisted when it isn't. If this unit-hardening is not adopted, native `[limits]` / `tmpfs` / `bind` are infeasible and only the Docker paths are available: [ADR 046](./046-declarative-app-resources.md)'s guaranteed-deployable baseline.

The error-code taxonomy is unchanged (`validation_failed` / `kernel_error` / `state_conflict` cover both families), and the client surface stays `LocalRootdClient.call(op, args)`.

### 19. Amendment: `proxy.*` op family ([ADR 040](./040-network-firewall-and-port-exposure.md) addon exposure)

[ADR 040](./040-network-firewall-and-port-exposure.md) exposes an app's *own* fixed ports by opening the host firewall (`firewall.*`, §4): the app already binds `0.0.0.0` and the rule simply lets traffic through. A database **addon** is different: it binds `127.0.0.1` only (Hop3 convention, never `0.0.0.0`), so `hop3 addon expose` cannot be satisfied by a firewall rule alone. A rule on a public port would reach a closed socket. Making a loopback-only service reachable on a public host port needs a real forwarder, and creating one is a privileged act. Hence a third op family.

**Ops** (registered, dispatched, and audited like the others; `proxy.list` is read-only, `audit=False`):

```
proxy.add({addon_type, addon_name, public_port, target_port, source?}) -> {unit, public_port, target_port, ...}
proxy.remove({addon_type, addon_name}) -> {removed, unit}
proxy.list({addon_type?}) -> {proxies: [...]}
```

**Mechanism.** rootd realises each exposure as a per-addon `systemd-socket-proxyd` unit pair:

```
hop3-expose-<type>-<name>.socket    ListenStream=0.0.0.0:<public_port>
hop3-expose-<type>-<name>.service   ExecStart=…/systemd-socket-proxyd 127.0.0.1:<target_port>
```

rootd **never `exec`s the proxy binary itself.** It writes the two unit files (atomic write→fsync→rename, mode 0644, the same discipline as `state.json`) and drives the *units* through the already-allow-listed `systemctl` (`daemon-reload`, `enable --now`, `disable --now`, `stop`): exactly as `nginx.reload` drives `systemctl`, adding no new allow-listed binary beyond the `systemd-socket-proxyd` path baked into the rendered `ExecStart`.

**Containment (the §1 framing).**

- *Loopback-only destination.* The forwarder target host is hardcoded to `127.0.0.1`. This primitive can forward a public port to a *loopback* port and nothing else: never to an arbitrary internal host. It cannot become a general-purpose network relay.
- *No caller-supplied unit name.* The unit base name is composed **inside rootd** from a validated `addon_type` + `addon_name` (the §4 validators, reused). A raw systemd unit name is never accepted off the wire, so a caller can only ever act on a `hop3-expose-<type>-<name>` unit it owns: it cannot stop/disable an operator's units.
- *No secrets on disk.* A unit file carries only ports; no addon credential ever touches it.

**One state discipline (as §18).** Exposures are `StoredProxy` rows in `state.json` under the same atomic-write + startup-reconcile model as firewall rules. `reconcile_proxies` sweeps orphans by the §6 rule: a `hop3-expose-*` unit on disk with no matching state row is "ours" by naming and is removed (it is a leftover from a crashed expose). `proxy.list` is the teardown-verification surface: after `hop3 addon unexpose`, the server calls it and expects the unit gone. The error-code taxonomy is unchanged: `ProxyError` / `ProxyUnavailableError` → `kernel_error`, validation failures → `validation_failed`.

**Deploy coupling.** `hop3 addon expose` opens the firewall (`firewall.add_rule`) and then creates the forwarder (`proxy.add`) in one rootd session; a failure of either rolls the exposure back (the firewall grant is removed, the `PortClaim` row released): the all-or-nothing shape of §8, applied to addon exposure. Teardown drops the claim row first (so the host port is reclaimable even if rootd is down), then best-effort closes the firewall and removes the forwarder, with `reconcile_proxies` as the completeness backstop.

**Unit-hardening note.** Writing `/etc/systemd/system` and running `systemctl` is a materially larger surface than `CAP_NET_ADMIN`-only: the same forward constraint §18 records for `cgroup.*` / `mount.*`. The current unit runs with minimal sandboxing precisely because rootd is the privileged executor of several external tools (`nft`, `nginx`, `systemctl`) whose needs the heavy §10 profile could not jointly satisfy; a future hardening redesign must preserve `proxy.*`'s unit-file write and `systemctl` needs alongside the §18 ones. The client surface stays `LocalRootdClient.call(op, args)`.

## Consequences

### Positive

- **The kernel privilege boundary is in exactly one place**, with the smallest possible code surface. Future privileged ops do not each get their own escalation path.
- **The cloud-firewall analogy is structural**: hop3-server's `Firewall` plugin sees one protocol regardless of whether the backend is local-via-rootd or cloud-via-API.
- **The trust budget is explicit and reviewable**: hop3-rootd is a small Python package with a fixed operation set and no external dependencies.
- **Pre-figures [ADR 017](./017-agent-based-architecture.md) Phase 3** (multi-node): each node ships its own rootd; the same protocol shape extends.
- **Retires `/etc/sudoers.d/hop3`**: nginx-reload no longer needs a sudoers fragment.
- **Defends [ADR 040](./040-network-firewall-and-port-exposure.md)'s design choices**: per-port grants are now backed by a clean execution model rather than a sudoers fragment.
- **Explicit threat model**: the ADR names "hop3-server compromise = total compromise" rather than pretending to defend against it.

### Negative

- **One more daemon to install, monitor, and version** alongside hop3-server. The systemd unit is a new failure mode operators have to know about.
- **The daemon is the kernel boundary**: a bug in argument parsing or the firewall shell-out is a privilege-escalation bug. The bar for code review is higher than for hop3-server.
- **No authorization layer**: an operator cannot say "this box must never expose tcp/22 to the internet, regardless of what an app declares". Mitigation: the operator can stop hop3-rootd to lock down all firewall changes; for finer-grained policies, future ADR work.
- **Operator config edits require service restart**: rotating a Hetzner token or changing `HOP3_FIREWALL_BACKENDS` requires `sudo systemctl restart hop3-server`. Lazy reload was rejected for predictability.

### Operational

- Operators who previously relied on `hop3-server` running as the only Hop3 process now have two services to look at. Standardised systemd units and `hop3 status` reporting both should make this a non-event.
- `journalctl -u hop3-rootd` is the first place to look when a deploy fails with a `kernel_error`.
- The audit log at `/var/log/hop3-rootd/audit.log` is the queryable record of every grant decision; `hop3 firewall history` reads it directly.
- The "operator manages Hop3, Hop3 manages the server" contract is explicit: operator manual mutations to managed state are unsupported.

## Alternatives considered

### A. Sudoers fragment for a tightly-scoped command

The pattern implied by [ADR 040](./040-network-firewall-and-port-exposure.md)'s earlier draft and exemplified by the current `/etc/sudoers.d/hop3`. **Rejected** because: every invocation is a setuid escalation, the validation surface is "whatever the wrapper script parses on every call" (no shared state), the sudoers fragment is itself a TOFU asset, and the model does not generalise to other privileged operations without one sudoers entry per op.

### B. Setuid binary

A `hop3-firewall` setuid-root binary that takes a tight argument schema. **Rejected** because: setuid is the most-attacked Linux pattern in history; the bar for "is this binary actually correct" is brutal; the same generalisation problem as (A) applies.

### C. Capabilities on hop3-server (CAP_NET_ADMIN ambient)

Give hop3-server `AmbientCapabilities=CAP_NET_ADMIN` via its systemd unit. No helper at all. **Rejected** because: hop3-server then has root-equivalent network powers; if compromised, the attacker can do anything to the firewall: not just the v1-supported subset. The whole point of running as the `hop3` user is to contain the impact; this gives back almost all of it for one feature.

### D. PolicyKit-mediated helper

Register a polkit action; hop3 user invokes pkexec to run a helper. **Rejected** because: heavy dependency (polkit not always present on minimal systemd setups); the polkit configuration surface is its own learning curve for operators; the audit story is good but no better than what we get with journald + our own audit log. Worth revisiting if we need cross-distro consistency that polkit happens to provide.

### E. D-Bus system service

`hop3-rootd` registers a name on the system bus. **Rejected** because: hard dependency on dbus-daemon; protocol is heavier than we need; the Python d-bus bindings are not stdlib and would re-introduce the third-party dependency we are avoiding. Future option if D-Bus integration becomes required for other reasons.

### F. Per-app network namespaces

Run each app in its own `unshare(CLONE_NEWNET)` namespace. The local-firewall problem partially dissolves: each namespace has its own rules. **Rejected as a substitute for this ADR** because: it is a much larger architectural change (Hop3 deliberately does not use Docker for production, and per-app netns brings most of Docker's networking complexity); it does not eliminate the need for a privileged step (creating the namespace itself needs root); it does not address non-firewall privileged ops. Worth pursuing as a separate Phase-2-isolation ADR.

### G. Per-operation policy file with auto_allow / prompt / deny outcomes

A `/etc/hop3/rootd-policy.toml` file with per-port-range / per-bind-interface outcomes. **Rejected.** Two problems: (1) The "prompt" outcome would force operators to edit a config file as root and retry, contradicting the "single click to grant a port" UX goal; the deploy-time y/N prompt in the CLI (§9) handles "did you mean this?" without any policy-edit cycle. (2) The auth layer would be theatre against a compromised hop3-server: SO_PEERCRED only authenticates the hop3 user; per-app authorization claims are unverifiable. Acknowledging the threat model explicitly (hop3-server compromise = total compromise) and omitting the policy file describes what is actually defended and keeps the daemon's code surface smaller.

If real demand for finer-grained policy emerges, the schema can be reintroduced later with a clear-eyed understanding of what it does and doesn't defend against.

### H. Synchronous async-prompt queue

Rather than "edit policy, retry", expose a `hop3 firewall pending` / `hop3 firewall approve <id>` workflow: rootd holds requests pending operator decision. **Rejected.** Adds queueing, statefulness on the daemon side, a UI in hop3-server, and a synchronisation problem (what if a request is approved after the deploy CLI has timed out?). The CLI's deploy-time prompt is the simpler answer; (G) and (H) both fall away.

## Open questions

1. **Postgres-addon rework specifics**: moving `_ensure_pg_hba_docker_access` and `_ensure_pg_listen_addresses` from runtime to install time. The shape is clear (configure once at install time, idempotent on re-install); the details (which docker-network range to allow by default, whether to gate on a `--with docker` installer flag) need a small follow-up. Tracked separately from this ADR.

2. **`hop3-server.toml` schema redesign**: the flat-key format is extended with new keys for cloud-firewall. The administration guide describes a sectioned format (`[server]`, `[addons.postgres]`, etc.) that doesn't match reality. Whole-file redesign deserves its own ADR; this ADR uses the existing flat format.

3. **Label field surface**: the deploy-time prompt and the audit log both benefit from a free-text label per port. [ADR 045](./045-fixed-port-registry.md)'s `[[ports]]` schema carries an optional `name` field for this, exposed as an optional field on `Hop3TomlSchema`'s `PortEntry` model and threaded into rootd's `description` arg.

4. **Caddy / Traefik reload migration timing**: the exact release window for the follow-on depends on whether the nginx-reload migration uncovers issues that should land before adding more ops. Plan: ship rootd, gather real-world feedback for one release, then add caddy + traefik.

5. **`hop3 firewall history` CLI ergonomics**: reading the audit log is straightforward; the open question is what the default output should be (last 50 entries? grouped by app?). UX detail; not architecturally consequential.

6. **State migration story**: `state.json` is `{"version": 1, ...}`. Future schema bumps need a migration path. Suggest: daemon refuses to start on unknown version; installer's upgrade step runs an explicit migration tool. The version field is present from the start so this path stays open.

7. **Test for the "rootd unavailable" path in hop3-server**: when rootd is down, hop3-server fails the deploy with a clear diagnostic. The c_system test for this is straightforward but needs explicit coverage.

## Implementation sketch

The daemon lives in `packages/hop3-rootd/` with this approximate shape:

```
packages/hop3-rootd/
├── pyproject.toml           # stdlib-only deps; Python ≥3.12
├── README.md
├── src/hop3_rootd/
│   ├── __init__.py
│   ├── __main__.py          # entry: parse args, start server
│   ├── server.py            # accept loop, SO_PEERCRED, dispatch
│   ├── protocol.py          # JSON framing, envelope, error codes, handshake
│   ├── ops/
│   │   ├── __init__.py
│   │   ├── _base.py         # Op protocol; registry
│   │   ├── firewall.py      # add_rule, remove_rule, list_rules
│   │   ├── nginx.py         # reload, validate_config
│   │   └── daemon.py        # health, handshake
│   ├── nft/
│   │   ├── __init__.py
│   │   ├── table.py         # inet hop3 table management
│   │   └── rule.py          # rule construction, nft command emission
│   ├── state.py             # state.json read/write, atomic update
│   ├── reconcile.py         # startup reconciliation logic
│   ├── audit.py             # journald structured logging + audit.log writer
│   ├── exec.py              # safe subprocess wrapper (no shell=True, allow-listed binaries)
│   └── validation.py        # field validators reused across ops
└── tests/
    ├── a_unit/
    │   ├── test_protocol.py
    │   ├── test_validation.py
    │   ├── test_dispatcher.py
    │   ├── test_audit.py
    │   ├── test_firewall_ops_mock.py
    │   └── test_nginx_ops_mock.py
    └── b_integration/
        ├── conftest.py       # root_with_nftables fixture
        ├── test_firewall_real.py
        └── test_reconcile_real.py
```

The systemd units (`hop3-rootd.service`, `hop3-rootd.socket`) and the logrotate config ship under `packages/hop3-installer/` so the installer can drop them in place. The installer's `setup_sudoers` step in `server_installer/nginx.py` becomes a no-op (with a migration-cleanup pass for upgrades).

`hop3-server` gains a `LocalRootdClient` in `hop3.lib.rootd` (or similar): a thin class wrapping `socket.connect("/run/hop3-rootd/socket")`, sending JSON requests, parsing responses, raising on errors. Plugins (`LocalNftablesFirewall`, future `LocalNginxOps`) use the client.

The daemon is intentionally small: stdlib Python plus its tests, small enough to be reviewed end-to-end in a sitting.

## References

- [ADR 040](./040-network-firewall-and-port-exposure.md): network firewall and per-app port exposure (the trigger for this design)
- [ADR 017](./017-agent-based-architecture.md): agent-based architecture (the LocalAgent / multi-node story this composes with)
- [ADR 010](./010-security-and-resilience.md): security and resilience (parent decision on the unprivileged-hop3-user model)
- [ADR 036](./036-cli-ergonomics.md): CLI ergonomics (exit code conventions, `-y` flag, `--no-input` mode)
- [ADR 045](./045-fixed-port-registry.md): fixed-port registry (the `[[ports]]` mechanism that drives rootd's firewall ops)
- [ADR 046](./046-declarative-app-resources.md): declarative app resources (the cgroup/mount ops)
- `packages/hop3-installer/`: the existing "no external dependencies" Python pattern this daemon mirrors
