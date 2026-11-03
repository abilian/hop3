# ADR 017: Agent-Based Distributed Architecture

- **Status**: Draft
- **Type**: Feature
- **Created**: 2024-07-17
- **Revised**: 2026-10-27, 2026-10-28, 2026-10-29 (see "Revision" below)
- **Related-ADRs**: [010](./010-security-and-resilience.md) (failover scope, changed in Phase 3 by §7), [016](./016-backups.md) and [024](./024-backup-restore-system.md) (backups), [029](./029-reconciliation-health-checks.md) (Phase 1), [041](./041-privileged-operations-agent.md) (the privileged helper, §17 on agents), [063](./063-identity-layer.md) (the identity layer); detailed designs: [065](./065-workload-identity.md) (enrolment), [068](./068-guest-networking.md) (the private network), [069](./069-worker-servers.md) (worker servers and placement), [070](./070-fault-tolerance.md) (fault tolerance, deferred to Phase 3)
- **Related**: Hop3 paper (Section 7.4: Agent Model)

## Summary

This ADR sets the principles and phases of Hop3's growth from one server to several, and frames the ADRs that design each phase. A server is capacity: the number of servers should not matter to an app, to the people who use it or to the operator.

A platform should be one **primary**, which holds everything that has a single location, plus any number of **worker servers** that run the apps' workers and nothing else, joined by a private network. A single server is a primary with no worker servers. Hop3 gets there in four phases, each useful alone:

1. **Phase 1, self-healing on one server**: reconciliation, health checks and restart policies ([ADR 029](./029-reconciliation-health-checks.md)).
2. **Phase 2, a primary with worker servers**: enrolment ([ADR 065](./065-workload-identity.md)), the private network ([ADR 068](./068-guest-networking.md)), worker servers and placement ([ADR 069](./069-worker-servers.md)). A lost worker server stops receiving requests. The operator moves its workers.
3. **Phase 3, later**: failover of workers with leases and fencing ([ADR 070](./070-fault-tolerance.md)), then a standby primary that takes over by itself, and placement that filters, scores and picks servers, after Nomad.
4. **Phase 4, federation and the edge**: research on several operators and sites that are often cut off, with promises replicated as CRDTs by gossip.

Phase 2 is the next step, designed by ADRs 065, 068 and 069. Phases 3 and 4 build on it.

## Context and Goals

### Context

Hop3 runs all apps on one server, on Heroku's model: a router in front, disposable workers behind it, backing services attached by URL. Adding capacity today means a second platform, managed apart. Production orchestrators spread workloads through a replicated control plane that a small organisation can neither run nor repair.

The project targets twelve-factor apps: stateless processes, configuration in the environment, state in backing services, logs as streams. An app that keeps state on local disk stays on one server; distributing it would need network or block storage, which this ADR leaves aside.

### Goals

1. **Incremental evolution**: each phase is useful alone. One server runs the code paths of several, which the catalog's tests then exercise.
2. **A small model**: Heroku's router, workers and backing services over a handful of servers, placed by a few rules.
3. **Stated failure semantics**: each failure has a stated behaviour and cost, the primary's included; in Phase 2, the operator decides what moves.
4. **Privilege stays local**: the control plane can make a worker server do nothing a local operator could not.

### Non-Goals

- Competing with Kubernetes or Nomad.
- Consensus, or a primary that fails over by itself.
- Distributing apps with local disk state, live migration, hosting DNS.

## Decision

We propose the following principles.

### 1. One primary

The primary holds what has a single location:

- the control plane: apps, configuration, secrets, accounts, placements, and the database Hop3 keeps them in;
- the entry point: the proxy, the certificates and the access gate;
- the identity layer and the sign-in issuer (ADR 063);
- builds and the cache of build artifacts;
- by default, the backing services (PostgreSQL, MySQL, Redis), unless the operator places them on a server of their own or uses external ones.

### 2. Worker servers run workers

A worker server holds no state and no users, and has no public entry point. It joins once with a key the operator enrols, which also identifies it on the private network. Enrolment refuses a server whose distribution release differs from the primary's, so a native release built on the primary runs on any worker server.

The operator says how many workers of each process type an app runs. The control plane spreads them over the servers that offer what the app requires (hardware virtualisation for an app in a VM) and honours the operator's pins.

### 3. Every request enters at the primary

DNS points each app hostname at the primary. The proxy there forwards requests by hostname to the app's workers on any server, over a private WireGuard network. Certificates stay on the primary. Workers reach their backing services at addresses valid across that network.

Identity follows the request: the gate on the primary passes it on; OpenID Connect apps check tokens against the issuer's published keys. A worker server never checks a password, so it needs no copy of the accounts.

### 4. Reports, and moves the operator decides

