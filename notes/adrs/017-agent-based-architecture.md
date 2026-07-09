# ADR 017: Distributed, Agent-Based Architecture

- **Status**: Draft
- **Type**: Feature
- **Created**: 2024-07-17
- **Related-ADRs**: [029](./029-reconciliation-health-checks.md)
- **Related**: Hop3 paper (Section 7.4: Agent Model)

## Introduction

This ADR describes the long-term vision for Hop3's evolution from a single-server PaaS to a distributed, agent-based platform. It establishes the architectural principles and evolution path while recognizing that foundational work ([ADR 029](./029-reconciliation-health-checks.md)) must be completed first.

## Summary

Hop3 will evolve through four phases:

1. **Phase 1** ([ADR 029](./029-reconciliation-health-checks.md)): Single-server reconciliation, health checks, and restart policies
2. **Phase 2**: Extract agent responsibilities into a separate module
3. **Phase 3**: Multi-server support with central coordinator
4. **Phase 4**: Full distributed scheduling and orchestration

This phased approach allows Hop3 to gain production reliability immediately (Phase 1) while building toward a scalable distributed architecture over time.

## Context and Goals

### Context

Hop3 is currently a single-server PaaS optimized for simplicity. Comparing Hop3's architecture with production-grade orchestrators (like Kubernetes, Nomad, or the "Cube" pattern from container orchestration literature) reveals several gaps:

| Aspect | Production Orchestrators | Hop3 Current |
|--------|-------------------------|--------------|
| Architecture | Distributed Manager-Worker | Single-server monolithic |
| Reconciliation | Periodic background loop | On-demand only |
| Health Checks | Active probing + remediation | Defined but not implemented |
| Restart Policy | Always/OnFailure/Never | Not implemented |
| Metrics | Worker collects CPU/Memory | Not implemented |
| Event Log | Immutable state changes | Not implemented |

While multi-server distribution isn't needed for Hop3's primary use case (single-server simplicity), the **patterns** from distributed systems (reconciliation loops, health monitoring, self-healing) provide significant reliability benefits even on a single server.

### Goals

1. **Incremental Evolution**: Build distributed capabilities incrementally.
2. **Single-Server First**: Ensure single-server deployments gain full reliability benefits
3. **Production Patterns**: Adopt proven patterns from production orchestrators
4. **Minimal Complexity**: Add multi-server support only when justified by concrete requirements
5. **Promise-Based Design**: Use the theory of promises for coordination semantics

### Non-Goals

- Competing with Kubernetes for large-scale container orchestration
- Supporting arbitrary distributed consensus algorithms
- Real-time sub-second state synchronization

## Decision

Hop3 will adopt an agent-based architecture where each server runs an autonomous agent that:
1. Manages local application lifecycle
2. Maintains promises about application state
3. Reports status to a coordinator (in multi-server mode)
4. Self-heals based on configured policies

The architecture will be implemented in phases, with each phase delivering standalone value.

## Detailed Design

### Phase 1: Single-Server Foundations ([ADR 029](./029-reconciliation-health-checks.md))

Phase 1 implements the core patterns on a single server (the detailed design lives in [ADR 029](./029-reconciliation-health-checks.md)):

```
┌─────────────────────────────────────────────────────────┐
│                    Hop3 Server                          │
│                                                         │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────┐   │
│  │   Watchdog   │───▶│   Database   │◀───│   CLI    │   │
│  │   Service    │    │   (SQLite)   │    │          │   │
│  └──────┬───────┘    └──────────────┘    └──────────┘   │
│         │                                               │
│         ▼                                               │
│  ┌──────────────┐    ┌──────────────┐                   │
│  │   Health     │    │    uWSGI     │                   │
│  │   Checker    │───▶│   Emperor    │                   │
│  └──────────────┘    └──────────────┘                   │
│                             │                           │
│                             ▼                           │
│                      ┌──────────────┐                   │
│                      │ App Processes│                   │
│                      └──────────────┘                   │
└─────────────────────────────────────────────────────────┘
```

Key deliverables:
- `WatchdogService`: Background reconciliation loop (30-60 second cycle)
- `HealthChecker`: Command and HTTP-based health probing
- `RestartPolicy`: NEVER, ON_FAILURE, ALWAYS with exponential backoff
- `AppEvent`: Immutable audit log of state changes

### Phase 2: Agent Module Extraction

Phase 2 extracts agent responsibilities into a distinct module, preparing for distribution:

```python
class LocalAgent:
    """Agent running on a single Hop3 server."""

    def __init__(self, node_id: str, coordinator: Coordinator | None = None):
        self.node_id = node_id
        self.watchdog = WatchdogService()
        self.health_checker = HealthChecker()
        self.coordinator = coordinator  # None for single-server

    async def run(self) -> None:
        """Main agent loop."""
        while True:
            # 1. Reconcile local state
            await self.watchdog.reconcile()

            # 2. Run health checks
            await self.health_checker.check_all()

            # 3. Process restart policies
            await self.watchdog.process_restarts()

            # 4. Report to coordinator (if multi-server)
            if self.coordinator:
                await self.report_status()

            await asyncio.sleep(30)

    async def report_status(self) -> AgentStatus:
        """Report agent status to coordinator."""
        return AgentStatus(
            node_id=self.node_id,
            timestamp=datetime.now(UTC),
            apps=self._get_app_statuses(),
            resources=self._get_resource_usage(),
        )

    def receive_task(self, task: Task) -> Promise:
        """Receive a task from coordinator and return a promise."""
        return Promise(
            promiser=self.node_id,
            promisee="coordinator",
            body=f"deploy:{task.app_name}",
            status="pending",
        )
```

