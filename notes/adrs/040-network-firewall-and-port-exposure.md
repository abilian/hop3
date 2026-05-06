# ADR 040: Network firewall and per-app port exposure

**Status**: Draft — design phase
**Type**: Feature
**Created**: 2026-04-25
**Updated**: 2026-05-01
**Related-ADRs**: 010 (security and resilience), 016 (backups), 033 (docker integration), 038 (multi-service apps), 041 (privileged operations agent — supersedes the sudo/wrapper privilege-handling sketched here)
**Related-deliverable**: NGI 0.5 — "Security will be fortified with network-level firewalls and a Web Application Firewall (WAF) using tools like OWASP Core Ruleset and Coraza."

## Revisions

- v0.3: Privilege-handling deferred to ADR 041 (now v0.2 after a design-grilling session). ADR 041 settles: rootd is a pure executor with no policy file (no auto_allow / prompt / deny outcomes); deploy-time confirmation lives in the CLI as a y/N summary computed from the firewall delta vs the previous deploy; nftables only in v1 with a dedicated `inet hop3` table; cloud-firewall plugins call provider APIs directly from hop3-server. The grant lifecycle described in this ADR (open on deploy, close on destroy) flows through rootd's `firewall.add_rule` / `firewall.remove_rule` ops; the `[[expose]]` schema gains an optional `description` field surfaced in the y/N prompt and audit log (2026-05-01).
- v0.2: Privilege-handling pointer added — ADR 041 introduces `hop3-rootd`, a small Python daemon that supersedes the sudoers-fragment / setuid-binary approaches implied here. The grant lifecycle in this ADR (open on deploy, close on destroy) flows through hop3-rootd's `firewall.add_rule` / `firewall.remove_rule` ops; cloud-provider firewall integration uses the same `Firewall` plugin protocol but bypasses hop3-rootd (calls cloud APIs directly with operator credentials). See ADR 041 for the agent design (2026-04-24).
- v0.1: Initial draft (2026-04-25). Proposes declarative per-app port exposure backed by an installer-managed L3/L4 firewall. Explicitly defers the WAF half of the NGI commitment to a separate ADR.

## Context

The 2026-05 internal security audit flagged that Hop3 ships **zero** firewall configuration: addon ports (3306, 5432, 6379) and high uWSGI app ports are internet-facing on a default cloud VM. The MySQL installer's own comment delegates security to "firewall/iptables" — but the installer doesn't deploy any. The audit's "Wave 5" remediation proposal was a platform-level baseline of "ufw allow OpenSSH/80/443, deny rest".

That model is too simplistic for what Hop3 actually packages. **Several apps already in the catalog need ports beyond 22/80/443:**

- **Gitea / Forgejo** — TCP 22 (or alt) for SSH-based `git push/pull`.
- **Matrix-synapse** — TCP 8448 for server-to-server federation.
- **Owncast** — TCP 1935 for RTMP ingest. The product is unusable without it.
- **Jenkins** — TCP 50000 (default JNLP) for build agents.
- **Mattermost** — voice/video calls via Coturn (UDP 3478/5349 + relay range).

And the future catalog widens further. Self-hosted alternatives that fit Hop3's sovereignty-focused vision routinely need non-HTTP ports:

- **Mail servers** (Stalwart, Maddy, etc.) — TCP 25/465/587/993/995. The whole product depends on these ports being reachable from the public Internet.
- **Jitsi Meet** — UDP 10000 for media + TCP fallback + Coturn relay range.
- **AdGuard Home / Pi-hole** — UDP/TCP 53 (DNS), optional 853 (DoT), 5443 (DoH).
- **WireGuard / Headscale** — UDP 51820 (or operator-chosen).
- **Mosquitto / MQTT** — TCP 1883, 8883 (TLS).
- **Prosody / XMPP** — TCP 5222 (client), 5269 (federation), 5280 (BOSH).
- **Plex / Jellyfin** — TCP 32400 / 8096 + DLNA.

A "deny by default, allow only 22/80/443" platform firewall would silently break *currently-shipped* applications. The firewall design therefore cannot be installer-only; it has to participate in the **app deploy / destroy lifecycle**.

### Two failures the audit didn't separate

The Wave 5 plan bundled "network-level firewall" as one item. In practice it's two distinct concerns:

1. **Platform baseline.** Drop everything on the wire that doesn't belong to a Hop3-managed service (SSH for operators, nginx for HTTP/S, addons bound only where addon topology says). One-shot, installer-time. Static.
2. **Per-app port exposure.** Some apps need additional inbound ports. Each app declares what it needs; Hop3 reconciles the firewall against those declarations. Lifecycle-aware: open on deploy, close on destroy, diff-and-apply on config change.

The audit collapsed these into one item. They are different decisions with different blast radii and merit separate sections in this ADR.

### What the NGI deliverable promised

> "Security will be fortified with **network-level firewalls** and a **Web Application Firewall (WAF)** using tools like OWASP Core Ruleset and Coraza."

The two halves are at different OSI layers:

- L3/L4 firewall (this ADR) — drops packets by IP/port/protocol before any service sees them. ufw on Debian/Ubuntu, firewalld on RHEL/Fedora.
- L7 WAF (separate ADR, deferred) — inspects HTTP requests for SQLi/XSS/RCE patterns. Coraza or libmodsecurity in front of nginx, with the OWASP Core Rule Set. Substantial work in its own right (rule tuning, false-positive management, per-app exemptions, log pipeline). Deserves its own ADR; tracked as a follow-up.

This ADR addresses only the L3/L4 piece. The WAF piece is referenced as a future commitment but its design is out of scope here.

### Docker interaction

Docker writes its own iptables rules in the `DOCKER` chain ahead of any rules ufw inserts. A docker-compose `ports:` declaration like `"1935:1935"` makes the port reachable from the public Internet *regardless of the host firewall*. This means:

- A "deny by default" host firewall is undermined by any container that publishes a port — visible reachable, but not visible *to ufw*, so operators can't audit it via `ufw status`.
- For app-declared exposures to be the single source of truth, Hop3 must not let docker-compose publish ports unilaterally. Either rewrite generated compose files to bind container ports to `127.0.0.1` and let ufw forward inbound traffic, or require operators to use Hop3's `[[expose]]` mechanism instead of compose-level `ports:`.

The right resolution here is non-trivial and is itself an open question (see "Open questions").

## Decision (proposed)

### 1. Platform firewall baseline

The installer ships a `configure_firewall()` step that, on **fresh installs**, applies a default ufw policy:

- Allow inbound: SSH (port detected from sshd_config; default 22), HTTP (80), HTTPS (443).
- Allow outbound: all (apps need to make outbound API calls, fetch packages, deliver mail, etc.).
- Default policy: deny inbound.
- Enable ufw.
- Write a marker `/etc/hop3/firewall-managed` recording that Hop3 owns the firewall.

On RHEL/Fedora hosts (firewalld available, ufw not), the equivalent `firewall-cmd` calls apply. On hosts where neither is available, the installer prints a clear instruction and skips auto-management.

Opt-out: `hop3-install server --no-firewall` skips the entire step (CI containers, embedded environments, operators with their own iptables setup).

On **upgrades** (marker file already present), the installer never touches firewall rules unless `hop3-install server --reconfigure-firewall` is passed. This avoids locking out operators whose post-install adjustments would otherwise be silently reverted.

### 2. Per-app `[[expose]]` declarations

Apps declare additional inbound ports in `hop3.toml`:

```toml
[[expose]]
port = 1935
protocol = "tcp"
description = "RTMP ingest for streamers"
```

Schema:

- `port` — required, integer 1-65535.
- `protocol` — required, one of `"tcp"`, `"udp"`. Multiple entries allowed for protocols that need both.
- `description` — optional, free-text. Surfaced in deploy logs and dashboard so operators can audit "why is this open?"
- `port-range` — optional alternative to `port`, format `"start-end"`. For e.g. Coturn relay (`49152-65535/udp`). Range size capped at 16384 to prevent denial-of-firewall via a million-rule explosion.
- `source` — optional, default `"any"`. CIDR or `"any"`. Allows e.g. `"10.0.0.0/8"` for VPN-only services.

Example for Matrix-synapse with Coturn sidecar:

```toml
[[expose]]
port = 8448
protocol = "tcp"
description = "Matrix federation"

[[expose]]
port = 3478
protocol = "udp"
description = "Coturn STUN"

[[expose]]
port-range = "49152-65535"
protocol = "udp"
description = "Coturn relay"
```

The default for any app *without* an `[[expose]]` block is "no extra ports" — apps reachable only via nginx (HTTP/S apps) need no declaration.

### 3. Lifecycle: open on deploy, close on destroy

The deployer reconciles ufw rules against the app's `[[expose]]` declarations:

- **On deploy / redeploy:** compute the desired set of (port, protocol, source) tuples, diff against current rules tagged with the app name, apply the diff. New rules are tagged with a comment containing the app name (`ufw allow ... comment 'hop3-app:<name>'`) so they're discoverable and removable.
- **On destroy:** remove all rules tagged with the app name.
- **On config change:** the deployer re-runs the reconciliation. Removed `[[expose]]` entries close their ports; added entries open theirs.
- **At server startup:** an idempotency check rebuilds the desired-state from the database of deployed apps and applies any missing rules (covers the "operator manually deleted a rule" case).

### 4. Operator visibility

- Deploy log surfaces `Opening port 1935/tcp for app 'owncast' — RTMP ingest`.
- Dashboard shows a per-app "Exposed ports" panel.
- A `hop3 firewall list` command prints all Hop3-managed rules with their owning app and description.
- A `hop3 firewall verify` command warns when ufw is disabled, when rules drift from declarations, or when Docker-published ports exist that aren't covered by an `[[expose]]` block.

### 5. Docker interaction (provisional)

Generated compose files will bind container ports to `127.0.0.1` rather than `0.0.0.0`, e.g.:

```yaml
ports:
  - "127.0.0.1:1935:1935"
```

Inbound traffic from outside the host arrives at ufw, which forwards to the container's loopback-bound port. This makes ufw the single source of truth.

