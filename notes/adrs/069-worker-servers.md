# ADR 069: Worker Servers and Placement

- **Status**: Draft
- **Type**: Feature
- **Created**: 2026-10-27
- **Revised**: 2026-10-28 (no leases and no automatic failover: reports, health checks and operator-driven moves; §8 added), 2026-10-29 (round-trip bound in placement; §9, losing the primary)
- **Related-ADRs**: [017](./017-agent-based-architecture.md) (the phases: this ADR details Phase 2), [029](./029-reconciliation-health-checks.md) (health checks), [041](./041-privileged-operations-agent.md) (the privileged helper, §17), [042](./042-cli-context-model.md) (contexts in the CLI), [065](./065-workload-identity.md) (enrolment), [067](./067-microvm-execution-backend.md) (the micro-VM backend), [068](./068-guest-networking.md) (the private network), [070](./070-fault-tolerance.md) (automatic failover, deferred)

## Context

This ADR details the worker servers of [ADR 017](./017-agent-based-architecture.md)'s Phase 2: how a platform runs an app's workers on servers other than the primary, with the hostname and the users unchanged.

Today the workers of an app run under uWSGI on the server that built the app, behind the proxy of that server. An organisation that adds a server gets a second platform. To run workers there, Hop3 lacks four things: a protocol between the control plane and the server, a release the server can run, rules for where workers go, and a route from the proxy to another machine.

The design follows Heroku's model on a pool of servers: the proxy on the primary is the router, in front of disposable workers and of backing services attached by URL. It targets twelve-factor apps. An app that keeps state on local disk stays on one server.

## Decision

We propose the following.

### 1. A protocol between the control plane and worker servers

Each worker server runs a small agent as the platform's user. The agent talks to the control plane over the private network ([ADR 068](./068-guest-networking.md)). Instructions from the control plane travel in the signed envelope of [ADR 065](./065-workload-identity.md) §5. Messages from a worker server are identified by the enrolled key that admitted it to the private network (ADR 065 §4). Both sides listen only on private network addresses. The operator's enrolment on the primary adds the server as a peer of the private network. The server, given the primary's endpoint and key in the same step (ADR 065 §4), brings up the tunnel before it sends anything. The protocol has six messages:

| Message | Sent by | Effect |
|---|---|---|
| `enrol` | worker server | Completes the enrolment the operator started on the primary, with the server's distribution release and capabilities (hardware virtualisation, memory, processors); refused for an unknown key or a release that differs from the primary's; the reply gives the server its guest range (ADR 068 §3) |
| `rotate` | either side | Announces the sender's new public key, signed by the old one; both keys are accepted for a stated overlap (ADR 065 §6) |
| `place` | control plane | Assigns a worker (app, process type, release) to the server, which fetches the artifact |
| `start` | control plane | Starts a placed worker with the app's configuration |
| `stop` | control plane | Stops a worker and deletes its configuration |
| `report` | worker server | Gives the state, health check and private address of each worker, and the server's load, clock offset (ADR 065 §7) and latency (round trip) to the primary; sent at a fixed interval, it also tells the control plane that the server is live |

Each message has a fixed name and a validated argument schema; adding one needs an amendment to this ADR. A refused or failed message returns the reason, logged on both sides.

The control plane keeps placements in its database and recovers them before it answers after a restart. A worker server ends a worker only on `stop`, never because it lost contact with the control plane or because a reply does not mention it. A restart of the control plane is then invisible to running workers. At start, the control plane treats each server as live until its next report is due, so the proxy's targets stay as they were.

On a worker server, a step that needs root (the worker's user and firewall rules, a micro-VM's tap) goes through the privileged helper (rootd, [ADR 041](./041-privileged-operations-agent.md) §17) of that server. The helper checks the step against the allow-list it applies to a local request. The control plane can ask a worker server for nothing a local operator could not do.

### 2. Releases built once and fetched

Each app is built once, on the primary. The build artifact plus the app's configuration makes a release, in twelve-factor terms. A content hash identifies the artifact. When a worker is placed on a worker server, the server fetches the artifact from the primary's cache over the private network. It keeps the artifact for a while after the last worker using it has ended, so a restart is quick, then deletes it (open question 5).

- A Nix-built artifact is a closure. The worker server fetches the store paths it lacks and runs the closure on any distribution.
- A native artifact depends on the host's runtimes. Worker servers run the primary's distribution release, checked at enrolment, so the artifact runs there too.
- An app that runs in a micro-VM ([ADR 067](./067-microvm-execution-backend.md)) boots from the same artifact, on a server with hardware virtualisation.