Key deliverables:
- `LocalAgent`: Encapsulates all agent responsibilities
- `AgentStatus`: Standardized status reporting format
- `Task` / `Promise`: Data structures for task assignment

### Phase 3: Multi-Server Coordinator

Phase 3 adds a central coordinator for multi-server deployments:

```
┌───────────────────────────────────────────────────────┐
│                       Coordinator                     │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐  │
│  │  Scheduler  │   │   Task      │   │   Promise   │  │
│  │  (3-phase)  │   │   Queue     │   │   Registry  │  │
│  └─────────────┘   └─────────────┘   └─────────────┘  │
└────────────────────────────┬──────────────────────────┘
                             │ HTTP/gRPC
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
        ┌──────────┐   ┌──────────┐   ┌──────────┐
        │  Agent   │   │  Agent   │   │  Agent   │
        │  Node 1  │   │  Node 2  │   │  Node 3  │
        └──────────┘   └──────────┘   └──────────┘
```

**Coordinator Responsibilities:**

```python
class Coordinator:
    """Central coordinator for multi-server Hop3."""

    def __init__(self):
        self.agents: dict[str, AgentConnection] = {}
        self.scheduler = Scheduler()
        self.task_queue = TaskQueue()
        self.promise_registry = PromiseRegistry()

    async def deploy_app(self, app: App) -> DeploymentResult:
        """Deploy application to best available node."""
        # 1. Filter: Find capable nodes
        candidates = self.scheduler.filter(
            self.agents.values(),
            requirements=app.resource_requirements,
        )

        # 2. Score: Rank by resource availability
        scored = self.scheduler.score(candidates)

        # 3. Pick: Select best node
        target = self.scheduler.pick(scored)

        # 4. Create task and send to agent
        task = Task(app_name=app.name, action="deploy")
        promise = await target.assign_task(task)

        # 5. Register promise and track
        self.promise_registry.register(promise)
        return DeploymentResult(node=target.node_id, promise_id=promise.id)

    async def reconciliation_loop(self) -> None:
        """Periodic reconciliation with all agents."""
        while True:
            for agent in self.agents.values():
                status = await agent.get_status()
                await self._reconcile_agent(agent, status)
            await asyncio.sleep(30)
```

**Three-Phase Scheduler:**

```python
class Scheduler:
    """Three-phase scheduler for task placement."""

    def filter(
        self,
        agents: Iterable[AgentConnection],
        requirements: ResourceRequirements,
    ) -> list[AgentConnection]:
        """Phase 1: Filter out incapable nodes."""
        return [
            agent for agent in agents
            if agent.has_capacity(requirements)
            and agent.is_healthy()
            and not agent.is_draining()
        ]

    def score(
        self,
        candidates: list[AgentConnection],
    ) -> list[tuple[AgentConnection, float]]:
        """Phase 2: Score remaining candidates."""
        scored = []
        for agent in candidates:
            score = (
                0.4 * agent.available_memory_ratio()
                + 0.3 * agent.available_cpu_ratio()
                + 0.2 * agent.app_spread_score()  # Prefer nodes with fewer apps
                + 0.1 * agent.locality_score()    # Prefer co-located dependencies
            )
            scored.append((agent, score))
        return sorted(scored, key=lambda x: x[1], reverse=True)

    def pick(
        self,
        scored: list[tuple[AgentConnection, float]],
    ) -> AgentConnection:
        """Phase 3: Pick the best candidate."""
        if not scored:
            raise NoCapacityError("No nodes available for scheduling")
        return scored[0][0]
```

Key deliverables:
- `Coordinator`: Central management service
- `Scheduler`: Three-phase scheduling algorithm
- `AgentConnection`: Agent communication protocol
- `PromiseRegistry`: Track and verify promises

### Phase 4: Advanced Orchestration and Federation

Phase 4 adds advanced features and explores two complementary coordination models:

**Engineering track (coordinator-based):**

1. **Placement Constraints**: Affinity/anti-affinity rules
2. **Rolling Updates**: Zero-downtime deployments across nodes
3. **Resource Quotas**: Per-tenant resource limits

**Research track (fully decentralized):**

For edge and fog computing scenarios where a central coordinator is unavailable or undesirable (network partitions, multi-operator federation), an alternative coordination model based on CRDTs and gossip-based dissemination can replace the central coordinator:

