# ADR 033: Web Application Firewall (WAF) and Network Security Integration

**Status**: Draft
**Date**: 2025-12-03
**Related ADRs**: ADR 010 (Security and Resilience), ADR 021 (Proxy Plugin System), ADR 020 (Pluggable Architecture)

---

## Summary

This ADR proposes a comprehensive security layer for Hop3 with three components:

1. **Static WAF** - Rule-based inspection using OWASP CRS and custom rules
2. **Adaptive WAF** - Behavioral analysis and automatic threat response
3. **Network Firewall** - Kernel-level IP blocking via iptables/nftables

The WAF subsystem uses a **pluggable architecture**: LeWAF (Python) is the initial implementation, with Coraza (Go) as a future high-performance alternative. Applications can define simple allow/deny rules without learning CRS/SecLang syntax.

Anti-bot features (Anubis, proof-of-work challenges) are **deferred to a later phase** to focus on core WAF functionality first.

---

## Context and Goals

### Context

The research contract specifies:

> "Security will be fortified with network-level firewalls and a Web Application Firewall (WAF) using tools like OWASP Core Ruleset and Coraza."

Currently, Hop3 provides no built-in WAF protection. Applications deployed on Hop3 are exposed to common web attacks:
- SQL injection, XSS, command injection (OWASP Top 10)
- Path traversal, file inclusion, protocol violations
- DDoS and rate-limiting attacks
- API abuse and credential stuffing
- Brute force login attempts

Additionally, there is no network-level protection: malicious IPs can repeatedly attack applications without being blocked at the firewall level.

### Goals

1. **Primary**: Protect applications from OWASP Top 10 vulnerabilities using industry-standard rulesets (CRS)
2. **Secondary**: Provide adaptive protection that learns from attack patterns and blocks repeat offenders
3. **Tertiary**: Network-level firewall integration for IP-based blocking
4. **Fourth**: Simple per-app rules (allowlist/denylist) without requiring CRS expertise
5. **Non-goals (this phase)**: Anti-bot challenges (Anubis), CAPTCHA, proof-of-work

### Success Criteria

- Block >90% of OWASP Top 10 attack patterns
- <5ms additional latency per request for WAF inspection
- Configuration via `hop3.toml` with sensible defaults
- Per-application WAF settings with global fallback
- Pluggable WAF engine (swap LeWAF for Coraza without config changes)
- Automatic IP blocking after repeated attacks

---

## Background: Available Technologies

### LeWAF

**LeWAF** is a pure Python WAF engine implementing SecLang (ModSecurity-compatible rule language):

| Feature | Status |
|---------|--------|
| OWASP CRS Compatibility | 92% (594 rules) |
| Standard Operators | 32 implemented (`@rx`, `@detectSQLi`, `@detectXSS`, etc.) |
| Transformations | 48 (145% of Go Coraza baseline) |
| Actions | 36 standard actions |
| Framework Integration | FastAPI, Flask, Django, Starlette |
| Performance | ~1000 req/s per worker |
| License | Apache 2.0 |

**Strengths**:
- Pure Python: single-language stack, easier debugging
- SecLang compatibility: reuse existing ModSecurity rules
- ASGI/WSGI middleware integration
- Active development (v1.4.0, production ready)

**Limitations**:
- Slower than C-based WAF engines (ModSecurity, Coraza Go)
- No built-in anti-bot challenges (CAPTCHA, JavaScript challenges)
- No IP reputation database integration

### Anubis

