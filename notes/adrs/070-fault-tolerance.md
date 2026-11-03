# ADR 070: Fault Tolerance

- **Status**: Deferred (2026-10-28)
- **Type**: Architecture
- **Created**: 2026-10-27
- **Related-ADRs**: [010](./010-security-and-resilience.md) (failover scope, changed for workers), [016](./016-backups.md) and [024](./024-backup-restore-system.md) (backups), [017](./017-agent-based-architecture.md) (the phases: this ADR details Phase 3), [029](./029-reconciliation-health-checks.md) (health checks and restart policies), [041](./041-privileged-operations-agent.md) (the privileged helper), [065](./065-workload-identity.md) (enrolment and clocks), [068](./068-guest-networking.md) (the private network), [069](./069-worker-servers.md) (worker servers and placement)

> **Deferred.** Phase 2 of [ADR 017](./017-agent-based-architecture.md) keeps the pool of servers simple: worker servers report, the proxy stops routing to a lost one, and the operator moves its workers ([ADR 069](./069-worker-servers.md) §8). Leases, fencing and automatic restart elsewhere, and the continuous backup of the primary, wait for Phase 3. Throwaway prototypes of October 2026 (seven failures, a restore of the primary) support this design when it comes back.

## Context

This ADR details the failure handling of [ADR 017](./017-agent-based-architecture.md)'s Phase 3. With worker servers ([ADR 069](./069-worker-servers.md)), a platform fails in more ways than one server does. A worker server can go down, or be cut off from the primary while it keeps running. A worker can crash. The primary, or a server holding backing services, can go down.

The cut-off worker server is the hard case. The control plane cannot tell it from a stopped one. If the control plane starts replacements while the cut-off server keeps the workers running, a scheduler or a queue consumer runs twice. Health checks alone cannot prevent this.

[ADR 010](./010-security-and-resilience.md) placed multi-server failover out of scope. This ADR brings failover of workers into scope and keeps failover of the primary and of backing services out. Each failure gets a stated behaviour and a stated cost.

## Decision

We propose the following.

### 1. Leases

The control plane grants a lease on each worker when the worker starts (ADR 069 §1). Each lease records the worker, the server, the release and a duration. The worker server renews all the leases it holds in one `renew` message, well before they end. We propose leases of 20 seconds renewed every 5 seconds, values the failure tests settle (open question 1).

Each side times a lease on a local monotonic clock, so clock offsets between servers do not matter. The worker server counts from the moment it sent the renewal and the control plane from the moment it received it, so the worker server's lease always ends first. The worker server uses a clock that keeps counting while the server is suspended (CLOCK_BOOTTIME on Linux).

### 2. Fencing

A worker server that cannot renew halts each worker a margin before the lease ends: the time a worker needs to stop, plus a bound on clock drift. It acts alone, with no message from the control plane. A worker still running when the lease ends is killed through the worker's control group, by the privileged helper (rootd, [ADR 041](./041-privileged-operations-agent.md) §18). The control plane starts a replacement only once the lease has ended by the control plane's clock. Hence:

- the proxy never sends requests both to a cut-off web worker and to the replacement;
- a singleton worker (a process type declared to run once, such as a scheduler or a queue consumer) never runs on two servers at once.

Fencing must also hold when the agent itself dies, since no process would then stop the workers. They should run inside the agent's service, so that the init system ends them when the agent exits (open question 2).

Fencing by the agent alone is a race when a frozen server resumes: the agent's check and the worker wake together. A singleton worker that updates a backing service therefore presents a fencing token, the number of its lease, which the control plane increases at each placement. The backing service refuses a token older than the last one it saw, so a resumed worker that acts before its agent fences it changes nothing.

A fenced server that reconnects reports what it stopped. It receives new work and restarts none of the old.

### 3. Restarting workers elsewhere

