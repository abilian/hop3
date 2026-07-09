# ADR 050: Layer-7 Web Application Firewall (LeWAF)

- **Status**: Accepted
- **Type**: Feature
- **Created**: 2026-06-16
- **Related-ADRs**: [040](./040-network-firewall-and-port-exposure.md) (network firewall: defers the WAF half here), [041](./041-privileged-operations-agent.md) (privileged operations agent), [045](./045-fixed-port-registry.md) (fixed-port registry), [021](./021-proxy-plugin-system.md) (proxy plugin system), [020](./020-pluggable-architecture.md) (pluggable architecture)

> **Design stance.** Start minimal and prove it before adding power. The access model below is restricted to the two use cases that are real (§Decision 2); speculative features (in-app middleware, kernel-level bans, auth-gated URLs, honeypot lists) are named and **deferred** until customer feedback justifies them (§v1 scope).

## Context

The NGI 0.5 deliverable commits to two distinct security layers: network-level firewalls and a Web Application Firewall built on the OWASP Core Ruleset and a ModSecurity-compatible engine. [ADR 040](./040-network-firewall-and-port-exposure.md)/045 cover the **L3/L4** half (dropping/allowing packets by port (`[[ports]]` → rootd → `nft`). This ADR covers the **L7** half) inspecting HTTP requests for SQLi / XSS / RCE / path-traversal patterns, and applying a per-app access policy, before requests reach the app. It supersedes the WAF half deferred by [ADR 040](./040-network-firewall-and-port-exposure.md) §6 and carries forward the durable content of the earlier WAF planning note.

The two layers are orthogonal and compose: the firewall decides *whether a packet may reach a port*; the WAF decides *whether an HTTP request that reached the app's port is acceptable*. An app can use either, both, or neither.

