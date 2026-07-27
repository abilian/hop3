# ADR 045: Fixed-Port Registry: Exclusive Host Ports for Non-HTTP Apps

- **Status**: Accepted
- **Type**: Architecture
- **Created**: 2026-06-10
- **Supersedes**: [ADR 040](./040-network-firewall-and-port-exposure.md)
- **Related-ADRs**: [041](./041-privileged-operations-agent.md) (privileged-operations-agent), [043](./043-unified-testing-architecture.md) (unified-testing-architecture), [008](./008-nix-builders-2.md) (template-based-nix-expression-generation)

## Context

HTTP/HTTPS is the only protocol Hop3 multiplexes. The reverse proxy (nginx) virtual-hosts by `Host:`, so dozens of apps share `:80`/`:443` with no conflict; each app's web server is assigned a dynamic `$PORT` and proxied. Everything else (SMTP (25/465/587), XMPP (5222/5269), RTMP (1935), Matrix federation (8448), IMAP, TURN, …) has **no proxy and no virtual hosting**. The app binds the host port directly, so physically **exactly one app can own a given (port, protocol) per host**.

Without a registry, Hop3 is blind to those ports. They are baked into the app rather than into `hop3.toml`: e.g. owncast hardcodes RTMP 1935 internally, which appears nowhere in its config. The failure mode (observed with owncast on the Test Lab) is: a second owncast instance, or a leftover one, fails to bind 1935 and crashes on startup, surfacing only as an opaque *"app did not respond to health checks within 120s."* The platform can neither detect the conflict nor explain it.

The user requirement: a user who tries to install a second SMTP server (or XMPP, RTMP, …) must get a **clear error up front (before the install attempt) rather than a confusing system error after the fact.**

This sits on the project's platform-robustness ethos: apps must coexist without interference, and failures must be actionable. It complements the reliable-teardown work (the leftover-process fix in the uWSGI deployer): teardown stops a *previous* instance from holding the port; this ADR stops a *concurrent* second app from silently colliding.

## Goals

1. Let an app declare the fixed host ports it binds directly.
2. Refuse a second app that claims an already-held port **before build**, with a message that names the conflicting app.
3. Open the firewall for a claimed port on successful deploy and close it on teardown.
4. Be a *general* mechanism (any non-HTTP fixed port), not a per-app workaround.
5. Never make conflict-detection depend on a running privileged daemon.

## Decision

**Declaration.** A new `[[ports]]` array in `hop3.toml`, each entry `{ number, protocol = "tcp"|"udp", name? }`. The HTTP port is *not* declared here: it stays dynamic and proxied.

**Registry.** A host-wide `PortClaim` ORM table, unique on `(number, protocol)`, recording the owning app and (once opened) the rootd firewall `rule_id`.

**Pre-flight.** In `do_deploy`, after config/addon processing but **before build**, each declared port is checked against the registry. If another app holds it, the deploy aborts with a `Diagnosis` (`Deployer can't claim port 1935/tcp: already used by app 'owncast-…'`). Otherwise the claim is inserted into the *deploy session*: so a later build/deploy failure rolls it back with the session (no leak). A unique-constraint flush makes concurrent claims race-safe.

**Firewall.** On a *successful* deploy, `open_fixed_ports` calls `firewall.add_rule` via the rootd client ([ADR 041](./041-privileged-operations-agent.md)) and stores the `rule_id`. On teardown, `release_fixed_ports` calls `firewall.remove_rule`; the claim rows are removed by the cascade on app delete. Firewall wiring is **best-effort**: conflict detection is DB-based and does not need rootd, so an unavailable daemon is a warning (the port is claimed but not externally reachable).

The apps that need it are declared accordingly: owncast (`1935/tcp`) and matrix-synapse (`8448/tcp`).

**Reserved ports.** `22`, `80`, and `443` are rejected at schema validation: SSH and the reverse proxy own them (and nginx, which binds 80/443 directly, is not a `PortClaim`, so the registry alone couldn't catch that collision). HTTP apps use `$PORT` and are proxied.

**Reconcile.** A redeploy that drops a previously-declared port releases the stale claim and closes its firewall rule, so a removed or changed port cannot leak or wrongly keep blocking another app.

## Alternatives considered

**Per-app network isolation (network namespace / always-containerize) (rejected.** It does not solve the actual problem: an *external* fixed port must be reachable from outside on one host `IP:port`, which isolation cannot multiplex (the outside world still reaches a single listener). Isolation would only help *internal* (localhost-only) ports) and those are better solved without it (below). The cost (a netns/container per native/nix app) buys nothing for the case at hand.

**Do internal ports need allocation?** Reviewed against real apps, effectively never in a way that needs a *fixed* port or isolation: a bundled datastore should use a Hop3 **addon** (already per-app, collision-free); a frontend↔backend or worker port should be a **dynamic** port Hop3 hands the app via env, or a Unix socket. A hardcoded internal port that can't be configured is a packaging defect. So the future direction for "an app needs a second port" is **dynamic allocation**.

## Deferred / follow-ups

- **Docker port-publishing.** A Docker app's container does not yet publish declared ports to the host. For Docker apps the claim is recorded (so the conflict check still applies) but the firewall is *not* opened; fixed ports currently take effect for native/Nix builds, which bind the host port directly. The shipped Docker variants of owncast/matrix therefore do not declare `[[ports]]`. Plumbing declared ports into the generated compose `ports:` is the follow-up.
- **Operator confirmation ([ADR 041](./041-privileged-operations-agent.md) §9).** This code path opens the firewall rule directly inside `do_deploy`, without the delta-confirmation [ADR 041](./041-privileged-operations-agent.md) envisions for privileged operations (the existing nginx-reload path is likewise direct). The reserved-port guard prevents the worst case (claiming 22/80/443); a general "show the privileged changes, confirm before applying" step across all rootd-driven deploy actions is a separate, cross-cutting follow-up.
- **Source scoping.** A declared port is opened to `any` (the whole internet): correct for the public services this targets, but an optional per-port `source` (CIDR), which rootd already supports, is a planned enhancement.
- **Cross-variant testing.** All variants of a fixed-port app declare the same port; the default test flow destroys each app before the next (releasing the claim), so sequential runs are fine, but a `--keep` run that co-deploys two variants of the same app will (correctly) be refused on the second.

## Consequences

- **Positive:** non-HTTP apps coexist predictably; a conflicting second install fails fast with a clear, pre-build message; ports are firewalled on deploy and freed on teardown; the mechanism is uniform across SMTP/XMPP/RTMP/federation/etc.
- **Positive:** the opaque owncast "health-check timeout" becomes either a clean deploy (port free) or a precise conflict error.
- **Negative / limits:** a fixed port is single-instance per host: by design, you cannot run two apps on the same fixed port (the error explains this). Docker-deployed apps additionally need their container to *publish* the declared port to the host for external reachability; that wiring is a follow-up (the registry + conflict refusal already apply).
- **Migration:** a new `port_claim` table (Alembic migration; `create_all` covers fresh DBs). No change to existing apps that declare no `[[ports]]`.