The configuration and secrets arrive with `start` and go into the worker's environment file (mode `0600`), as on one server. The worker server deletes them at `stop`. A placed worker gets an app directory on the worker server, under the app's user created there through the privileged helper (ADR 055): the artifact, the environment file and, for a guest, the writable `/var` and `/tmp` of ADR 067 §3. None of the app's data is there, since an app with local storage is pinned (§3). The directory goes when the artifact goes (open question 5). Build hooks run in the build (ADR 071). Release hooks (database migrations) run once, on the primary, before the switch of §5. They run in a one-shot instance of the new release, with the app's configuration and addon rules: a one-shot guest (ADR 067 §4) for a VM app, a process as the app's user otherwise.

### 3. Placement rules

For each app, the operator states:

- **counts per process type**: how many `web` workers and how many of each other type run, set with `hop3 ps scale` as today; a process type declared singleton runs exactly once;
- **capabilities**: what a server must offer, such as hardware virtualisation for an app that runs in a VM, whether the recipe asks for it or the platform's default puts it there (ADR 067 §1);
- **pins**: the servers the app's workers may use, or must avoid.

The control plane places each worker on an eligible server, one with the capabilities and pins satisfied. For an app with a database addon, it prefers the eligible servers with a latency to the primary under a limit set in the platform's configuration (open question 2). Among those it picks the server that runs the fewest workers of the same app, then the fewest workers overall. An app with two web workers and as many eligible servers thus runs one on each, so it keeps serving when one server is lost (§8). The primary is eligible unless the operator pins workers away from it. An app whose recipe declares local storage is pinned to the server that holds the storage; one that declares the `sasl` addon is pinned to the primary, where the sign-in socket is served (ADR 063 §5). `hop3 ps pin` warns when it places an app with a database addon beyond that limit. A worker that no server can run is refused: the deploy or the `scale` command fails with the reason (ADR 067 §1).

### 4. Routing from the primary

On the primary, the proxy sends each hostname's requests to the app's workers on any server, at their private addresses. The proxy targets only workers whose server reported within the last two intervals and whose last health check passed. Certificates and the access gate stay on the primary. The gate's identity headers travel only on the private network. A worker server admits connections to workers from the primary's private address alone ([ADR 068](./068-guest-networking.md)), so no other host can forge those headers.

Workers reach their backing services at the private address of the server that runs those services, which the addon URLs give. The firewall in front of the backing services admits the servers that run the app's workers. For a guest, the rules on the tap narrow that to the services the app declared (ADR 068 §2). For native workers on a shared worker server, the admission is per server. A native worker there can thus reach the port of another app's backing service, as on one server today. The credentials, kept apart by per-app users (ADR 055), protect the data.

### 5. Deploys across servers

A deploy builds once on the primary, runs the release hooks in a one-shot instance of the new release (§2) and halts if one fails, then for each process type:

1. places and starts the new workers;
2. waits until each passes the health check;
3. switches the proxy to the new workers;
4. stops the old ones.

A new worker that fails the health check halts the deploy before the switch. The old workers keep serving. The deploy names the failing worker, the server and the worker's log. A singleton process type is stopped before the replacement starts, so it never runs twice.

### 6. Logs

Workers on any server stream their output to the primary over the private network, tagged with the app, the process type, the worker and the server. `hop3 app logs` reads them as today. A worker server buffers lines while the primary is unreachable, up to a bound. Beyond it, the server reports how many lines it dropped, so the gap shows in the log.

### 7. The CLI and web views

The CLI talks to the primary alone: a pool of servers is one context ([ADR 042](./042-cli-context-model.md)). We propose:

- `hop3 server enrol`, `list` and `remove`. The list shows the release, capabilities, latency to the primary and workers of each server, with the age of its last report. A server whose reports cease is shown as lost with that age (§8), never omitted.
- `hop3 server drain`, which moves the workers of a server elsewhere as a deploy does (start, health check, switch, stop) and lists, with the reason, what it cannot move.
- `hop3 server remove --force`, for a server that is lost (§8).
- `hop3 ps` with a server column; `hop3 ps scale` sets the counts and `hop3 ps pin` the pins. A change of pins moves the workers it affects as a deploy does (§5), so one command moves an app to another server.

The administration web interface shows the same views.

### 8. A lost worker server

A worker server whose reports stop is shown as lost, with the age of its last report. The proxy stops sending it requests, so an app scaled across servers keeps serving from the others. Nothing restarts by itself. The control plane cannot tell a stopped server from one that is only cut off. A second copy of a scheduler or a queue consumer would do its work twice. The operator decides:

- on a server that still answers, `hop3 server drain` moves its workers as a deploy does;
- on a server that is gone, `hop3 server remove --force` records the loss, removes the server from the private network and places its workers elsewhere.

Removing the server from the private network also cuts its old workers off from the backing services and the control plane. A server that was only cut off therefore cannot do the work twice when it comes back. The cut-off does not reach an external backing service attached by URL (open question 3). For a singleton that wrote to one, `remove --force` says so. The operator then rotates that service's credentials, or ends the worker on the server, before the singleton is placed elsewhere. It is refused until the operator enrols it again. A singleton process type thus moves only on the operator's word.