**Engine: LeWAF.** [LeWAF](https://pypi.org/project/lewaf/) (v0.7.5, Apache-2.0, Python ≥3.12; on **PyPI**) is Abilian's pure-Python, ModSecurity-compatible WAF engine: a SecLang parser, the OWASP Core Rule Set (681 rules), per-framework integrations (Flask / FastAPI / Starlette / Django), **and a standalone reverse-proxy mode** (`lewaf-proxy`). Choosing it over the NGI-named Coraza is deliberate:

- **Pure Python, no CGo / no binary.** Coraza is Go; libmodsecurity is C. LeWAF drops into Hop3's existing Python toolchain and process model with no extra build/runtime story.
- **Sovereignty.** Hop3's ethos is owning the stack; LeWAF is a project we control, so rule-engine bugs and gaps are fixable in-house.
- **Same rules.** LeWAF speaks SecLang and ships the OWASP CRS, so the NGI "OWASP Core Ruleset" commitment is met regardless of engine.

Coraza is not rejected: it is kept as a *future alternative engine* behind the same plugin interface (§Decision 6), for operators who want a non-Python, higher-throughput engine.

## Goals

1. An app opts into a WAF with a few lines of `hop3.toml`; no per-app bespoke wiring.
2. The WAF is **language-agnostic**: it must protect any app (PHP, Node, Go, …).
3. The access model expresses **only the two real use cases** (positive allowlist; conditional access) without a verbose rule grammar.
4. A WAF that is enabled but cannot start, or whose rules don't compile, must **fail the deploy loudly**: never silently let traffic through unprotected (project ethos: no fake success, no silent fallback).
5. Operators can see what the WAF blocked and manage runtime state (bans, networks) via CLI/UI.
6. The engine is pluggable: LeWAF first, Coraza later, behind one interface.

## Decision

### 1. Deployment shape: a platform-managed proxy process

LeWAF runs as a **long-lived reverse-proxy service managed by Hop3**. Request flow for a WAF-enabled app:

```
Client → Nginx (TLS, vhost) → LeWAF proxy (unix socket) → app (uWSGI/web socket)
                                   │
                                   └── JSON audit log (loguru rotation)
```

Honcho supervises it alongside the existing services:

```
├── hop3-server     (API / UI)
├── uwsgi emperor   (app processes)
└── lewaf-proxy     (WAF service)   ← new
```

**Why the proxy shape over in-app middleware** (LeWAF supports both): middleware is Python-only and per-framework, and couples the WAF lifecycle to each app's process and dependency tree. The proxy shape protects any app uniformly, is configured/reloaded by the platform, and keeps the WAF decision out of the app's code. The cost is one network hop and a shared service to operate: acceptable for the uniformity gained.

### 2. Access model: two use cases, regex pattern lists, named networks

Per-app access policy is reduced to the only two patterns that are real. There is **no unconditional per-URL deny**: it isn't needed (it falls out of use case 1) and it invites unscalable rule lists.

**Use case 1 (positive model (default-deny).** The app lists the URL-path patterns it actually serves; everything else is denied. A denied request is, by definition, a probe) so it also feeds the ban scorer (§4). This subsumes honeypot lists: `/wp-admin` on a non-WordPress app is denied because it isn't in the allowlist.

**Use case 2: conditional access (gate).** Specific path patterns are reachable only when a condition holds. v1 conditions: a **named network** (operator-defined CIDR set). `auth` (authenticated against Hop3) is designed-in but **deferred** to forward-auth (§v1 scope).

**Patterns are Python regex, full-matched against the URL path**: one mechanism, no glob semantics to document. Full-match because this is a security boundary: `/admin/.*` must not match `/administrator-public`. The bare-`/admin` case is written `/admin(/.*)?`.

```toml
[waf]
enabled = true
mode    = "block"          # block | detect (log-only: for safe rollout)
ruleset = "owasp-crs"      # CRS attack-detection baseline (§3)

# Use case 1: positive model. If `allow` is set, any path NOT matching one of
# these regexes is denied (and counts as a probe for the ban scorer).
allow = ["/", "/static/.*", "/api/.*"]

# Use case 2: conditional access. Matching paths are reachable only when the
# condition holds. `require` is a named network (v1), or `auth` (deferred).
[[waf.gate]]
paths   = ["/admin/.*", "/internal/.*"]
require = "office"
```

**Named networks live at the operator level, referenced by name**: not as inline CIDRs in app configs. The operator knows their office/VPN ranges; the app author must not hardcode them (and must not need redeploying when they change). Networks are operator runtime state (DB, CLI/UI-managed); app configs reference names, so they stay portable across servers:

```
hop3 network add office 203.0.113.0/24
hop3 network add vpn    10.8.0.0/24
```

**Evaluation order** (per request): **(1) ban check** (a banned source is rejected before anything else; **(2) gate**) if the path matches a gate and the condition fails, deny; **(3) allow**: if `allow` is set and the path matches neither `allow` nor a satisfied gate, deny; **(4) CRS** inspection; **(5) score** the violation (a deny or a CRS match) toward bans. When `allow` is absent, gates merely carve out conditional regions and everything else is open (the WordPress case).

Two things this model leans on entirely (the client's **source IP** (for network gates and bans) and **path normalization** (for matching)) are where positive-security WAFs get bypassed. They are pinned as normative Security invariants (1) and (2) below; an implementation that gets either wrong is bypassable regardless of the rules above.

### 3. CRS baseline and tuning

`ruleset` selects the managed attack ruleset (OWASP CRS); `mode` is `block` or `detect` (log-only, for safe rollout); paranoia is the CRS aggressiveness dial. False positives are silenced with **scoped, verb-named tuning**: never an ambiguous "exclusions" key (which reads as *deny* but means *allow through*):

```toml
[[waf.tuning]]
paths                = ["/admin/.*"]
disable_rule_ids     = [941100, 942100]   # turn off these CRS rules, here only
# skip_body_inspection = true             # or: don't scan request bodies on these paths
reason               = "rich-text editor posts HTML as an authed admin"
```

Each `[[waf.tuning]]` entry is scoped to `paths` (omit = global). Keys are imperatives (`disable_rule_ids`, `skip_body_inspection`) so direction is unambiguous. Method-handling false positives (e.g. WebDAV verbs tripping CRS rule 911100) are tuning.

**CRS distribution:** ship a minimal rule bundle for offline installs; `hop3 waf update-rules` fetches the full OWASP CRS on demand.

### 4. Bans: detect (L7) → score → enforce

A repeated attacker should be cut off once and for all, sparing the cost of re-inspecting every subsequent request. The pipeline:

- **LeWAF detects**: a denied request (allow-miss or gate-fail) or a CRS match writes a structured violation to the audit stream.
- **A Hop3 scorer** consumes that stream and keeps a per-source score over a sliding window.
- **Enforcement** when the score trips the threshold: the source is banned for a TTL.

```toml
[waf.bans]
enabled   = true
threshold = 5
window    = "10m"
duration  = "1h"
```

**v1 enforces bans at L7** (LeWAF holds an in-memory denylist and 403s the source). This needs no new privilege and no rootd change. The **proven-later upgrade** is an L3/L4 drop via rootd: an `nft` set `banned` with per-element `timeout` (kernel-level drop on *all* ports, self-expiring: `nft add element inet hop3 banned { 1.2.3.4 timeout 1h }`). That is strictly better but requires teaching rootd a **deny capability** it does not have today ([ADR 041](./041-privileged-operations-agent.md) §5: rootd's `Firewall` protocol only grants/revokes port rules and has no source-drop capability), so it is deferred until bans earn it (§v1 scope).

### 5. Failure policy (fail loud)

- **Rules must compile before the deploy commits.** Hop3 generates the engine config (SecLang) and loads it into LeWAF in a dry-run; if it doesn't parse, the deploy **aborts with a diagnosis**: never half-deploy an app whose protection is broken.
- If `[waf].enabled = true` and the WAF service cannot be configured or is down at deploy time, the deploy aborts: an app must not advertise protection it isn't getting. (Runtime fail-open vs fail-closed if the *running* WAF dies later is an open question.)
- The `auth` gate condition, until forward-auth exists, is a **hard validation error** ("`require = auth` needs Hop3 forward-auth, not available yet").

### 6. Pluggable engine interface

A `WafEngine` protocol + `get_waf_engines()` Pluggy hook, mirroring `get_proxies()` / `get_addons()` ([ADR 020](./020-pluggable-architecture.md)/021). LeWAF is the first implementation; Coraza can be added later as another engine selected via `[waf].engine` without touching the deploy flow. Interface (sketch): `start_service` / `stop_service` / `reload_config` / `configure_app(app, policy)` / `remove_app(name)` / `get_upstream_socket()` / `check_status()`. The platform compiles the declarative policy (§2/§3) into the engine's native form (SecLang for LeWAF), so engines stay swappable.

### 7. Nginx integration and lifecycle

When `[waf].enabled`, the app's generated nginx upstream points at the LeWAF socket instead of the app's web socket; LeWAF forwards clean traffic on to the app socket. When disabled, nginx points straight at the app (today's behaviour): the single integration point in `plugins/proxy/nginx/`. `configure_app` on deploy, `remove_app` on destroy, file-touch reload (the uWSGI-emperor pattern Hop3 already uses). Per-app generated config lives under `WAF_ROOT`. A redeploy that flips `enabled` re-points the upstream.

### 8. Config vs runtime state (the Web-UI seam)

Two clean tiers, so an admin UI can manage the operational parts without editing app repos:

| Tier | Where | Examples |
|------|-------|----------|
| **Declarative policy** | `hop3.toml` (in the app repo) | `enabled`, `mode`, `allow`, `[[waf.gate]]`, `[[waf.tuning]]`, `[waf.bans]` thresholds |
| **Runtime state** | hop3 DB (CLI/UI-managed) | named networks, active bans, a per-app `detect↔block` override for incident response |

v1's only architectural commitment here is to put **named networks and active bans in the DB**, so a future UI/CLI can list/add/clear them. The UI itself is not built in v1.

### 9. CLI & observability

- `hop3 waf status`: service health + per-app enabled/mode.
- `hop3 waf logs [--app] [--severity]`: the JSON audit trail (rotated; surfaced where the operator looks, never `/dev/null`).
- `hop3 network add|list|rm <name> <cidr…>`: operator-managed named networks (§2).
- `hop3 waf bans list|clear [--app] [<ip>]`: inspect/lift active bans (runtime state, §8).

Each audit entry is one JSON record: and is the exact contract the ban scorer (§4) consumes: `timestamp`, `transaction_id`, `app`, `client_ip`, `request_method`, `request_uri`, `matched` (rule hits), `action` (`blocked` | `allowed` | `logged`), `response_code`, `processing_time_ms`.

## Security invariants (must hold before implementation)

A WAF that can be bypassed is worse than none (it advertises protection it doesn't deliver. These are **normative**: the implementation must satisfy them and tests must cover them. The first two are critical) they are where positive-security WAFs are most often defeated.

1. **Trusted client IP (no client-supplied `X-Forwarded-For` trust).** Gates (`require = <network>`) and bans decide on the client's source IP, so that IP must be unforgeable. If violated: `X-Forwarded-For: <office-ip>` bypasses a network gate (authorization bypass), and a spoofed or shared IP lets an attacker ban arbitrary victims: amplified to all ports once the L3/L4 ban (§4) lands. LeWAF handles this via `trusted_proxy_count`: XFF is honored only when N trusted proxies are declared, and the client is the **Nth entry from the right** (so client-forged leftmost entries are ignored); the default `0` ignores XFF entirely and uses the connecting peer. `lewaf-proxy` must be run with `trusted_proxy_count` set to the number of proxies in front of it (nginx ⇒ `1`), so it reads the real client and not nginx. Tests must assert a forged XFF does **not** satisfy a network gate.

2. **One canonical path; matched == routed.** `allow` / `gate` / CRS matching runs on a single normalized form: percent-decoded once, dot-segments (`.` / `..`) resolved, slashes collapsed, with an explicit case policy. Ambiguous or double-encoded paths are rejected outright. The matched form must equal what the backend routes on: otherwise `/%61dmin`, `/admin/../x`, or `/Admin` slip past a gate. Full-match anchoring (§2) is necessary but not sufficient; normalization is the part that does the real work.

3. **No path around the WAF.** For a WAF-enabled app the backend is reachable **only** via the LeWAF socket: the app's web socket/port is loopback/unix-only and not otherwise exposed. Scope boundary: services that bind host ports directly via `[[ports]]` ([ADR 045](./045-fixed-port-registry.md)) are **not** behind the WAF: L7 coverage is the nginx-proxied HTTP path only; those ports get L3/L4 firewalling. "WAF enabled" must not be read as "every listener protected."

4. **Fail closed, never silent.** If LeWAF is down at runtime, WAF-enabled apps return 5xx: they do **not** silently serve unprotected traffic (the "fake success / silent fallback" the project forbids). Any future per-app `fail_open` override must be explicit and audited, never the default.

5. **Bans must not become a DoS.** Trusted networks (office/VPN) and operator-registered monitors are **ban-exempt** (the named-networks mechanism doubles as the exemption list). Bans on shared egress IPs (CGNAT / CDN / corporate proxy) prefer per-session L7 action over an all-ports L3/L4 drop. A misconfigured default-deny `allow` can mass-ban legitimate users: deploy-time validation flags suspiciously narrow allowlists, and `detect` mode is the safe rollout path.

6. **Rule compilation is injection-safe.** Author-supplied paths/patterns and `[waf.custom]` are escaped/parameterized when compiled to SecLang: a crafted value must not inject directives or disable the engine (`SecRuleEngine Off`). The §5 dry-run validates the *generated* ruleset, and engine-control / disruptive actions (`exec`, …) in custom rules are rejected.

7. **Audit logs are redacted.** The audit stream (also the ban-scorer's input) redacts secrets/PII from `request_uri` and captured data (query-string tokens, credentials, session IDs) following [ADR 041](./041-privileged-operations-agent.md)'s sanitization discipline. Credential-bearing bodies are never logged.

8. **Author regex is bounded.** `allow` / `gate` patterns run per-request on attacker-controlled paths; use a non-backtracking engine or a per-match timeout, and validate patterns at deploy, so a pathological regex can't CPU-DoS the app.

## Relationship to hop3-rootd

In v1 the WAF needs **no privileged operations**: it is a userspace proxy running as the `hop3` user, binding unix sockets and reading/writing files under `WAF_ROOT`; bans are enforced in-process at L7. So it does **not** go through hop3-rootd ([ADR 041](./041-privileged-operations-agent.md)). Clean split: rootd is the kernel boundary; the WAF is an ordinary supervised service.

The one place the two layers will meet is the **deferred L3/L4 ban** (§4): dropping a banned source at the kernel for all ports is a rootd `nft` operation, and it is the first real case for adding a *deny* capability to rootd. That is a future ADR/revision, gated on bans proving their value.

## v1 scope: deliberately minimal

Shipped in v1: proxy shape, `enabled`/`mode`/`ruleset`, the two-construct access model (`allow` + `[[waf.gate]]` with **network** conditions), scoped `[[waf.tuning]]`, L7 bans, named networks + bans in the DB, the CLI above, compile-before-commit validation.

Deferred until customer feedback justifies the complexity:

- **In-app middleware engine**: proxy only for now.
- **L3/L4 bans via rootd**: L7 bans first; the rootd deny-capability is a real extension, built once bans prove their value.
- **`auth` gate condition**: needs a Hop3 forward-auth/SSO layer that doesn't exist yet; validated as an error until it does.
- **`[[waf.tuning]] skip-body-inspection`**: `ctl:requestBodyAccess` is a no-op in lewaf 0.7.5 (bug-report follow-up); the compiler fails loud on it until the engine supports it. `disable-rule-ids` tuning works.
- **Honeypot/`instant_ban_paths`**: subsumed by default-deny in use case 1.
- **Per-rule ban flags, per-rule method matching, inline CIDRs**: folded into the model above or dropped.
- **Coraza engine, response-phase inspection, the admin UI itself.**

## Worked examples

**Bespoke app (use case 1)**: default-deny; scanners are denied and banned with no honeypot list:

```toml
[waf]
enabled = true
mode    = "block"
ruleset = "owasp-crs"
allow   = ["/", "/static/.*", "/api/.*", "/health"]
[waf.bans]
enabled = true
threshold = 5
window = "10m"
duration = "24h"
```

**WordPress (use case 2)**: too many dynamic routes for an allowlist, so gate the admin area and tune the editor:

```toml
[waf]
enabled = true
mode    = "block"
ruleset = "owasp-crs"
[[waf.gate]]
paths   = ["/wp-admin/.*", "/wp-login\\.php"]
require = "office"
[[waf.tuning]]
paths            = ["/wp-admin/.*"]
disable_rule_ids = [941100, 941160, 942100, 942200]
reason           = "Gutenberg editor posts HTML/JS as admin"
[waf.bans]
enabled = true
threshold = 8
window = "10m"
duration = "1h"
```

**Nextcloud**: the WAF-hostile case: WebDAV methods + chunked uploads are handled as CRS tuning:

```toml
[waf]
enabled = true
mode    = "block"
ruleset = "owasp-crs"
[[waf.tuning]]
paths                = ["/remote.php/dav/.*", "/remote.php/webdav/.*"]
skip_body_inspection = true
disable_rule_ids     = [911100, 920420, 920470]   # WebDAV methods + content-type
reason               = "Nextcloud sync clients are not browsers"
[waf.bans]
enabled = true
threshold = 6
window = "10m"
duration = "2h"
```

## Alternatives considered

- **In-app ASGI/WSGI middleware** (LeWAF supports it). Rejected as the primary shape: Python-only, per-framework, couples WAF to the app process. May return later as an opt-in for Python apps that want zero extra hops.
- **A general allow/deny rule grammar** (array of `{path, method, action, …}` tables). Rejected: it doesn't scale (one table per path), and the only real cases are the positive model and conditional gates: both expressed more compactly above.
- **fail2ban for bans.** Off-the-shelf, but a *second* writer to the firewall → two owners of nft state, the shared-mutable-state hazard the robustness ethos warns against. Prefer L7 now, rootd-owned drops later.
- **Coraza (Go) via binary/gRPC.** Viable and NGI-named; deferred behind the same `WafEngine` interface for the pure-Python / sovereignty reasons above.
- **libmodsecurity + nginx connector (C module).** Mature, but a C build dependency and a custom nginx module: heavy operationally and against the sovereignty/simplicity grain.
- **No WAF; rely on app-level protections.** Rejected: the NGI deliverable commits to a WAF, and per-app protection is inconsistent and unauditable.

## Consequences

**Positive**: meets the NGI WAF commitment with OWASP CRS; language-agnostic; the access model is two constructs a packager grasps immediately; default-deny makes scanner-banning automatic; content-checked blocking is testable; pluggable so Coraza can follow; networks/bans in the DB make a future admin UI cheap.

**Negative**: a new long-lived platform service to supervise; one extra network hop for WAF-enabled apps; CRS false-positive tuning is ongoing work; regex full-match has a learning edge (the bare-prefix gotcha); the WAF is a hard dependency in the request path: **fail-closed by default** (Security invariant 4), so a WAF outage takes WAF-enabled apps down until it recovers; the security invariants (trusted-IP, canonicalization, no-bypass) are non-trivial to get right and must be tested explicitly.

## Open questions

1. **Per-app `fail_open` override.** The runtime default is **fail-closed** (Security invariant 4): if LeWAF is down, WAF-enabled apps return 5xx. The only remaining question is whether to offer an explicit, audited per-app `fail_open` escape hatch for availability-over-security apps.
2. **Performance under load.** Pure-Python inspection cost per request; benchmark before advertising; Coraza is the escape hatch.
3. **Response-phase inspection** (CRS phases 3/4): LeWAF's proxy-mode support needs verifying.

## LeWAF engine facts

On the pinned floor `lewaf>=0.7.5`, the engine has these properties that shape the integration:

- **Proxy shape**: `lewaf-proxy --upstream <url> --rules-file <seclang> [--host --port --timeout --max-connections]` (a uvicorn/Starlette ASGI app forwarding via httpx. The proxy is single-upstream (one `--upstream`), so the fit is **one proxy process per WAF-enabled app**, supervised by Hop3) a shared multi-tenant, vhost-routing mode would be an upstream LeWAF contribution and is not needed for v1.
- **Rules**: SecLang. Network gates / IP bans compile to `SecRule REMOTE_ADDR "@ipMatch <cidrs>"`-style rules. `lewaf-validate` is the compile-before-commit dry-run (§5).
- **Config format**: the proxy consumes a SecLang **rules file** (`--rules-file`); LeWAF's richer YAML config (`rules` / `rule_files` / `storage` / `audit_logging` / `request_limits`) drives the library path. The §6 compiler emits SecLang per app.
- **Audit**: YAML `audit_logging` supports `format: json` + `mask_sensitive: true` (helps Security invariant 7).
- **`drop` == `deny`** (no TCP drop in pure-Python middleware): real bans need the L3/L4 rootd path (§4).
- **Trusted client IP** is handled via `trusted_proxy_count` (Security invariant 1): the middleware reads XFF safely, taking the Nth entry from the right and ignoring client-forged leftmost entries. `lewaf-proxy` runs with `trusted_proxy_count=1` for the single nginx hop, with no nginx XFF-rewrite needed.

The §6 compiler emits, for the pinned floor:

- **`allow`** → `!@rx` deny on `REQUEST_URI` (use case 1).
- **`[[waf.gate]]`** → `chain` of (path `@rx`) + (`REMOTE_ADDR !@ipMatch <network cidrs>`) (use case 2).
- **`[[waf.tuning]] disable-rule-ids`** → path-scoped `ctl:ruleRemoveById` (or global `SecRuleRemoveById`).

The **one remaining gap** is `[[waf.tuning]] skip-body-inspection`: `ctl:requestBodyAccess` is still a no-op in the engine, so the compiler **fails loud** on it rather than silently not inspect.

The `lewaf-proxy` CLI is rules-file-only; `create_proxy_app` accepts a `waf_config_file`, but the CLI does not expose it, so storage (redis) / audit / limits and `trusted_proxy_count` need a `--config` flag / CLI args / env wiring: a small LeWAF contribution if absent.

## Dependencies, prior art, and acceptance

**Dependency:** `lewaf>=0.7.5` from **PyPI** (Apache-2.0, Python ≥3.12) plus the OWASP CRS. Wired as the optional extra `hop3-server[waf]` with a `python_full_version >= '3.12'` marker (the base workspace supports 3.11, lewaf doesn't) (non-WAF installs and 3.11 installs don't carry it. It pulls `starlette` (the rest) httpx / redis / pyyaml: hop3-server already has). CRS distribution per §3.

**Prior art (reference.** An earlier WAF attempt was implemented on an abandoned `waf-integration` branch at commit **`77e4046a`** ("feat: step 1 of WAF integration"), including `commands/waf.py`, `lib/waf_logging.py`, and `plugins/waf/lewaf/engine.py`. It is **not** an ancestor of any live branch and uses the **pre-050 schema** (`[waf]` + `[security.rules]`). Consult it for the LeWAF engine wrapper and audit-logging mechanics; do not cherry-pick wholesale) the access model in §2 supersedes it. (SHA recorded so the commit survives git gc.)

**Acceptance criteria (v1):**

1. Deploy an app with `[waf] enabled = true`; the LeWAF proxy fronts it.
2. A known SQLi payload is blocked (CRS rule 942100); a legitimate request to the same path passes.
3. Under use case 1, a request outside `allow` is denied and, after `threshold` hits in `window`, the source is banned.
4. `hop3 waf status` shows the service running; `hop3 waf logs` contains structured audit entries.
5. A malformed rule, or `require = auth` before forward-auth exists, **aborts the deploy** with a clear diagnosis: no silent pass-through.