- Each node maintains a local CRDT replica of the deployment state
- Nodes synchronise via gossip protocols rather than reporting to a coordinator
- Scheduling emerges from local evaluation of capability promises against workload requirements
- Conflict resolution uses CRDT merge semantics (see the Hop3 paper, Section 7.4)

This decentralized model is the natural end-state for edge deployments where nodes must operate autonomously under partition. The coordinator-based Phase 3 serves as a pragmatic intermediate step that validates the agent/promise model before removing the central authority.

The Hop3 paper develops the formal argument for this trajectory, grounding it in Promise Theory \[PT1\] and showing how Nix content-addressed closures enable bandwidth-efficient store-carry-forward updates between disconnected nodes.

### Theory of Promises Integration

The theory of promises (Mark Burgess) provides the semantic foundation:

**Promise Types:**

```python
class Promise:
    """A declaration by an agent about its behavior."""

    promiser: str        # Agent making the promise
    promisee: str        # Who can depend on it ("any" for broadcast)
    body: str            # What is promised (e.g., "running:myapp")
    status: PromiseStatus  # pending, kept, broken
    timestamp: datetime

class PromiseStatus(enum.Enum):
    PENDING = "pending"    # Promise made, not yet verified
    KEPT = "kept"          # Promise verified as fulfilled
    BROKEN = "broken"      # Promise verified as not fulfilled
```

**Promise Verification:**

```python
async def verify_promises(self) -> list[BrokenPromise]:
    """Verify all registered promises against actual state."""
    broken = []
    for promise in self.promise_registry.active():
        agent = self.agents.get(promise.promiser)
        if not agent:
            broken.append(BrokenPromise(promise, reason="agent_unavailable"))
            continue

        # Parse promise body and verify
        if promise.body.startswith("running:"):
            app_name = promise.body.split(":")[1]
            status = await agent.get_app_status(app_name)
            if status.state != AppState.RUNNING:
                broken.append(BrokenPromise(promise, reason="app_not_running"))

    return broken
```

**Promise-Based Coordination:**

Instead of imperative commands ("deploy this app now"), the coordinator expresses desired state and agents make promises:

1. Coordinator: "I need app X running on some node"
2. Agent A: "I promise to run app X" (promise pending)
3. Agent A deploys app X
4. Agent A: Updates promise status to "kept"
5. Coordinator: Verifies promise periodically

This provides:
- **Decentralization**: Agents decide how to fulfill promises
- **Fault Tolerance**: Broken promises trigger re-scheduling
- **Auditability**: Promise history provides clear audit trail

## Consequences

### Benefits

1. **Incremental Value**: Each phase delivers standalone improvements
2. **Production Reliability**: Single-server deployments become self-healing
3. **Scalability Path**: Clear evolution to multi-server when needed
4. **Semantic Clarity**: Promise theory provides rigorous coordination semantics
5. **Debugging**: Promise history and event logs enable root cause analysis

### Drawbacks

1. **Complexity**: Multi-server coordination adds significant complexity
2. **Overhead**: Promise verification and reconciliation consume resources
3. **Learning Curve**: Promise theory concepts require documentation and training

### Trade-offs

| Aspect | Decision | Alternative | Why Rejected |
|--------|----------|-------------|--------------|
| Evolution | Phased | Big-bang | Risk too high, value delayed |
| Coordination | Promise-based | Imperative | Less fault tolerant |
| Scheduling | 3-phase | Simple round-robin | Insufficient for heterogeneous nodes |
| Storage | Per-agent SQLite | Distributed consensus | Unnecessary complexity for Hop3 scale |

## Prior Art

- **Kubernetes**: Manager-worker architecture with reconciliation loops
- **Nomad**: Three-phase scheduler (feasibility, ranking, selection)
- **CFEngine**: Theory of promises for configuration management
- **Cube Orchestrator**: Educational reference for container orchestration patterns
- **systemd**: Local process supervision with restart policies

## Related

- [ADR 020: Pluggable Architecture](./020-pluggable-architecture.md) - Plugin system used by agents
- [ADR 022: Build and Deployment Plugin System](./022-build-deploy-plugin-system.md) - Deployment strategies
- [ADR 029: Reconciliation and Health Checks](./029-reconciliation-health-checks.md) - Phase 1 implementation details

## References

- Burgess, M. "An Approach to Computer System Configuration Based on Promise Theory," *Science of Computer Programming*, vol. 71, no. 3, pp. 243–265, 2008.
- Burgess, M. and Bergstra, J.A. *Promise Theory: Principles and Applications*. Xtaxis Press, 2014.
- Burgess, M. "Testable System Administration," *Communications of the ACM*, vol. 54, no. 3, pp. 44–49, 2011.
- Burgess, M. "In Search of Certainty" (2013)
- Kubernetes Documentation: [Controllers](https://kubernetes.io/docs/concepts/architecture/controller/)
- Nomad Documentation: [Scheduling](https://developer.hashicorp.com/nomad/docs/concepts/scheduling)
- "Build an Orchestrator in Go (From Scratch)" by Tim Boring
- Hop3 paper, Section 7.4: "From Single Node to Distributed Edge: The Hop3 Agent Model"