When a lease ends, the control plane places the worker again by the rules of ADR 069 §3 and starts it on an eligible server, which fetches the release if it lacks it. If no server can run the worker, `hop3 ps` and `hop3 app status` show the app as degraded, with the reason. A restart takes at most the lease length plus one renewal interval, since a worker server learns of new work at its next renewal; pushing placements to the agent would remove the second term (open question 5).

An app pinned to the lost server, or whose local storage is there, waits for that server to return or for a restore from the app's backup ([ADR 024](./024-backup-restore-system.md)). The status names the server it waits for.

### 4. Health checks

Each worker server runs the app's health check against the workers it hosts ([ADR 029](./029-reconciliation-health-checks.md)) and sends the results with each `report`. A worker that crashes or fails the check restarts in place, under the restart policy of ADR 029. After repeated failures on one server, the control plane places the worker on another. A worker that fails on every server is reported as failing, with the last lines of its log.

### 5. Proxy targets

The proxy on the primary sends requests to a worker only while the lease is current and the last health check passed. The control plane removes a worker from the proxy's targets at the first late renewal, before the worker server fences it. When no worker of an app can take requests, the proxy answers with a 503 page that names the app.

### 6. Failures and their cost

| Failure | Behaviour | Recovery time (RTO) | Data lost (RPO) |
|---|---|---|---|
| A worker server stops | The leases end; the control plane starts the same workers on other servers; the proxy stopped routing there at the first late renewal | Seconds to a minute: the lease, then a start | None |
| A worker server is cut off | The server fences the workers before the leases end; replacements start elsewhere; on return, the server receives new work | The same | None |
| A worker crashes or fails its health check | Restarted where it runs, or elsewhere if it keeps failing | Seconds | None |
| The primary stops | All apps are unreachable. Worker servers fence their workers when the leases end. Apps return, with restarted workers, when the primary does or once it is restored on another server (§8) | The time to notice the loss, then about a second of restore and two renewal intervals until the workers run again | Data written since the last backup |
| A server holding backing services stops | The apps that use them fail until the server returns or the services are restored from backup | The restore time | Data written since the last backup |

The failures of worker servers cost a short delay and no data. The primary is a single point of failure, as in most small deployments. Sections 7 to 9 reduce the cost of losing it, without consensus.

### 7. Continuous backup to a worker server

The primary backs up continuously, over the private network, to a worker server the operator chooses:

- the control plane's database, by streaming the write-ahead log (as Litestream does for SQLite);
- the certificates, the platform's keys and the apps' configuration, at each change;
- the backing services, each by the log it already keeps: PostgreSQL's write-ahead log, MySQL's binary log, Redis's append-only file;
- the backups of apps with local storage ([ADR 024](./024-backup-restore-system.md)).

The backup is encrypted to a key the operator keeps outside the platform. The worker server that stores it cannot read it. The RPO is the lag of each stream, which the platform measures and shows in `hop3 system status`. The streams are asynchronous: commits on the primary do not wait for them. The loss is what the worker server had not received at the moment of failure, usually below a second. Synchronous replication to the worker server would make it zero, at the cost of latency on every commit; it is an operator setting. A backing service on a separate server is backed up the same way, to another server.

### 8. A tested restore command

One command restores the primary on another server, a worker server or a new one. We propose `hop3-install server --restore`. It installs hop3-server, asks for the operator's backup key, restores the control plane, the keys, the certificates and the backing services, then runs each app's content check. The restored primary receives a new private-network key. The restore revokes the old primary's key on every worker server and moves the platform's service address, on which the control plane and the backing services listen, to the restored primary; apps and agents keep their configuration. Then the floating-address plugin moves the public address (§9); without one, the command names the DNS records to change and waits until they resolve to the new primary.

A restore raises the platform's epoch. Worker servers keep the highest epoch they have seen and refuse instructions from a lower one. A primary that starts checks the epoch with the worker servers before it starts anything: control plane, entry point, backing services and its own agent. It stays stopped, with a diagnosis, when a worker server has seen a higher epoch, and also when none answers; the operator then confirms with an explicit command. A platform with no worker server has nothing to check and starts. Where a floating-address plugin exists for the provider, the restore also powers the old primary off.