Automatic restart elsewhere, with leases and fencing, is [ADR 070](./070-fault-tolerance.md), deferred to a later phase.

### 9. Losing the primary

The primary is the stated single point of failure (ADR 017 §7). While it is down, the worker servers keep their workers running (§1), but no request reaches them and no one signs in, since the entry point and the identity layer are on the primary.

In Phase 2 the operator restores the primary from backup on a fresh server, with Hop3's existing restore (ADRs 016 and 024), by a documented runbook. For a platform with worker servers, the backup also holds the enrolments, the private-network keys, the certificates and the artifact cache. The restore keeps the primary's private address, which the addon URLs on worker servers name (ADR 068 §9). It gives the new primary a new key and re-enrols each worker server, which refuses the old key from then on. The workers keep running throughout. The placements read from the backup are reconciled against the servers' next reports. DNS, or a floating address, is the operator's. Continuous backup to a worker server and a command that does all this in one step are Phase 3 (ADR 070).

## Acceptance

- A worker server enrols with a key. One with an unknown key or another distribution release is refused, with the reason on both sides.
- On a primary with one worker server, `hop3 ps scale web=2` runs one web worker on each server, and the app's content check passes through each.
- A Nix-built app and a native app both run on a worker server.
- An app that requires a VM runs only on servers with hardware virtualisation; a pinned app runs only on the servers named; an app with local storage stays where the storage is.
- A deploy across two servers switches traffic only after each new worker passes the health check. A failing new worker leaves the old ones serving and is named.
- `hop3 app logs` shows lines from workers on both servers.
- A worker server refuses connections to workers from any address but the primary's.
- Restarting the control plane leaves every worker running and the proxy's targets unchanged; a client loop against the app sees no failed request.
- A worker server cut off from the primary is shown as lost. The proxy stops routing to it, so an app with a web worker on another server keeps serving.
- After `hop3 server remove --force`, the lost server's workers run elsewhere, a singleton exactly once; the removed server, back online, reaches neither the control plane nor the platform's backing services.
- `hop3 server drain` moves the workers of a live server while the app keeps serving; a singleton stops before its replacement starts.
- The catalog's tests pass unchanged on a single server, where the primary runs all workers.
- A primary restored from backup on a fresh server, with the same private address and a new key, re-enrols its worker servers; their workers run throughout and the app serves again once DNS points at the new primary. The runbook is published.

## Consequences

### Positive

- An organisation adds capacity by enrolling a server. Apps, hostnames and users do not change.
- A release is built once and shared by all servers.
- A single server is the same code with no worker servers.

### Negative

- All requests cross the primary and the private network. Workers on other servers add a hop; the primary's bandwidth bounds the platform.
- Native apps tie worker servers to the primary's distribution release.
- Apps with local disk state gain nothing.
- A lost worker server's workers wait for the operator. With web workers on two servers, the app keeps serving meanwhile.
- A lost primary halts the platform until it is restored from backup (§9): no request is served and no one signs in meanwhile.

## Alternatives considered

- **Kubernetes or Nomad** bring mature scheduling and failover. Kubernetes costs a replicated control plane and images. Nomad runs as one server and without images, but schedules jobs and leaves sign-in, backing services and recipes to the operator. Both need skills a small operator lacks (ADR 017's non-goals).
- **Automatic restart elsewhere** ([ADR 070](./070-fault-tolerance.md)) shortens outages without the operator. It costs leases, fencing and a control plane that persists them. It is deferred to a later phase.
- **A proxy on each server, with DNS naming them all,** spreads the entry point. It costs certificates and the gate on every server, and DNS that follows failures.
- **Building on each worker server** avoids the artifact transfer. It costs a build per server, toolchains everywhere and room for drift between servers.

## Open questions

1. **The agent's process.** Part of hop3-server or a separate small daemon. Decided by whether reports must continue while hop3-server restarts on a worker server.
2. **The latency limit.** §3 keeps the workers of an app with a database addon near the primary by measured latency. The default limit, and whether a backing-service server of its own (ADR 068, open question 4) is measured the same way, are decided by a catalog run with a worker server at another provider.
3. **External backing services.** A managed database attached by URL takes a backing-service failure out of Hop3's hands; the platform should accept one as a first-class addon. The cut-off of §8 does not reach it, so such an addon needs a credential rotation the platform can run at `remove --force`. Decided addon by addon, starting with those the golden apps use.
4. **Mixed Hop3 versions during an upgrade.** The order (primary first, then worker servers, each refusing messages it does not know) and how long two versions may coexist. Decided by the first release that changes a message.
5. **The artifact cache on worker servers.** How long a server keeps an artifact no worker uses, to speed up a restart. Decided by disk use measured in the catalog runs.
