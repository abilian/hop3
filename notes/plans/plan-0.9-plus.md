# Plan: 0.9 and beyond

**Created:** 2026-08-01. **Owner:** SF. **Horizon:** after 0.8 ships, so late 2026 onward.
**Siblings:** [`plan-0.7.x.md`](plan-0.7.x.md) (maintenance), [`plan-0.8.md`](plan-0.8.md) (September), [`parked.md`](parked.md) (not scheduled at all).

## What this file is

The queue behind 0.8: work that is wanted, has a design or a design record, and has no date. Unlike [`parked.md`](parked.md), nothing here is held back on purpose: these are simply next, and each will move into a release plan when it earns the slot.

Ordered by how likely each is to be picked up first.

## Security and identity

**Per-app UID separation, second increment (ADR 055).** 0.8 ships the shared `hop3-apps` user, which closes the privilege-escalation path into `hop3-rootd` and stops applications reading the control plane's secrets. It does *not* stop applications interfering with each other: `app_name` is still caller-asserted, so one application can act on another's cgroups, ports and volumes. Per-app `hop3-app-<name>` users are the second increment, and the ADR's open questions (UID allocation and reuse after destroy, the minimal capability set for the process supervisor, groups versus ACLs for addon sockets) need answers first.

**Per-resource ownership (`App.owner`).** Ownership recorded on the row, dispatcher-level authorization, and a migration for existing applications. Needs its own ADR. ADR 011 notes that per-tenant encryption keys only become meaningful once the control plane distinguishes accounts, so this gates that too.

**SSO / identity management.** Evaluate Canaille as an IDM component, design an OAuth2/OIDC gateway, prototype. Related: **MFA (ADR 012)** is deferred with a settled design (TOTP gating token issuance, U2F/FIDO2 above it) and its stated trigger is the dashboard becoming the primary administrative surface. The 0.7 acceptance campaign, in which all twenty catalog applications were installed by hand through the web interface, suggests that trigger has quietly been met, so the deferral is worth re-reading.

**CSRF tokens.** Today `samesite=lax` plus the invariant that every mutation is a POST stands in for them, and a route-map test enforces the invariant. Tokens are the belt to that pair of braces.

## Runtime and isolation

**An isolation ADR, before any isolation code.** chroot versus systemd-nspawn versus bubblewrap versus micro-VMs versus rootless OCI, with trade-offs and a recommendation. Several of these appear on wish-lists (`../todo.md`); none should be built before the comparison is written, and writing it is about a day. ADR 055 §9 places namespace isolation as a heavier decision *building on* UID separation, so the 0.8 work comes first regardless.

**Alternative runtimes and backends.** Podman rootless or youki to run the OCI images Hop3 already produces without a `dockerd` dependency; systemd-nspawn or bubblewrap for per-application dependency trees; micro-VMs for the multi-tenant case; a Docker backend that does not require compose. Each waits on the ADR above.

**Runtime stack replacement (ADR 023).** Granian plus Caddy plus a purpose-built process manager, replacing uWSGI plus nginx plus supervisor. uWSGI is unmaintained, Hop3 uses a handful of its features, and there is no hot reconfiguration. Partial groundwork exists: the Caddy plugin is in tree and Granian already serves `hop3-server` itself. It stays large and its open questions are unanswered: Granian's production maturity, a zero-downtime migration for existing deployments, and what replaces uWSGI's rack and JVM plugins for Ruby, Node and Go applications. It also interacts with whatever ADR 055 settles, since that rests on the Emperor. **The benchmark and the migration design would make this real.**

## Operations

**Deployment strategies (ADR 032).** Blue-green and canary appear in an accepted ADR and nowhere in the source, alongside `revert`/`upgrade`/`downgrade` naming over `current`/`previous`. 0.7 shipped upgrade-with-automatic-rollback, which covers the operationally urgent part; the rest is optional for a single-server platform, which is why it sits here.

**Backups, phases 2 and 3 (ADR 016).** Scheduled backups and retention policies first; then remote storage (S3, B2), encryption, and incremental backups. Phase 1 shipped in 0.7 including cross-instance restore. Phase 2 is small and pairs naturally with the control-plane audit log that 0.8 adds.

**Supply chain (ADR 013).** Signature attestation for release artefacts and for the SBOM (Sigstore, in-toto, cosign), scheduled reproducible-builds verification, and upstream source mirroring against registry deletions. The Cyber Resilience Act imposes an external deadline on attestation, which makes this the item here most likely to become urgent for reasons that have nothing to do with our own priorities.

**HTTPS in the test lab.** Applications that force HTTPS can only be redirect-verified over plain HTTP today, so their content is never actually checked. This blocks a class of applications from the corpus.

## Platform reach

**Reproducibility beyond x86_64.** The bit-for-bit rebuild property is measured on one architecture. An ARM-class target means vendoring a second dependency set per template: mechanical work, and a prerequisite for anything edge-shaped.

**Toolchain breadth.** A `.NET` toolchain exists but no corpus application exercises it; Clojure and Elixir are in the same position. Each is a real packaging gap the moment an application needs it.

**The Docker corpus at the sign-in bar.** Recipes exist for most of the twenty catalog applications and none has ever been verified by signing in. The variant is deliberately not claimed anywhere as a result. Measuring it is a campaign, and the two families that *have* been measured both failed comprehensively on first contact, so this remains a known unknown.

## Smaller, self-contained

- **Web terminal (ADR 005, deferred).** In-browser log streaming and interactive shells. The original implementation was removed during the Litestar migration; the specification survives. The streaming infrastructure it waited on now exists.
- **Web analytics for deployed applications:** integrate an existing tool, or offer one as an addon.
- **`sslip.io` as a default hostname**, so a fresh deployment is reachable without configuring DNS first.
- **A shared download helper.** 27 application scripts still use a bare `curl -s` without `--fail` or retry, so an HTTP error yields a truncated file and an unclear build failure.
- **Retire the deprecated command spellings.** Several concepts are still reachable under more than one name; the documentation check found that most surviving uses are in our own guides rather than in user scripts.

## Corpus tail

- The applications under `apps/bad/` each carry a `DEFERRED.md` naming their blocker. Every platform fix should trigger a re-try of the applications it unblocks; a `--filter-blocker` selector in the test runner would make that mechanical.
- Two Ruby test applications and a source-built `wiki-js` variant remain unconverted from an earlier packaging pass.