### 9. An optional floating-address plugin

Some providers offer an address that moves between servers in one location: Hetzner's floating IPs, OVH's additional IPs, Scaleway's flexible IPs. DNS then points at that address. A plugin per provider moves the address to the restored primary through the provider's API and configures it there, which saves the DNS delay. The plugin is optional; the DNS change works with any provider.

### 10. Moving the platform to another provider

Moving to another provider is a planned restore plus a drain:

1. enrol worker servers at the new provider;
2. drain the old worker servers (ADR 069 §7), whose workers move as in a deploy;
3. stop writes on the primary and take a final backup;
4. restore the primary at the new provider (§8);
5. change DNS;
6. remove the old servers.

Hostnames, certificates and the sign-in issuer stay the same, so users keep their accounts. The command states the downtime, which runs from stopping writes to the DNS change.

### 11. Failure tests in the catalog runs

hop3-test should run these scenarios, on Docker and on remote servers, with content-checked validations:

- stop a worker server: the workers run elsewhere within the stated time and the app's content check passes;
- cut a worker server off the private network: a singleton test worker never runs on two servers at once, as the records it leaves show; once back, the server runs only new work;
- kill a worker, and make another fail the health check repeatedly;
- restore the primary on a worker server: the golden apps pass their content checks and a sign-in, with no more data lost than the measured RPO;
- start the old primary after a restore: it stays stopped with a diagnosis.

The runs publish the measured RTO and RPO.

## Out of scope

A standby primary that takes over by itself needs a quorum of three servers to decide which side of a partition may accept changes. So does promoting a database replica. Without a quorum, two primaries could accept changes at once. Both are later work ([ADR 017](./017-agent-based-architecture.md), Phase 3).

## Acceptance

- The failure tests of §11 pass in a clean catalog run, on Docker and on two remote servers.
- After a worker server stops, the workers it ran serve again elsewhere in under a minute.
- A cut-off worker server runs no singleton worker after the leases end.
- `hop3-install server --restore` restores the primary on a worker server, and the golden apps pass their content checks and a sign-in there.
- The floating-address plugin for one provider moves the address during a restore.
- The documentation states the measured RTO and RPO of each failure.

## Consequences

### Positive

- Losing a worker server costs a short delay and no data.
- A singleton worker never runs twice when a server is cut off.
- Losing the primary has a tested recovery with stated costs.
- Moving to another provider reuses the restore.

### Negative

- While the primary is down, all apps are unreachable. Worker servers fence their workers in the meantime, so the return of the primary also restarts all workers.
- A server paused by the hypervisor past the end of the leases may run the workers for a moment after it resumes, until the agent sees the expiry. The fencing token of §2 keeps such a worker from writing.
- The backups need a worker server with enough disk. The operator must keep the backup key safe.

## Alternatives considered

- **Consensus among three servers** (Raft, as in etcd or Consul). Automatic failover of the primary. Costs three servers, replicated state and a protocol a small organisation must operate and repair.
- **Health checks without leases.** Simpler. A cut-off server keeps singleton workers running while replacements start.
- **Fencing by powering servers off** through the provider's API. Needs no cooperation from the cut-off server. Needs an API for each provider; kept for the old primary where the plugin exists.

## Open questions

1. **Lease duration.** A short lease restarts workers sooner; a long one fences less often under load. Decided by the failure tests, which measure both.
2. **Workers that stop with the agent.** How workers under uWSGI and in micro-VMs run inside the agent's service. Decided with the agent's process (ADR 069, open question 1).
3. **Backups on a single server.** The storage targets (another host by SSH, object storage) for a platform with no worker server. Decided by what the first operators use.
4. **Providers.** Which floating-address plugins follow the first. Decided by the providers of the first operators.
5. **Pushed placements.** Whether the control plane tells an agent of new work at once, through a request the agent keeps open, instead of at the next renewal. Decided by how much of the restart delay the renewal interval accounts for in the failure tests.