For user-supplied compose files (where Hop3 doesn't own the YAML), the deployer parses the file at deploy time, warns about any `0.0.0.0:N:M` publish without a matching `[[expose]]` declaration, and either (a) refuses the deploy unless the operator confirms with `--allow-unmanaged-ports`, or (b) auto-rewrites the bind to `127.0.0.1` (operator pref TBD — see Open Questions).

### 6. Out of scope (this ADR)

- **WAF / Layer 7 inspection.** Coraza + OWASP CRS in front of nginx. Separate ADR.
- **Per-app rate limiting.** Already partially in `server/security/rate_limit.py`; not a firewall concern.
- **Cloud-provider firewall integration** (AWS Security Groups, Hetzner Cloud Firewalls). Operators who use those layer them on top; Hop3 doesn't manage them.
- **IPv6 source restrictions.** ufw handles IPv6 automatically when enabled; the `source = "10.0.0.0/8"` syntax above is IPv4-only for the first cut.

## Consequences

### Positive

- Closes the externally-reachable addon-listener and high-app-port surface that the audit flagged, without breaking apps that legitimately need non-HTTP ports.
- Apps that need network-level visibility (mail, video, DNS, VPN) become first-class citizens. Today they don't exist in the catalog because they'd be silently broken; this ADR makes them deployable.
- Operators get an audit trail: every open port has an owning app and a description.
- The `[[expose]]` block is self-documenting. Reviewing an app's `hop3.toml` answers "what does this app expose?" before deploying.
- Sets up the Scalingo-style "publicly accessible addon" 0.6 feature cleanly: an addon's `public = true` just synthesises an `[[expose]]` entry under the addon's own deployment.

### Negative

- New schema in `hop3.toml`. Existing apps need no change (default = no extra ports), but documentation, tutorials, and the schema validator all need updates.
- The Docker port-publishing rework is real engineering work. We've been letting compose handle inbound traffic for a year; reverting to "ufw forwards to loopback-bound containers" requires careful testing across docker-compose versions.
- Firewall reconciliation introduces a new failure mode: deploy succeeds at the app level but the firewall step fails (e.g., sudo timeout, ufw rule conflict). Need clear rollback and operator-facing diagnostics.
- Per-app `--reconfigure-firewall` invitations on upgrades will catch some operators who manually adjusted rules outside Hop3's view.

### Operational

- New install-time decision: `--no-firewall` opt-out for CI / unusual environments.
- New `hop3 firewall ...` admin commands.
- Documentation: a single reference page explaining the model, the `[[expose]]` schema, and the Docker-port-publishing change. Plus migration notes for existing operators on upgrade.

## Alternatives considered

### A. Platform-level firewall only; no per-app declarations

The simplest model: ufw allow 22/80/443, deny rest, done. Same as the original Wave 5 proposal.

Rejected because it silently breaks Owncast, Gitea SSH, Matrix federation, Jenkins, and most of the future catalog Hop3 plausibly wants to support.

### B. No firewall; rely on operators

Status quo. Rejected because:

- The 2026-05 audit explicitly flagged it as the largest external attack surface.
- The NGI deliverable explicitly committed to network-level firewalls.
- The MySQL installer's existing code already comments "rely on firewall/iptables for security" — code documenting a dependency it doesn't enforce.

### C. Cloud-provider firewall integration

Defer all firewall management to AWS Security Groups, Hetzner Cloud Firewalls, etc. Hop3 stays out of iptables.

Rejected as a primary mechanism because it's cloud-specific and doesn't help operators on bare metal, OVH dedicated, Hetzner servers (separate from Cloud), or local VMs. Could be a *complementary* deliverable later (Hop3 emits a JSON description of its desired firewall state, and an integration script applies it to AWS Security Groups), but not the baseline.

### D. nftables instead of ufw / iptables

nftables is the modern replacement for iptables. It's cleaner and supported on all current distros.

Plausible but adds a third backend (ufw, firewalld, nftables) and operator familiarity is lower. Defer to a possible follow-up ADR; ufw and firewalld both ultimately produce nftables rules on current systems anyway.

### E. Deny-list rather than allow-list

"Open everything by default; explicitly close known-dangerous ports." Reverses the default.

Rejected — modern security practice is firmly allow-list. The deliverable framing ("network-level firewalls") implies allow-list as well.

## Open questions

1. **Docker port-publishing rewrite.** Is the right answer to (a) generate compose files with `127.0.0.1:N:M` and forward through ufw, (b) refuse deploys with `0.0.0.0` published ports unless `--allow-unmanaged-ports`, (c) auto-rewrite user-supplied compose files, or (d) some combination? Need a small experiment with a couple of catalog apps to see what breaks.

2. **`source` granularity for IPv6.** The `source = "10.0.0.0/8"` field needs an IPv6 cousin. Should we accept comma-separated mixed lists, or require `source-v4` / `source-v6` keys?

3. **Coturn-style large port ranges.** The 16384-port-range cap proposed above is arbitrary. Is that the right ceiling? Some operators might need wider relay ranges for high-volume video conferencing.

4. **What happens on firewall failure mid-deploy?** If ufw is broken or sudo times out during the reconciliation step, the app may already be running but its declared ports aren't open. Should the deploy fail loudly (and roll back the app), succeed with a warning, or retry?

5. **Existing-install upgrade path.** Marker file is the proposal, but we need to decide whether re-running the installer with the marker present should be silent (current proposal) or print the current rule set so operators can confirm.

6. **Audit log of firewall changes.** Every rule addition/removal should land in a log somewhere — the `hop3.db` audit table? a dedicated firewall log? syslog? — for after-the-fact incident review.

7. **Interaction with the addon-binding topology** from the Wave 5 review note. The topology marker (`native` / `docker` / `mixed`) decides where addons listen. Does the firewall reconciliation need to know the topology, or is the addon installer's bind-address choice already sufficient?

8. **Self-hosted-mail port 25 problem.** Many ISPs and cloud providers block outbound port 25 to fight botnets. A mail-server app would deploy successfully and `[[expose]] port = 25` would open the firewall, but outbound delivery still fails. Hop3 should detect this at deploy time and warn the operator. Out of scope for the firewall mechanism itself but worth a note.

## Implementation sketch

Phasing if accepted:

- **Phase 1 (Wave 5 of the security remediation):** platform baseline only. Installer adds `configure_firewall()`. No per-app declarations yet. Existing apps that need non-HTTP ports (Gitea SSH, Owncast, Matrix federation, Jenkins) get hand-added rules via a transitional `hop3.toml` field or an installer flag, to keep the catalog working until Phase 2 ships.
- **Phase 2 (post-0.5):** schema for `[[expose]]`, deployer reconciliation, dashboard panel, `hop3 firewall ...` commands, the Docker port-publishing rework. This is a non-trivial chunk; probably a 0.6 milestone.
- **Phase 3 (0.6 or later):** WAF (separate ADR), cloud-provider firewall integration adapter (if demand exists), nftables backend (if there's value over ufw/firewalld).

The Phase-1 / Phase-2 split avoids blocking the 0.5 tag on the full design, while still delivering on the "network-level firewalls" half of the NGI commitment in 0.5.

## References

- ADR 041 — Privileged operations agent (`hop3-rootd`): the kernel-boundary executor that v0.3 of this design routes nft mutations through.
- NGI 0.5 project plan: `notes/ngi-2024/project-plan.md`
- ADR 010 (security and resilience), ADR 033 (docker integration), ADR 038 (multi-service apps)