A worker server reports the state and health of its workers at a fixed interval. The proxy routes only to workers whose server reported recently and whose health check passes. A server whose reports stop is shown as lost. Nothing restarts by itself. When the operator drains a live server, or removes a lost one (which also cuts it off from the private network), its workers are placed elsewhere ([ADR 069](./069-worker-servers.md) §8). A singleton worker (a scheduler, a queue consumer) therefore never runs twice. Phase 3 replaces the operator's decision by leases and fencing ([ADR 070](./070-fault-tolerance.md)).

### 5. Privilege stays on each server

Agents run as the platform's user. A step that needs root goes through the privileged helper (rootd, [ADR 041](./041-privileged-operations-agent.md) §17) of the server concerned, with the allow-list it applies to a local request. An enrolled key authenticates a worker server; every operation it signs still passes the allow-list of the privileged helper on that server.

### 6. Promises

Promise theory (Mark Burgess) gives the semantics. The control plane states needs ("app X should run two web workers at release R"). A worker server accepts part of a need by promising about its own state ("one web worker of X runs here at release R"), pending until it reports the promise kept or broken. The history of promises is the platform's audit trail.

In Phase 3, a lease is a promise with an expiry, renewed while the worker server can. Once the lease has expired, the control plane treats the promise as broken without asking the server, which has stopped the worker by then ([ADR 070](./070-fault-tolerance.md)). Because each server owns the promises it makes, Phase 4's replicated state stays possible.

### 7. Failover of workers comes in Phase 3

[ADR 010](./010-security-and-resilience.md) placed multi-server failover out of scope. Phase 2 keeps it out: a worker on a lost server moves when the operator says so (§4). Phase 3 brings failover of workers into scope: a worker on a lost server restarts on another by itself ([ADR 070](./070-fault-tolerance.md)). Failover of the primary and of backing services stays out in both. The primary is a stated single point of failure. In Phase 2 the operator restores it from backup on a fresh server by a documented runbook ([ADR 069](./069-worker-servers.md) §9). Phase 3 reduces the outage by continuous backup to a worker server, a tested restore command and an optional floating-address plugin.

## Consequences

Capacity grows by enrolling worker servers, with apps, users and DNS records unchanged. Losing a worker server costs no data; an app with workers on another server keeps serving, and the lost server's workers wait for the operator in Phase 2. There is no consensus protocol to run or repair.

The primary is a single point of failure: losing it costs the restore time and the data written since the last backup (ADRs 016 and 024). All requests cross the primary, which bounds the platform's bandwidth. A worker at another provider than its database pays the round trip on each query. Apps with local disk state gain nothing.

## Revision (2026-10-27)

The 2024 version planned an agent module (Phase 2), a central coordinator with a three-phase scheduler (Phase 3), then federation (Phase 4). This revision keeps agents that keep promises, phases useful alone and no consensus. It changes five things:

1. **Phase 2 is a primary with worker servers.** The coordinator becomes the control plane on the primary.
2. **Stated failure semantics.** Each failure has a stated behaviour and cost; leases and fencing, which give promises an expiry, belong to Phase 3 (see below).
3. **Placement is a few rules.** The scheduler moves to Phase 3.
4. **Identity.** Worker servers are enrolled by key; accounts and sign-in stay on the primary.
5. **Scope.** Twelve-factor apps on Heroku's model, and failover of workers (§7).

The revision of 2026-10-28 moves leases, fencing and failover of workers (ADR 070) from Phase 2 to Phase 3, to keep Phase 2 simple: worker servers report and the operator decides what moves.

The revision of 2026-10-29 names the sign-in issuer among what the primary holds (§1) and states how Phase 2 recovers a lost primary: a documented restore from backup on a fresh server (§7, ADR 069 §9).

## Open Questions

1. **Mixed distribution releases.** Worker servers on another distribution release would need native apps rebuilt per release, or only Nix-built and micro-VM apps. Decided when an operator asks for it.
2. **When Phase 3 starts.** A standby primary needs a quorum of three servers and replicated state, as does promoting a database replica. Decided by the restore times the catalog's failure tests measure and by operators' reports.

ADR 069 holds the questions on latency across providers and external backing services; ADR 070, those on lease durations.

## Prior Art

- **Heroku**: router, dynos, backing services.
- **Kubernetes**: reconciliation loops, node leases.
- **Nomad**: a three-step scheduler; a cut-off client stops its allocations after a set time.
- **CFEngine**: promise theory.
- **Leases** (Gray and Cheriton): a grant with an expiry.

## References

- Burgess, M. "An Approach to Computer System Configuration Based on Promise Theory," *Science of Computer Programming*, vol. 71, no. 3, pp. 243–265, 2008.
- Gray, C. and Cheriton, D. "Leases: An Efficient Fault-Tolerant Mechanism for Distributed File Cache Consistency," *Proceedings of the 12th ACM Symposium on Operating Systems Principles*, pp. 202–210, 1989.
- Wiggins, A. *The Twelve-Factor App*, 2011: [12factor.net](https://12factor.net).