**[Anubis](https://github.com/TecharoHQ/anubis)** is a proof-of-work anti-AI scraper tool:

| Feature | Description |
|---------|-------------|
| Language | Go (with JavaScript challenges) |
| Mechanism | Proof-of-work cryptographic challenge |
| Browser Detection | JA4 TLS fingerprinting, THR1 |
| Adoption | GNOME, FFmpeg, UNESCO, Duke University |
| Performance | Lightweight, minimal overhead |
| License | MIT |

**How it works**:
1. Anubis sits between reverse proxy and application
2. Challenges visitors with lightweight computational puzzle
3. Browsers solve the puzzle in JavaScript (users see brief loading screen)
4. Bots without JavaScript execution fail the challenge
5. Verified visitors receive a cookie for subsequent requests

**Strengths**:
- Highly effective against AI crawlers
- Minimal resource usage
- Battle-tested (200,000+ downloads)
- Simple deployment

**Limitations**:
- Requires JavaScript (excludes non-JS users)
- No WAF rules (doesn't block SQL injection, XSS, etc.)
- No ModSecurity/SecLang compatibility

### ModSecurity / Coraza (Go)

Traditional WAF engines that integrate with reverse proxies:

| Engine | Language | Integration |
|--------|----------|-------------|
| ModSecurity 3.x | C++ | NGINX module, Apache module |
| Coraza | Go | Caddy plugin, standalone proxy |

**Strengths**:
- Mature, battle-tested
- High performance (~50k req/s)
- Native proxy integration

**Limitations**:
- Complex multi-language stack
- Harder to customize/debug
- Requires compilation with proxy

### Paf le WAF / LeWAF Platform (Conceptual)

A full WAF platform concept documented in LeWAF prospective notes:

- Pure Python ASGI gateway with LeWAF middleware
- Orchestrator with job scheduling
- Web UI for management
- Plugin system (antibot, rate limiting, IP reputation)
- Docker/Kubernetes autoconf controllers

**Status**: Architecture documented, not implemented. Would require significant development effort.

---

## Decision Options

### Option A: LeWAF Middleware Integration

**Architecture**:
```
┌─────────┐     ┌──────────┐     ┌─────────────────┐     ┌─────────┐
│ Client  │────▶│  Proxy   │────▶│ LeWAF Middleware│────▶│   App   │
│         │     │ (Nginx)  │     │   (per-app)     │     │         │
└─────────┘     └──────────┘     └─────────────────┘     └─────────┘
```

**Implementation**:
- LeWAF runs as ASGI/WSGI middleware within each application's process
- Configuration loaded from `hop3.toml` or database
- Per-application rule customization
- Supervisor manages app+LeWAF as single unit

**Pros**:
- Pure Python: fits Hop3's philosophy
- Per-app isolation: rules don't leak between apps
- Easy debugging and customization
- No additional processes

**Cons**:
- Performance overhead in application process
- Only works for Python applications
- Doesn't protect non-Python apps (Node.js, Go, etc.)

### Option B: LeWAF Reverse Proxy Service

**Architecture**:
```
┌─────────┐     ┌──────────┐     ┌────────────────┐     ┌─────────┐
│ Client  │────▶│  Proxy   │────▶│  LeWAF Proxy   │────▶│   App   │
│         │     │ (Nginx)  │     │   (shared)     │     │         │
└─────────┘     └──────────┘     └────────────────┘     └─────────┘
```

**Implementation**:
- Single LeWAF reverse proxy service (using `lewaf-proxy` CLI)
- All traffic routes through LeWAF before reaching apps
- Per-app configuration via routing rules
- Managed by supervisor alongside apps

**Pros**:
- Protects all application types (Python, Node.js, Go, etc.)
- Single point of WAF configuration
- Can use full LeWAF feature set

**Cons**:
- Additional service to manage
- Single point of failure
- Adds network hop

### Option C: Anubis Anti-Bot Service

**Architecture**:
```
┌─────────┐     ┌──────────┐     ┌──────────────┐     ┌─────────┐
│ Client  │────▶│  Proxy   │────▶│   Anubis     │────▶│   App   │
│         │     │ (Nginx)  │     │  (per-app?)  │     │         │
└─────────┘     └──────────┘     └──────────────┘     └─────────┘
```

**Implementation**:
- Anubis service handles proof-of-work challenges
- Can run per-app or shared
- Configured via environment variables
- Proxy routes traffic through Anubis

**Pros**:
- Highly effective against AI crawlers
- Minimal overhead
- Simple to deploy

**Cons**:
- No WAF rules (SQL injection, XSS still unprotected)
- Requires JavaScript (accessibility concern)
- Doesn't fit all use cases (APIs, mobile apps)

### Option D: Hybrid (LeWAF + Anubis)

**Architecture**:
```
┌─────────┐     ┌──────────┐     ┌──────────────┐     ┌──────────────┐     ┌─────────┐
│ Client  │────▶│  Proxy   │────▶│   Anubis     │────▶│  LeWAF Proxy │────▶│   App   │
│         │     │ (Nginx)  │     │  (anti-bot)  │     │    (WAF)     │     │         │
└─────────┘     └──────────┘     └──────────────┘     └──────────────┘     └─────────┘
```

**Implementation**:
- Anubis handles bot detection and proof-of-work challenges
- LeWAF handles WAF rules (OWASP CRS, custom rules)
- Both services managed by supervisor
- Configuration via `hop3.toml`

**Pros**:
- Comprehensive protection: both bot detection AND WAF
- Best-of-breed for each concern
- Flexible: enable/disable each independently

**Cons**:
- Two additional services
- More complex configuration
- Two network hops

### Option E: Proxy-Integrated WAF (ModSecurity/Coraza)

**Architecture**:
```
┌─────────┐     ┌───────────────────────────┐     ┌─────────┐
│ Client  │────▶│  Proxy + ModSecurity      │────▶│   App   │
│         │     │  (Nginx + module)         │     │         │
└─────────┘     └───────────────────────────┘     └─────────┘
```

**Implementation**:
- ModSecurity compiled as NGINX module (or Coraza with Caddy)
- WAF rules loaded at proxy level
- Per-vhost configuration

**Pros**:
- Maximum performance (~50k req/s)
- Single process (proxy = WAF)
- Battle-tested in production

**Cons**:
- Complex build process (compile NGINX with ModSecurity)
- C/Lua stack: harder to debug
- OS-specific binary dependencies
- Conflicts with Hop3's "simple, no Docker" philosophy

### Option F: Optional WAF Plugin (Recommended)

**Architecture**:
```
┌─────────┐     ┌──────────┐     ┌─────────────────────────────┐     ┌─────────┐
│ Client  │────▶│  Proxy   │────▶│  WAF Service (if enabled)   │────▶│   App   │
│         │     │ (Nginx)  │     │  LeWAF | Anubis | Both      │     │         │
└─────────┘     └──────────┘     └─────────────────────────────┘     └─────────┘
```

**Implementation**:
- WAF as optional Hop3 plugin (enabled via config)
- Server-wide WAF service with per-app routing
- Supports LeWAF (WAF rules), Anubis (anti-bot), or both
- Configuration via `hop3.toml` and server config
- Graceful degradation: apps work without WAF

---

## Decision

**We recommend a layered security architecture** with pluggable components:

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Security Layers                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Layer 1: Network Firewall (iptables/nftables)                      │
│           └── Block IPs at kernel level (fastest, lowest overhead)  │
│                                                                     │
│  Layer 2: Static WAF (LeWAF/Coraza)                                 │
│           ├── Simple rules: allowlist/denylist (fast, no CRS)       │
│           └── CRS rules: OWASP Core Rule Set inspection             │
│                                                                     │
│  Layer 3: Adaptive WAF                                              │
│           └── Behavioral analysis, rate limiting, auto-ban          │
│               ("fail2ban-like" for web traffic)                     │
│                                                                     │
│  Layer 4: Anti-Bot (FUTURE - Phase 5)                               │
│           └── Anubis, proof-of-work, CAPTCHA                        │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Core Concepts

#### 1. Pluggable WAF Engine

The WAF engine is abstracted behind an interface, allowing multiple implementations:

```python
class WafEngine(Protocol):
    """Interface for WAF engine implementations."""

    name: str

    def load_rules(self, rules: list[WafRule]) -> None:
        """Load WAF rules (CRS, custom, etc.)."""

    def inspect(self, transaction: WafTransaction) -> WafResult:
        """Inspect a request/response transaction."""

    def get_audit_log(self, transaction_id: str) -> AuditLogEntry:
        """Retrieve audit log for a transaction."""


class WafRule:
    """A WAF rule (either CRS-style or simple pattern)."""
    id: str
    source: Literal["crs", "custom", "app"]
    enabled: bool
    # For CRS rules: SecLang syntax
    seclang: str | None
    # For simple rules: pattern matching
    pattern: SimpleRulePattern | None


class SimpleRulePattern:
    """Simple allowlist/denylist rule without CRS syntax."""
    action: Literal["allow", "deny"]
    match_type: Literal["path", "path_prefix", "regex", "ip", "user_agent"]
    pattern: str
    priority: int = 0
```

**Initial Implementation**: LeWAF (Python)
**Future Implementation**: Coraza (Go) for higher performance

#### 2. Static WAF vs Adaptive WAF

| Aspect | Static WAF | Adaptive WAF |
|--------|------------|--------------|
| **Rules** | Predefined (CRS, custom) | Dynamic (learned from traffic) |
| **Response** | Immediate block/allow | Score accumulation, threshold |
| **Updates** | Manual rule updates | Automatic based on behavior |
| **Examples** | SQL injection detection | Rate limiting, brute force detection |
| **Latency** | Predictable | May vary with analysis |

Both modes work together:
1. Static WAF catches known attack patterns immediately
2. Adaptive WAF monitors behavior and blocks repeat offenders

#### 3. Simple Per-App Rules

Applications can define rules without CRS/SecLang knowledge:

```toml
# hop3.toml - Simple rules (no CRS knowledge required)
[security.rules]

# Allowlist - these paths bypass WAF inspection
allow = [
    "/health",
    "/api/webhook/*",
    "/.well-known/*",
]

# Denylist - these paths are blocked
deny = [
    "/wp-admin/*",           # Block WordPress admin probes
    "/phpmyadmin/*",         # Block phpMyAdmin probes
    "*.php",                 # Block PHP file requests (if not a PHP app)
]

# IP allowlist (bypass all security)
allow_ips = [
    "10.0.0.0/8",            # Internal network
    "192.168.1.100",         # Monitoring server
]

# IP denylist (block at WAF level)
deny_ips = [
    "1.2.3.4",               # Known attacker
]
```

These simple rules are compiled to WAF rules internally but don't require users to learn SecLang.

#### 4. Network Firewall Integration

For persistent threats, block at the kernel level using iptables/nftables:

```python
class NetworkFirewall(Protocol):
    """Interface for kernel-level firewall management."""

    def block_ip(self, ip: str, duration: timedelta | None = None) -> None:
        """Block an IP address (temporary or permanent)."""

    def unblock_ip(self, ip: str) -> None:
        """Remove IP from blocklist."""

    def block_range(self, cidr: str, duration: timedelta | None = None) -> None:
        """Block an IP range (CIDR notation)."""

    def get_blocked(self) -> list[BlockedEntry]:
        """List all blocked IPs/ranges."""

    def sync_from_adaptive_waf(self, decisions: list[AdaptiveDecision]) -> None:
        """Sync block decisions from adaptive WAF to firewall."""
```

The adaptive WAF can automatically escalate blocks to the network firewall:

```
Attack detected by Static WAF
        │
        ▼
Adaptive WAF tracks IP score
        │
        ▼
Score exceeds threshold (e.g., 10 attacks in 1 minute)
        │
        ▼
Network Firewall blocks IP at kernel level
        │
        ▼
(Optional) After cooldown period, IP is unblocked
```

---

### Default Behavior

WAF is **opt-in** by default. Applications without explicit WAF configuration are not protected.

| Setting | Default | Scope |
|---------|---------|-------|
| WAF enabled | `false` | Per-app |
| WAF engine | `lewaf` | Global (server) |
| Paranoia level | `1` | Global (server), overridable per-app |
| Ruleset | `owasp-crs` | Global (server), overridable per-app |
| Mode | `block` | Per-app |
| Adaptive WAF | `false` | Per-app |
| Network Firewall | `false` | Global (server) |

**Global defaults** are set in server configuration:

```bash
# /etc/hop3/server.conf
HOP3_WAF_DEFAULT_ENGINE=lewaf
HOP3_WAF_DEFAULT_PARANOIA_LEVEL=1
HOP3_WAF_DEFAULT_RULESET=owasp-crs
HOP3_FIREWALL_ENABLED=false
HOP3_FIREWALL_BACKEND=nftables
```

**Per-app opt-in** via `hop3.toml`:

```toml
[waf]
enabled = true  # Opt-in to WAF protection
# Other settings inherit from global defaults unless overridden
```

### Rule Processing Order

When WAF is enabled, rules are processed in this order:

```
1. IP Allowlist (security.rules.allow_ips)
   └── If match: BYPASS all security, proceed to app

2. IP Denylist (security.rules.deny_ips)
   └── If match: BLOCK (403 Forbidden)

3. Path Allowlist (security.rules.allow)
   └── If match: BYPASS WAF inspection, proceed to app

4. Path Denylist (security.rules.deny)
   └── If match: BLOCK (403 Forbidden)

5. Static WAF (CRS rules + custom rules)
   └── If violation: BLOCK or LOG (based on mode)

6. Adaptive WAF (if enabled)
   └── Rate limiting, scoring, auto-ban
```

This order ensures:
- Trusted IPs/paths are never blocked by WAF rules
- Known-bad patterns are blocked before expensive CRS processing
- CRS rules handle complex attack detection
- Adaptive WAF provides behavioral protection

### Single WAF Instance Architecture

Hop3 runs a **single WAF service** that handles all applications:

```
┌─────────────────────────────────────────────────────────────────┐
│                    LeWAF Service (Single Instance)              │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                    Request Router                         │  │
│  │  Inspects Host header / X-Hop3-App to determine app       │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              │                                  │
│              ┌───────────────┼───────────────┐                  │
│              ▼               ▼               ▼                  │
│  ┌───────────────┐ ┌───────────────┐ ┌───────────────┐          │
│  │  App: myapp   │ │ App: otherapp │ │  App: api     │          │
│  │  ─────────────│ │  ─────────────│ │  ─────────────│          │
│  │  paranoia: 2  │ │  paranoia: 1  │ │  waf: disabled│          │
│  │  custom rules │ │  defaults     │ │  (passthrough)│          │
│  └───────────────┘ └───────────────┘ └───────────────┘          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Request flow**:
1. Nginx receives request for `myapp.example.com`
2. Nginx routes to LeWAF service (via Unix socket)
3. LeWAF identifies app from `Host` header or `X-Hop3-App` header
4. LeWAF loads app-specific rules from `/var/hop3/config/waf/apps/myapp.yaml`
5. LeWAF inspects request using app's configuration
6. If allowed, LeWAF proxies to app's upstream socket

**Configuration reload**:
- When app is deployed/updated, Hop3 regenerates WAF config
- LeWAF receives SIGHUP to reload per-app configurations
- No restart required for rule changes

### Adaptive WAF Storage

The Adaptive WAF maintains IP scores and violation history:

**Storage Architecture**:
```
┌─────────────────────────────────────────────────────────────────┐
│                    Adaptive WAF Storage                         │
│                                                                 │
│  ┌─────────────────────────┐    ┌─────────────────────────────┐ │
│  │    In-Memory Cache      │    │    SQLite Persistence       │ │
│  │    (Fast Lookups)       │    │    (Durability)             │ │
│  │  ───────────────────────│    │  ───────────────────────────│ │
│  │  • Active IP scores     │◄──►│  • Score snapshots          │ │
│  │  • Recent violations    │    │  • Violation history        │ │
│  │  • Rate limit counters  │    │  • Block decisions          │ │
│  │  • TTL-based expiry     │    │  • Audit trail              │ │
│  └─────────────────────────┘    └─────────────────────────────┘ │
│                                                                 │
│  Sync: Every 60 seconds + on graceful shutdown                  │
│  Recovery: Load from SQLite on startup                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Data model**:
```python
@dataclass
class IPScore:
    ip: str
    score: int
    last_violation: datetime
    violation_count: int
    blocked_until: datetime | None

@dataclass
class Violation:
    ip: str
    timestamp: datetime
    rule_id: str
    severity: str  # critical, high, medium, low
    app: str
    request_uri: str
```

**SQLite schema** (`/var/hop3/config/firewall/blocked.db`):
```sql
CREATE TABLE ip_scores (
    ip TEXT PRIMARY KEY,
    score INTEGER,
    last_violation TIMESTAMP,
    violation_count INTEGER,
    blocked_until TIMESTAMP
);

CREATE TABLE violations (
    id INTEGER PRIMARY KEY,
    ip TEXT,
    timestamp TIMESTAMP,
    rule_id TEXT,
    severity TEXT,
    app TEXT,
    request_uri TEXT
);

CREATE INDEX idx_violations_ip ON violations(ip);
CREATE INDEX idx_violations_timestamp ON violations(timestamp);
```

### Network Firewall Agent

Manipulating iptables/nftables requires elevated privileges (CAP_NET_ADMIN). Hop3 uses a **privileged firewall agent** that runs separately:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Firewall Architecture                        │
│                                                                 │
│  ┌─────────────────────────┐    ┌─────────────────────────────┐ │
│  │    Hop3 Server          │    │    Firewall Agent           │ │
│  │    (unprivileged)       │    │    (CAP_NET_ADMIN)          │ │
│  │  ───────────────────────│    │  ───────────────────────────│ │
│  │  • WAF service          │    │  • iptables/nftables cmds   │ │
│  │  • Adaptive WAF         │───►│  • Block/unblock IPs        │ │
│  │  • Block decisions      │    │  • Rule persistence         │ │
│  │                         │◄───│  • Status reporting         │ │
│  └─────────────────────────┘    └─────────────────────────────┘ │
│              │                              │                   │
│              │    Unix Socket IPC           │                   │
│              │  /var/hop3/run/firewall.sock │                   │
│              └──────────────────────────────┘                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**IPC Protocol** (JSON over Unix socket):
```json
// Request: Block IP
{"action": "block", "ip": "1.2.3.4", "duration": 3600, "reason": "waf_threshold"}

// Request: Unblock IP
{"action": "unblock", "ip": "1.2.3.4"}

// Request: List blocked
{"action": "list"}

// Response
{"status": "ok", "blocked": [{"ip": "1.2.3.4", "until": "2025-12-03T12:00:00Z"}]}
```

**Firewall Agent startup**:
```bash
# Started by systemd with capabilities
# /etc/systemd/system/hop3-firewall-agent.service
[Service]
ExecStart=/usr/local/bin/hop3-firewall-agent
User=hop3
AmbientCapabilities=CAP_NET_ADMIN
NoNewPrivileges=true
```

**Alternative**: If running as root (not recommended), the firewall agent can be integrated into the main Hop3 server process.

---

### Implementation Phases

### Phase 1: Static WAF with LeWAF (MVP)

**Goal**: Basic WAF protection with OWASP CRS rules

1. **WAF Plugin Interface**: Add `WafEngine` protocol to `hop3/core/protocols.py`

2. **LeWAF Plugin**: Implement `LeWafPlugin`:
   - Runs as ASGI reverse proxy service
   - Loads OWASP CRS rules by default
   - Per-app rule customization via `hop3.toml`
   - Managed by supervisor

3. **Simple Rules Support**: Translate `[security.rules]` to WAF rules

4. **WAF Logging**: Separate log stream for WAF events

5. **Configuration**:
   ```toml
   # hop3.toml (per-app)
   [waf]
   enabled = true
   engine = "lewaf"         # or "coraza" (future)
   ruleset = "owasp-crs"    # or "minimal", "custom"
   paranoia_level = 1       # 1-4 (1 = balanced, 4 = strict)
   mode = "block"           # or "detect" (log only)

   [waf.crs]
   # Custom CRS rules in SecLang syntax (for advanced users)
   custom = """
   SecRule ARGS "@detectSQLi" "id:10001,deny,status:403"
   """

   [waf.exclusions]
   # Paths excluded from CRS inspection (simple rules still apply)
   paths = ["/api/webhook", "/health"]
   rule_ids = [920350, 942100]  # Disable specific CRS rules
   ```

### Phase 2: Adaptive WAF

**Goal**: Behavioral analysis and automatic threat response ("fail2ban-like" experience for web traffic)

> **Historical note**: In early LeWAF documentation, behavioral/adaptive features were codenamed "LeBot". The Adaptive WAF in Hop3 incorporates these concepts: rate limiting, IP scoring, and automatic blocking based on behavior patterns.

The Adaptive WAF provides functionality similar to fail2ban but integrated directly with Hop3's WAF layer:

| fail2ban Concept | Adaptive WAF Equivalent |
|------------------|------------------------|
| `maxretry` | `block_threshold` / violation points |
| `findtime` | Implicit in scoring window |
| `bantime` | `block_duration` |
| `filter` | WAF rules (CRS + custom) |
| `jail` | Per-app adaptive config |
| `action` | Block at WAF or escalate to firewall |

1. **Scoring System**: Track per-IP attack scores
   ```python
   class AdaptiveWaf:
       def record_violation(self, ip: str, severity: int, rule_id: str) -> None:
           """Record a WAF violation for an IP."""

       def get_score(self, ip: str) -> int:
           """Get current threat score for an IP."""

       def should_block(self, ip: str) -> bool:
           """Check if IP should be blocked based on score."""

       def get_violations(self, ip: str, since: datetime) -> list[Violation]:
           """Get recent violations for an IP (like fail2ban's findtime window)."""
   ```

2. **Rate Limiting**: Per-IP request rate limits
   ```toml
   [waf.adaptive]
   enabled = true

   [waf.adaptive.rate_limit]
   requests_per_minute = 60
   burst = 20

   [waf.adaptive.scoring]
   # Points per violation type (like fail2ban severity)
   critical = 100    # Instant block
   high = 50
   medium = 20
   low = 5

   # Block threshold (like fail2ban maxretry, but score-based)
   block_threshold = 100

   # Score decay (points per minute) - scores expire over time
   decay_rate = 10

   # Block duration (like fail2ban bantime)
   block_duration = "1h"

   # Escalation: after N temporary bans, escalate to firewall
   escalate_after_bans = 3
   ```

3. **Auto-Ban**: Automatic temporary bans for high-scoring IPs

4. **Escalation**: Repeat offenders escalate to kernel firewall for longer bans

### Phase 3: Network Firewall Integration

**Goal**: Kernel-level IP blocking for persistent threats

1. **Firewall Backend**: Support for iptables and nftables
   ```python
   class IptablesFirewall:
       """iptables-based firewall implementation."""

   class NftablesFirewall:
       """nftables-based firewall implementation."""
   ```

2. **WAF-Firewall Integration**: Adaptive WAF escalates to firewall
   ```toml
   [firewall]
   enabled = true
   backend = "nftables"    # or "iptables"

   [firewall.auto_block]
   enabled = true
   # Escalate to firewall after N WAF blocks
   waf_block_threshold = 5
   # Block duration (0 = permanent until manual unblock)
   duration = "1h"
   ```

3. **CLI Commands**:
   ```bash
   hop3 firewall:list                    # List blocked IPs
   hop3 firewall:block 1.2.3.4 --duration=24h
   hop3 firewall:block 10.0.0.0/8 --permanent
   hop3 firewall:unblock 1.2.3.4
   hop3 firewall:sync                    # Sync from adaptive WAF
   ```

### Phase 4: Coraza Integration (Performance)

**Goal**: High-performance WAF engine option

1. **Coraza Plugin**: Implement `CorazaPlugin`:
   - Go binary or gRPC service
   - Same configuration interface as LeWAF
   - Higher throughput (~50k req/s vs ~1k req/s)

2. **Engine Selection**:
   ```toml
   [waf]
   engine = "coraza"  # Switch from LeWAF to Coraza
   ```

### Phase 5: Anti-Bot Integration (Future)

**Goal**: Protection against AI crawlers and bots

1. **Anubis Integration**: Proof-of-work challenges
2. **Browser Fingerprinting**: JA4, THR1
3. **CAPTCHA Support**: hCaptcha, Turnstile

(Deferred - not in current scope)

---

## Detailed Design

### Logging Architecture

WAF events require a separate log stream from application logs. This introduces a **multi-stream logging subsystem**:

```
┌─────────────────────────────────────────────────────────────────────┐
│                      Hop3 Logging Subsystem                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Stream 1: Application Logs                                         │
│            └── stdout/stderr from apps, access logs                 │
│            └── Location: /var/hop3/log/apps/<app>/                  │
│                                                                     │
│  Stream 2: WAF Audit Logs                                           │
│            └── Attack detection, blocked requests, rule matches     │
│            └── Location: /var/hop3/log/waf/                         │
│            └── Format: JSON (structured for analysis)               │
│                                                                     │
│  Stream 3: Firewall Logs                                            │
│            └── IP blocks/unblocks, policy changes                   │
│            └── Location: /var/hop3/log/firewall/                    │
│                                                                     │
│  Stream 4: System Logs                                              │
│            └── Hop3 server operations, deployments                  │
│            └── Location: /var/hop3/log/system/                      │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

#### WAF Log Format

WAF logs use structured JSON for easy parsing and analysis:

```json
{
  "timestamp": "2025-12-03T10:30:45.123Z",
  "transaction_id": "abc123",
  "app": "myapp",
  "client_ip": "1.2.3.4",
  "request": {
    "method": "POST",
    "uri": "/api/users",
    "headers": {"user-agent": "curl/7.88.1"}
  },
  "matches": [
    {
      "rule_id": "942100",
      "rule_msg": "SQL Injection Attack Detected",
      "severity": "critical",
      "matched_data": "1 OR 1=1",
      "matched_var": "ARGS:id"
    }
  ],
  "action": "blocked",
  "response_code": 403,
  "processing_time_ms": 2.3
}
```

#### Log Access

```bash
# View WAF logs for all apps
hop3 logs:waf

# View WAF logs for specific app
hop3 logs:waf myapp

# View firewall logs
hop3 logs:firewall

# Stream logs in real-time
hop3 logs:waf --follow

# Filter by severity
hop3 logs:waf --severity=critical

# Export for analysis
hop3 logs:waf --format=json --since="1 hour ago" > waf-events.json
```

#### Log Rotation and Retention

```toml
# /etc/hop3/server.conf
[logging]
# Retain WAF logs for 30 days
waf_retention_days = 30

# Retain firewall logs for 90 days
firewall_retention_days = 90

# Max log file size before rotation
max_file_size = "100MB"

# Compress rotated logs
compress = true
```

### Plugin Architecture

```
hop3/plugins/security/
├── __init__.py
├── waf/
│   ├── __init__.py
│   ├── plugin.py           # WAF plugin registration
│   ├── engine.py           # WafEngine protocol
│   ├── rules.py            # Rule compilation (simple → CRS)
│   ├── logging.py          # WAF audit logging
│   ├── lewaf/
│   │   ├── __init__.py
│   │   ├── service.py      # LeWAF service management
│   │   ├── config.py       # Rule configuration
│   │   └── templates/      # Config templates
│   └── coraza/             # Future: Coraza integration
│       └── ...
├── adaptive/
│   ├── __init__.py
│   ├── plugin.py           # Adaptive WAF plugin
│   ├── scoring.py          # IP scoring system
│   └── rate_limit.py       # Rate limiting
├── firewall/
│   ├── __init__.py
│   ├── plugin.py           # Firewall plugin
│   ├── iptables.py         # iptables backend
│   └── nftables.py         # nftables backend
└── antibot/                # Future: anti-bot features
    └── ...
```

### Service Management

WAF services are managed alongside applications:

```
/var/hop3/
├── run/
│   ├── nginx/              # Reverse proxy
│   ├── waf/                # WAF service (single instance for all apps)
│   │   ├── lewaf.sock
│   │   └── lewaf.pid
│   └── firewall-agent/     # Privileged firewall agent (if enabled)
│       └── firewall.sock
├── config/
│   ├── waf/
│   │   ├── crs/            # OWASP CRS rules
│   │   ├── apps/           # Per-app rule configurations
│   │   │   ├── myapp.yaml
│   │   │   └── otherapp.yaml
│   │   └── lewaf.yaml      # Global LeWAF configuration
│   └── firewall/
│       └── blocked.db      # Persistent blocklist (SQLite)
└── log/
    ├── waf/
    │   └── audit.log       # WAF audit log
    └── firewall/
        └── actions.log     # Firewall block/unblock events
```

### Proxy Integration

The existing proxy plugins (Nginx, Caddy, Traefik) need modification to route traffic through WAF:

```python
# In NginxVirtualHost.generate_config()
def _generate_upstream_config(self) -> str:
    if self.waf_enabled:
        # Route through WAF service
        return f"""
upstream {self.app_name}_waf {{
    server unix:/var/hop3/run/waf/lewaf.sock;
}}
"""
    else:
        # Direct to app
        return f"""
upstream {self.app_name}_app {{
    server unix:{self.workers['web']};
}}
"""
```

### Configuration Flow

```
1. App deployed → hop3.toml parsed
2. WAF settings extracted → WAF plugin notified
3. WAF plugin generates app-specific config
4. WAF service reloaded (if running)
5. Proxy config regenerated to route through WAF
6. Proxy reloaded
```

---

## Consequences

### Benefits

1. **Defense in Depth**: Multiple layers of protection (Static WAF + Adaptive WAF + Network Firewall)
2. **Flexibility**: Enable/disable per application
3. **Compatibility**: Works with all proxy backends (Nginx, Caddy, Traefik)
4. **Standards Compliance**: OWASP CRS for industry-standard protection
5. **Simple Configuration**: Sensible defaults with `hop3.toml` customization
6. **No Docker Required**: Pure Python stack (LeWAF)

### Drawbacks

1. **Performance Overhead**: Additional latency (1-5ms for LeWAF inspection)
2. **Resource Usage**: Additional services consume memory/CPU
3. **Complexity**: More moving parts to manage and debug
4. **False Positives**: WAF rules may block legitimate requests (requires tuning)

### Trade-offs

| Aspect | Decision | Trade-off |
|--------|----------|-----------|
| Performance vs Security | Security first | Accept 1-5ms overhead |
| Simplicity vs Features | Layered approach | MVP first, then advanced features |
| Per-app vs Server-wide | Both | Per-app config with server-wide service |
| LeWAF vs ModSecurity | LeWAF (Python) | Easier debugging, slower performance |

---

## Alternatives Considered

### 1. No Built-in WAF

Let users configure their own WAF at the infrastructure level.

**Rejected**: Contradicts research contract requirements and leaves applications unprotected by default.

### 2. ModSecurity Only

Use ModSecurity compiled into NGINX.

**Rejected**: Adds significant build complexity, requires C/Lua debugging, conflicts with Hop3's simplicity goals.

### 3. Cloud WAF (Cloudflare, etc.)

Recommend external WAF services.

**Rejected**: Doesn't work for self-hosted/air-gapped deployments, adds external dependency.

### 4. Full Paf le WAF Platform

Build the complete LeWAF platform with orchestrator, UI, etc.

**Rejected for MVP**: Too much development effort. Could be Phase 5+ goal.

---

## Prior Art

- **BunkerWeb**: NGINX + ModSecurity + Lua + Python orchestration. Inspired the Paf le WAF architecture but too complex for Hop3's needs.
- **Cloudflare WAF**: Cloud-based, per-request pricing, excellent UX. Model for configuration simplicity.
- **AWS WAF**: Rule-based, integrates with ALB/CloudFront. Good per-app configuration model.
- **Dokku + nginx-waf**: Community plugin approach. Validates plugin architecture.

---

## Resolved Questions

These questions were raised during design and have been resolved:

1. **LeWAF vs Coraza Go**: *Resolved* - WAF is pluggable. Start with LeWAF, add Coraza later for performance (if needed).

2. **Anubis JavaScript requirement**: *Resolved* - Anti-bot (including Anubis) is deferred to Phase 5.

3. **Audit logging**: *Resolved* - WAF logs are a separate stream from application logs. Multiple log streams are managed by a logging subsystem (see Logging Architecture section).

4. **Priority**: *Resolved* - WAF first (both static and adaptive), then network firewall, then anti-bot.

5. **Simple Rule Priority**: *Resolved* - Processing order is: IP allowlist → IP denylist → Path allowlist → Path denylist → CRS rules → Adaptive WAF. Allowlists take precedence, denylists block before expensive CRS processing. See "Rule Processing Order" section.

6. **Adaptive WAF Storage**: *Resolved* - In-memory cache for fast lookups + SQLite persistence for durability. Sync every 60 seconds and on graceful shutdown. See "Adaptive WAF Storage" section.

7. **Firewall Privileges**: *Resolved* - Separate firewall agent process with CAP_NET_ADMIN capability, communicates with Hop3 server via Unix socket IPC. See "Network Firewall Agent" section.

8. **Single vs Multi-Instance WAF**: *Resolved* - Single LeWAF service handles all applications, with per-app configuration loaded dynamically based on Host header. See "Single WAF Instance Architecture" section.

## Unresolved Questions

1. **CRS Rule Updates**: How do we update OWASP CRS rules without app redeployment? Options:
   - Separate CRS package with its own update mechanism
   - Pull latest CRS on server restart
   - Manual updates via CLI command

2. **Multi-instance Hop3**: How does WAF work in distributed deployments? Each instance has its own WAF, but:
   - Should adaptive scoring be shared across instances?
   - Should firewall blocks be synchronized?

3. **Performance Threshold**: At what traffic level should we recommend switching from LeWAF to Coraza? Need benchmarks.

4. **Fail-Open vs Fail-Closed**: If WAF service fails:
   - Fail-open: Allow traffic through (availability over security)
   - Fail-closed: Block traffic (security over availability)
   - Configurable per-app?

5. **Firewall Persistence**: How are firewall rules persisted across server reboots?
   - Store in database and replay on boot?
   - Use iptables-persistent / nftables native persistence?
   - Likely: Both (SQLite for Hop3 state, native persistence for system rules)

---

## Future Work

### In Scope (This ADR)

1. **Phase 1**: Static WAF with LeWAF + simple rules
2. **Phase 2**: Adaptive WAF with scoring and rate limiting
3. **Phase 3**: Network firewall integration (iptables/nftables)
4. **Phase 4**: Coraza integration for performance

### Deferred (Future ADRs)

1. **Anti-Bot Layer**: Anubis, proof-of-work, CAPTCHA integration
2. **IP Reputation**: Integration with AbuseIPDB, IPQualityScore
3. **ML-based Detection**: Behavioral analysis for sophisticated threats
4. **WAF Dashboard**: Metrics, log viewer, rule tuning UI
5. **GeoIP Blocking**: Block by country/region
6. **Full Paf le WAF Platform**: If enterprise features are needed
7. **fail2ban Integration**: Optional integration with fail2ban for non-web log monitoring (SSH, mail, custom app logs). The Adaptive WAF covers web traffic; fail2ban could complement it for:
   - SSH brute force attacks
   - Mail server abuse
   - Custom application authentication failures
   - Any log-based pattern matching beyond WAF scope

   *To be re-investigated once Adaptive WAF is proven in production.*

---

## References

- [OWASP Core Rule Set (CRS)](https://coreruleset.org/)
- [LeWAF GitHub](https://github.com/abilian/lewaf) - Pure Python WAF engine
- [Anubis GitHub](https://github.com/TecharoHQ/anubis) - Proof-of-work anti-AI scraper
- [ModSecurity Documentation](https://github.com/owasp-modsecurity/ModSecurity)
- [Coraza WAF (Go)](https://coraza.io/)
- [The Open-Source Software Saving the Internet From AI Bot Scrapers (404 Media)](https://www.404media.co/the-open-source-software-saving-the-internet-from-ai-bot-scrapers/)
- [Anubis: Fighting off the hordes of LLM bot crawlers (The Register)](https://www.theregister.com/2025/07/09/anubis_fighting_the_llm_hordes/)
- [BunkerWeb Architecture](https://docs.bunkerweb.io/)

---

## Appendix A: LeWAF SecLang Example

```apache
# Basic XSS protection
SecRule ARGS "@detectXSS" \
    "id:1001,\
    phase:2,\
    deny,\
    status:403,\
    msg:'XSS Attack Detected',\
    tag:'attack/xss'"

# Block AI crawlers
SecRule REQUEST_HEADERS:User-Agent "@rx (GPTBot|ChatGPT-User|Claude-Web|anthropic-ai)" \
    "id:9001,\
    phase:1,\
    deny,\
    status:403,\
    msg:'AI crawler blocked',\
    tag:'bot/ai-crawler'"

# Rate limiting (with LeWAF extension)
SecAction \
    "id:9010,\
    phase:1,\
    ratelimit:30/60/client_ip,\
    deny,\
    status:429,\
    msg:'Rate limit exceeded'"
```

## Appendix B: hop3.toml Configuration Reference

```toml
# =============================================================================
# Simple Security Rules (no CRS knowledge required)
# =============================================================================

[security.rules]
# Allowlist - these paths bypass WAF inspection entirely
allow = [
    "/health",
    "/api/webhook/*",
    "/.well-known/*",
]

# Denylist - these paths are blocked (403 Forbidden)
deny = [
    "/wp-admin/*",           # Block WordPress admin probes
    "/phpmyadmin/*",         # Block phpMyAdmin probes
    "/xmlrpc.php",           # Block XML-RPC attacks
    "*.php",                 # Block PHP file requests (for non-PHP apps)
]

# IP allowlist (bypass all security checks)
allow_ips = [
    "10.0.0.0/8",            # Internal network
    "192.168.0.0/16",        # Local network
    "172.16.0.0/12",         # Docker network
]

# IP denylist (blocked at WAF level)
deny_ips = [
    "1.2.3.4",               # Known attacker
    "5.6.7.0/24",            # Suspicious range
]

# =============================================================================
# WAF Configuration (Static WAF - CRS Rules)
# =============================================================================

[waf]
# Enable WAF for this application
enabled = true

# WAF engine: "lewaf" (default), "coraza" (future)
engine = "lewaf"

# Ruleset to use: "owasp-crs" (default), "minimal", "none"
ruleset = "owasp-crs"

# Paranoia level: 1 (balanced) to 4 (strict)
# Higher levels = more rules, more false positives
paranoia_level = 1

# WAF mode: "block" (default) or "detect" (log only, don't block)
mode = "block"

# Anomaly scoring threshold (lower = stricter)
# Default: 5 for requests, 4 for responses
anomaly_threshold = 5

[waf.crs]
# Custom SecLang rules (appended to CRS - for advanced users)
custom = """
# Example: Additional SQL injection pattern
SecRule ARGS "@detectSQLi" "id:100001,deny,status:403,msg:'Custom SQLi rule'"
"""

[waf.exclusions]
# Paths excluded from CRS inspection (simple rules still apply)
paths = ["/api/raw-data"]

# Specific CRS rule IDs to disable (for false positive tuning)
rule_ids = [920350, 942100]

# =============================================================================
# Adaptive WAF Configuration
# =============================================================================

[waf.adaptive]
# Enable adaptive WAF (behavioral analysis)
enabled = true

[waf.adaptive.rate_limit]
# Per-IP rate limiting
requests_per_minute = 60
burst = 20

[waf.adaptive.scoring]
# Points assigned per violation severity
critical = 100    # Instant block
high = 50
medium = 20
low = 5

# Score threshold to trigger block
block_threshold = 100

# Score decay rate (points per minute)
decay_rate = 10

# Block duration (seconds) when threshold exceeded
block_duration = 3600  # 1 hour

# =============================================================================
# Network Firewall Configuration
# =============================================================================

[firewall]
# Enable kernel-level firewall management
enabled = true

# Backend: "nftables" (preferred) or "iptables"
backend = "nftables"

[firewall.auto_block]
# Automatically escalate to firewall from adaptive WAF
enabled = true

# Escalate after N WAF blocks from same IP
waf_block_threshold = 5

# Block duration at firewall level
duration = "24h"

# =============================================================================
# Anti-Bot Configuration (FUTURE - Phase 5)
# =============================================================================

# [antibot]
# enabled = false
# provider = "anubis"
# ...
```

## Appendix C: Service Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              Hop3 Server                                │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                           Request Flow                            │  │
│  │                                                                   │  │
│  │                           Internet                                │  │
│  │                               │                                   │  │
│  │                               ▼                                   │  │
│  │  ┌────────────────────────────────────────────────────────────┐   │  │
│  │  │  Layer 1: Network Firewall (iptables/nftables)             │   │  │
│  │  │           Blocked IPs rejected at kernel level             │   │  │
│  │  └────────────────────────────┬───────────────────────────────┘   │  │
│  │                               │                                   │  │
│  │                               ▼                                   │  │
│  │  ┌────────────────────────────────────────────────────────────┐   │  │
│  │  │  Reverse Proxy (Nginx/Caddy/Traefik)                       │   │  │
│  │  │  Routes to WAF service or directly to app                  │   │  │
│  │  └────────────────────────────┬───────────────────────────────┘   │  │
│  │                               │                                   │  │
│  │                               ▼                                   │  │
│  │  ┌────────────────────────────────────────────────────────────┐   │  │
│  │  │  Layer 2: Static WAF (LeWAF/Coraza)                        │   │  │
│  │  │           CRS rules, custom rules, simple allow/deny       │   │  │
│  │  └────────────────────────────┬───────────────────────────────┘   │  │
│  │                               │                                   │  │
│  │                               ▼                                   │  │
│  │  ┌────────────────────────────────────────────────────────────┐   │  │
│  │  │  Layer 3: Adaptive WAF                                     │   │  │
│  │  │           Rate limiting, IP scoring, auto-ban              │   │  │
│  │  │           Can escalate to Network Firewall                 │   │  │
│  │  └────────────────────────────┬───────────────────────────────┘   │  │
│  │                               │                                   │  │
│  │                               ▼                                   │  │
│  │  ┌────────────────────────────────────────────────────────────┐   │  │
│  │  │  Application (uWSGI, Gunicorn, Node, etc.)                 │   │  │
│  │  └────────────────────────────────────────────────────────────┘   │  │
│  │                                                                   │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                        Supervisor Managed                         │  │
│  │                                                                   │  │
│  │   [nginx]  [hop3-waf]  [app1-web]  [app2-web]  ...                │  │
│  │                                                                   │  │
│  │   Note: hop3-waf = LeWAF + Adaptive WAF (single process)          │  │
│  │                                                                   │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                        Systemd Managed (privileged)               │  │
│  │                                                                   │  │
│  │   [hop3-firewall-agent]  (CAP_NET_ADMIN for iptables/nftables)    │  │
│  │                                                                   │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                           Log Streams                             │  │
│  │                                                                   │  │
│  │   /var/hop3/log/                                                  │  │
│  │   ├── apps/          # Application logs (stdout/stderr)           │  │
│  │   ├── waf/           # WAF audit logs (JSON)                      │  │
│  │   ├── firewall/      # Firewall block/unblock events              │  │
│  │   └── system/        # Hop3 server operations                     │  │
│  │                                                                   │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Appendix D: Security Layer Summary

| Layer | Component | Purpose | Overhead |
|-------|-----------|---------|----------|
| 1 | Network Firewall | Block IPs at kernel level (iptables/nftables) | Near-zero |
| 2 | Static WAF | Simple rules (allow/deny) + CRS rule inspection | 1-5ms |
| 3 | Adaptive WAF | Rate limiting, IP scoring, auto-ban | <1ms |
| 4* | Anti-Bot | Proof-of-work challenges (Anubis) | 50-500ms |

*Phase 5 (deferred)

**Processing order within Layer 2 (Static WAF)**:
1. IP allowlist → 2. IP denylist → 3. Path allowlist → 4. Path denylist → 5. CRS rules
