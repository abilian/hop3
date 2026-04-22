# ADR 029: Application Reconciliation and Health Check System

**Status**: Draft (no implementation; design proposal only)
**Type**: Feature
**Created**: 2025-11-25
**Updated**: 2026-04-22
**Related-ADRs**: 017, 036

## Revisions

- v0.3: CLI examples migrated from colon syntax (`hop3 app:deploy`, `hop3 app:logs`, `hop3 app:start`, proposed `hop3 app:health` / `hop3 app:events`) to space form per ADR 036 (2026-04-22).
- v0.2: Explicit status note. None of the four components (background reconciliation loop, active health checks, restart policies, immutable event log) has been implemented. The `[healthcheck]` section in `hop3.toml` *is* parsed and used by the deployer's one-shot startup probe, but the reconciliation loop, the active periodic probing, and the audit log remain on paper. PLAN-2026-Q2 schedules this work for the 0.6 release as the concrete Phase 1 of ADR 017 (2026-04-14).
- v0.1: Initial draft (2025-11-25)

## Current Status (2026-04-14)

What exists today:
- The `[healthcheck]` section in `hop3.toml` is parsed.
- A one-shot health probe runs at the end of `hop3 deploy` to confirm the freshly deployed app responds. Failure surfaces as a `Diagnosis` and the deployment is reported as failed.
- `hop3 logs --app <app>` lets an operator read worker logs after the fact.
- The dashboard's HTMX polling triggers `App.sync_state()` on each view — the closest thing to reconciliation today (and exactly the workaround this ADR exists to retire).

What this ADR proposes and what is **not** implemented:
- A background `WatchdogService` running on the server with a configurable cycle (planned: 30–60 s) reconciling DB state with actual process state.
- Active periodic health-check probing using the `[healthcheck]` config.
- A `RestartPolicy` model (NEVER / ON_FAILURE / ALWAYS) with exponential backoff.
- An immutable `AppEvent` audit log of all state changes.
- New CLI commands `hop3 app health` and `hop3 app events`.

The design below is what will be built when the work is scheduled. Until that happens, the ADR is paper, not code.

## Introduction

This ADR describes the implementation of a background reconciliation loop and active health check system for Hop3. This is a foundational step toward making Hop3 a self-healing platform that can automatically detect and recover from application failures without manual intervention.

## Summary

We will implement:
1. **Background Reconciliation Loop**: A periodic task that synchronizes database state with actual process state
2. **Active Health Checks**: Probing of application health endpoints with configurable checks
3. **Restart Policies**: Automatic recovery from failures with configurable retry behavior
4. **Event Log**: Immutable audit trail of all state changes for debugging and compliance

These components work together to transform Hop3 from a "fire and forget" deployment tool into a resilient, self-monitoring platform.

## Context and Goals

### Context

Currently, Hop3 only synchronizes application state in two scenarios:
1. When the dashboard is viewed (HTMX polling triggers `App.sync_state()`)
2. When lifecycle commands are explicitly run (`hop3 app start`, etc.)

This creates several problems:

1. **State Drift**: If a process crashes overnight, the database shows "RUNNING" while the app is dead. Users discover this only when they check the dashboard or receive user complaints.

2. **No Automatic Recovery**: Failed applications stay in FAILED state indefinitely, requiring manual intervention to restart.

3. **No Proactive Monitoring**: The `[healthcheck]` section in `hop3.toml` is parsed but never used for active monitoring.

4. **No Audit Trail**: When something goes wrong, there's no history of what happened, making debugging difficult.

### Goals

1. **Automatic State Synchronization**: Database state should reflect reality within 60 seconds
2. **Self-Healing**: Applications with appropriate restart policies should recover automatically
3. **Proactive Health Monitoring**: Detect unhealthy applications before they crash
4. **Operational Visibility**: Provide clear audit trail of all state changes
5. **Minimal Overhead**: Background tasks should have negligible performance impact
6. **Single-Server Simplicity**: No distributed coordination complexity

### Non-Goals

- Multi-server/distributed architecture (covered in ADR 017)
- Container orchestration (out of scope)
- External monitoring integration (future work)
- Auto-scaling based on metrics (future work)

## Decision

We will implement a unified **Watchdog** service that runs as part of the Hop3 server process, responsible for:
1. Periodic reconciliation of all application states
2. Execution of configured health checks
3. Enforcement of restart policies
4. Logging of all state change events

## Detailed Design

### 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      Hop3 Server                            │
│                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐   │
│  │   Web UI     │    │   JSON-RPC   │    │   Watchdog   │   │
│  │  (Litestar)  │    │    Server    │    │   Service    │   │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘   │
│         │                   │                   │           │
│         └───────────────────┼───────────────────┘           │
│                             │                               │
│                    ┌────────▼────────┐                      │
│                    │   App Model     │                      │
│                    │  (State Machine)│                      │
│                    └────────┬────────┘                      │
│                             │                               │
│         ┌───────────────────┼───────────────────┐           │
│         │                   │                   │           │
│  ┌──────▼──────┐    ┌───────▼───────┐   ┌──────▼──────┐     │
│  │  AppEvent   │    │    App DB     │   │HealthCheck  │     │
│  │    Log      │    │   (SQLite)    │   │   Results   │     │
│  └─────────────┘    └───────────────┘   └─────────────┘     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │     uWSGI Emperor + Nginx     │
              │      (Process Management)     │
              └───────────────────────────────┘
```

### 2. Database Models

#### 2.1 RestartPolicy Enum

```python
# packages/hop3-server/src/hop3/orm/app.py

class RestartPolicy(enum.Enum):
    """Defines how the system should respond to application failures."""
    NEVER = "never"           # Never auto-restart; require manual intervention
    ON_FAILURE = "on_failure" # Restart only on non-zero exit or crash (default)
    ALWAYS = "always"         # Always restart, even on clean exit
```

#### 2.2 App Model Extensions

```python
# Additional fields for App model

class App(BigIntAuditBase):
    # ... existing fields ...

    # Restart policy configuration
    restart_policy: Mapped[RestartPolicy] = mapped_column(
        SQLAlchemyEnum(RestartPolicy),
        default=RestartPolicy.ON_FAILURE,
        nullable=False
    )
    restart_count: Mapped[int] = mapped_column(default=0)
    max_restarts: Mapped[int] = mapped_column(default=5)
    last_restart_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Health check state
    health_status: Mapped[str] = mapped_column(
        default="unknown"  # "healthy", "unhealthy", "unknown"
    )
    last_health_check_at: Mapped[datetime | None] = mapped_column(nullable=True)
    consecutive_health_failures: Mapped[int] = mapped_column(default=0)

    def reset_restart_count(self) -> None:
        """Reset restart counter after successful sustained running."""
        self.restart_count = 0
        self.last_restart_at = None

    def increment_restart_count(self) -> None:
        """Increment restart counter and record timestamp."""
        self.restart_count += 1
        self.last_restart_at = datetime.utcnow()

    def can_restart(self) -> bool:
        """Check if app is eligible for automatic restart."""
        if self.restart_policy == RestartPolicy.NEVER:
            return False
        if self.restart_count >= self.max_restarts:
            return False
        return True

    def get_restart_backoff_seconds(self) -> int:
        """Calculate exponential backoff for restart attempts."""
        base_backoff = 10  # Start with 10 seconds
        max_backoff = 300  # Cap at 5 minutes
        backoff = base_backoff * (2 ** self.restart_count)
        return min(backoff, max_backoff)
```

#### 2.3 AppEvent Model (New)

```python
# packages/hop3-server/src/hop3/orm/app_event.py

from datetime import datetime
from enum import Enum
from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column
from advanced_alchemy.base import BigIntAuditBase

class EventType(str, Enum):
    """Types of events that can occur in application lifecycle."""
    # State transitions
    STATE_CHANGED = "state_changed"

    # Deployment events
    DEPLOY_STARTED = "deploy_started"
    DEPLOY_COMPLETED = "deploy_completed"
    DEPLOY_FAILED = "deploy_failed"

    # Lifecycle events
    STARTED = "started"
    STOPPED = "stopped"
    RESTARTED = "restarted"
    SCALED = "scaled"

    # Health events
    HEALTH_CHECK_PASSED = "health_check_passed"
    HEALTH_CHECK_FAILED = "health_check_failed"
    MARKED_UNHEALTHY = "marked_unhealthy"
    MARKED_HEALTHY = "marked_healthy"

    # Recovery events
    AUTO_RESTART_TRIGGERED = "auto_restart_triggered"
    AUTO_RESTART_EXHAUSTED = "auto_restart_exhausted"

    # Reconciliation events
    RECONCILED = "reconciled"
    UNEXPECTED_STOP = "unexpected_stop"


class EventSource(str, Enum):
    """Source that triggered the event."""
    USER = "user"                    # Manual user action via CLI/UI
    WATCHDOG = "watchdog"            # Background reconciliation
    HEALTH_CHECK = "health_check"    # Health check system
    SYSTEM = "system"                # System-level events (startup, etc.)


class AppEvent(BigIntAuditBase):
    """Immutable log of application lifecycle events."""

    __tablename__ = "app_event"

    app_id: Mapped[int] = mapped_column(
        ForeignKey("app.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    event_type: Mapped[EventType] = mapped_column(nullable=False, index=True)
    source: Mapped[EventSource] = mapped_column(nullable=False)

    # State change tracking
    old_state: Mapped[str | None] = mapped_column(nullable=True)
    new_state: Mapped[str | None] = mapped_column(nullable=True)

    # Additional context
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict] = mapped_column(default=dict)  # JSON field

    # Actor tracking (for user events)
    triggered_by: Mapped[str | None] = mapped_column(nullable=True)  # username or system identifier

    @classmethod
    def log(
        cls,
        db,
        app_id: int,
        event_type: EventType,
        source: EventSource,
        old_state: str | None = None,
        new_state: str | None = None,
        message: str | None = None,
        details: dict | None = None,
        triggered_by: str | None = None,
    ) -> "AppEvent":
        """Create and persist a new event log entry."""
        event = cls(
            app_id=app_id,
            event_type=event_type,
            source=source,
            old_state=old_state,
            new_state=new_state,
            message=message,
            details=details or {},
            triggered_by=triggered_by,
        )
        db.add(event)
        return event
```

#### 2.4 HealthCheckResult Model (New)

```python
# packages/hop3-server/src/hop3/orm/health_check.py

from datetime import datetime
from enum import Enum
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from advanced_alchemy.base import BigIntAuditBase


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    TIMEOUT = "timeout"
    ERROR = "error"
    SKIPPED = "skipped"  # No health check configured


class HealthCheckResult(BigIntAuditBase):
    """Record of individual health check executions."""

    __tablename__ = "health_check_result"

    app_id: Mapped[int] = mapped_column(
        ForeignKey("app.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    status: Mapped[HealthStatus] = mapped_column(nullable=False)
    response_time_ms: Mapped[int | None] = mapped_column(nullable=True)
    error_message: Mapped[str | None] = mapped_column(nullable=True)

    # Check details
    check_type: Mapped[str] = mapped_column(default="command")  # "command" or "http"
    check_target: Mapped[str | None] = mapped_column(nullable=True)  # command or URL
```

### 3. Health Check Configuration

#### 3.1 hop3.toml Schema Extension

```toml
[healthcheck]
# Command-based health check (runs in app environment)
command = "curl -f http://localhost:$PORT/health"

# OR HTTP-based health check (Hop3 makes the request)
http_path = "/health"
http_method = "GET"
expected_status = 200

# Timing configuration
interval = 30          # Seconds between checks (default: 30)
timeout = 10           # Seconds before check times out (default: 10)
start_period = 60      # Seconds to wait before first check after start (default: 60)

# Failure thresholds
failure_threshold = 3  # Consecutive failures before marking unhealthy (default: 3)
success_threshold = 1  # Consecutive successes before marking healthy (default: 1)
```

#### 3.2 HealthCheckConfig Dataclass

```python
# packages/hop3-server/src/hop3/core/health.py

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class HealthCheckConfig:
    """Configuration for application health checks."""

    # Check method (one of these should be set)
    command: str | None = None
    http_path: str | None = None
    http_method: str = "GET"
    expected_status: int = 200

    # Timing
    interval: int = 30           # seconds
    timeout: int = 10            # seconds
    start_period: int = 60       # seconds

    # Thresholds
    failure_threshold: int = 3
    success_threshold: int = 1

    @property
    def is_configured(self) -> bool:
        """Check if any health check method is configured."""
        return bool(self.command or self.http_path)

    @property
    def check_type(self) -> Literal["command", "http", "none"]:
        if self.command:
            return "command"
        elif self.http_path:
            return "http"
        return "none"
```

### 4. Watchdog Service

#### 4.1 Core Watchdog Implementation

```python
# packages/hop3-server/src/hop3/services/watchdog.py

import asyncio
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from hop3.orm.app import App, AppState, RestartPolicy
from hop3.orm.app_event import AppEvent, EventType, EventSource
from hop3.orm.health_check import HealthCheckResult, HealthStatus
from hop3.orm.session import get_session
from hop3.core.health import HealthChecker

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class WatchdogService:
    """
    Background service responsible for:
    1. Reconciling database state with actual process state
    2. Executing health checks for running applications
    3. Enforcing restart policies for failed applications
    """

    def __init__(
        self,
        reconciliation_interval: int = 30,
        health_check_enabled: bool = True,
    ):
        self.reconciliation_interval = reconciliation_interval
        self.health_check_enabled = health_check_enabled
        self.health_checker = HealthChecker()
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the watchdog background loop."""
        if self._running:
            logger.warning("Watchdog is already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            f"Watchdog started (reconciliation every {self.reconciliation_interval}s, "
            f"health checks {'enabled' if self.health_check_enabled else 'disabled'})"
        )

    async def stop(self) -> None:
        """Stop the watchdog background loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Watchdog stopped")

    async def _run_loop(self) -> None:
        """Main watchdog loop."""
        while self._running:
            try:
                await self._tick()
            except Exception as e:
                logger.exception(f"Watchdog tick failed: {e}")

            await asyncio.sleep(self.reconciliation_interval)

    async def _tick(self) -> None:
        """Execute one watchdog cycle."""
        with get_session() as db:
            # Phase 1: Reconcile all apps
            await self._reconcile_all_apps(db)

            # Phase 2: Run health checks for running apps
            if self.health_check_enabled:
                await self._run_health_checks(db)

            # Phase 3: Handle restart policies
            await self._process_restart_policies(db)

            db.commit()

    async def _reconcile_all_apps(self, db: "Session") -> None:
        """
        Synchronize database state with actual process state.

        This catches scenarios where:
        - A process crashed without Hop3 knowing
        - A process started outside of Hop3
        - State got stuck in transitional state
        """
        apps = db.query(App).filter(
            App.run_state.in_([
                AppState.RUNNING,
                AppState.STARTING,
                AppState.STOPPING,
            ])
        ).all()

        for app in apps:
            await self._reconcile_app(db, app)

    async def _reconcile_app(self, db: "Session", app: App) -> None:
        """Reconcile a single application's state."""
        actual_running = app.check_actual_status()
        old_state = app.run_state

        if app.run_state == AppState.RUNNING and not actual_running:
            # Process died unexpectedly
            logger.warning(f"App '{app.name}' found dead, was marked as RUNNING")
            app._transition_state(AppState.FAILED, "Process stopped unexpectedly")
            AppEvent.log(
                db,
                app_id=app.id,
                event_type=EventType.UNEXPECTED_STOP,
                source=EventSource.WATCHDOG,
                old_state=old_state.name,
                new_state=AppState.FAILED.name,
                message="Process stopped unexpectedly (detected by reconciliation)",
            )

        elif app.run_state == AppState.STARTING:
            if actual_running:
                # Transitional state resolved
                app._transition_state(AppState.RUNNING)
                AppEvent.log(
                    db,
                    app_id=app.id,
                    event_type=EventType.RECONCILED,
                    source=EventSource.WATCHDOG,
                    old_state=old_state.name,
                    new_state=AppState.RUNNING.name,
                    message="Start completed (confirmed by reconciliation)",
                )
            elif self._is_start_timeout_exceeded(app):
                # Start took too long
                app._transition_state(AppState.FAILED, "Start timeout exceeded")
                AppEvent.log(
                    db,
                    app_id=app.id,
                    event_type=EventType.RECONCILED,
                    source=EventSource.WATCHDOG,
                    old_state=old_state.name,
                    new_state=AppState.FAILED.name,
                    message="Start timeout exceeded",
                )

        elif app.run_state == AppState.STOPPING:
            if not actual_running:
                # Stop completed
                app._transition_state(AppState.STOPPED)
                AppEvent.log(
                    db,
                    app_id=app.id,
                    event_type=EventType.RECONCILED,
                    source=EventSource.WATCHDOG,
                    old_state=old_state.name,
                    new_state=AppState.STOPPED.name,
                    message="Stop completed (confirmed by reconciliation)",
                )

    def _is_start_timeout_exceeded(self, app: App, timeout_seconds: int = 120) -> bool:
        """Check if app has been in STARTING state too long."""
        if app.updated_at is None:
            return False
        elapsed = datetime.utcnow() - app.updated_at
        return elapsed > timedelta(seconds=timeout_seconds)

    async def _run_health_checks(self, db: "Session") -> None:
        """Run health checks for all running applications."""
        running_apps = db.query(App).filter(
            App.run_state == AppState.RUNNING
        ).all()

        for app in running_apps:
            await self._check_app_health(db, app)

    async def _check_app_health(self, db: "Session", app: App) -> None:
        """Execute health check for a single application."""
        config = self._get_health_check_config(app)

        if not config.is_configured:
            return  # No health check configured

        # Check if enough time has passed since last check
        if app.last_health_check_at:
            elapsed = (datetime.utcnow() - app.last_health_check_at).total_seconds()
            if elapsed < config.interval:
                return  # Not time for next check yet

        # Check start period
        if app.updated_at:
            since_start = (datetime.utcnow() - app.updated_at).total_seconds()
            if since_start < config.start_period:
                return  # Still in start period

        # Execute health check
        result = await self.health_checker.check(app, config)

        # Record result
        health_result = HealthCheckResult(
            app_id=app.id,
            status=result.status,
            response_time_ms=result.response_time_ms,
            error_message=result.error_message,
            check_type=config.check_type,
            check_target=config.command or config.http_path,
        )
        db.add(health_result)

        # Update app health state
        app.last_health_check_at = datetime.utcnow()

        if result.status == HealthStatus.HEALTHY:
            app.consecutive_health_failures = 0
            if app.health_status != "healthy":
                old_health = app.health_status
                app.health_status = "healthy"
                AppEvent.log(
                    db,
                    app_id=app.id,
                    event_type=EventType.MARKED_HEALTHY,
                    source=EventSource.HEALTH_CHECK,
                    message=f"Health restored after {old_health}",
                )
        else:
            app.consecutive_health_failures += 1
            if app.consecutive_health_failures >= config.failure_threshold:
                if app.health_status != "unhealthy":
                    app.health_status = "unhealthy"
                    AppEvent.log(
                        db,
                        app_id=app.id,
                        event_type=EventType.MARKED_UNHEALTHY,
                        source=EventSource.HEALTH_CHECK,
                        message=f"Failed {app.consecutive_health_failures} consecutive health checks",
                        details={"last_error": result.error_message},
                    )
                    # Trigger failure handling
                    app._transition_state(AppState.FAILED, "Health check failures exceeded threshold")

    def _get_health_check_config(self, app: App) -> "HealthCheckConfig":
        """Load health check configuration for an app."""
        from hop3.core.health import HealthCheckConfig

        try:
            app_config = app.get_config()
            if hasattr(app_config, 'healthcheck') and app_config.healthcheck:
                hc = app_config.healthcheck
                return HealthCheckConfig(
                    command=getattr(hc, 'command', None),
                    http_path=getattr(hc, 'http_path', None),
                    http_method=getattr(hc, 'http_method', 'GET'),
                    expected_status=getattr(hc, 'expected_status', 200),
                    interval=getattr(hc, 'interval', 30),
                    timeout=getattr(hc, 'timeout', 10),
                    start_period=getattr(hc, 'start_period', 60),
                    failure_threshold=getattr(hc, 'failure_threshold', 3),
                    success_threshold=getattr(hc, 'success_threshold', 1),
                )
        except Exception as e:
            logger.debug(f"Could not load health check config for {app.name}: {e}")

        return HealthCheckConfig()  # No health check configured

    async def _process_restart_policies(self, db: "Session") -> None:
        """Process restart policies for failed applications."""
        failed_apps = db.query(App).filter(
            App.run_state == AppState.FAILED,
            App.restart_policy != RestartPolicy.NEVER,
        ).all()

        for app in failed_apps:
            await self._maybe_restart_app(db, app)

    async def _maybe_restart_app(self, db: "Session", app: App) -> None:
        """Attempt to restart an app according to its restart policy."""
        if not app.can_restart():
            # Check if we just exhausted restarts
            if app.restart_count >= app.max_restarts:
                # Only log once when we hit the limit
                recent_events = db.query(AppEvent).filter(
                    AppEvent.app_id == app.id,
                    AppEvent.event_type == EventType.AUTO_RESTART_EXHAUSTED,
                    AppEvent.created_at > datetime.utcnow() - timedelta(hours=1),
                ).count()

                if recent_events == 0:
                    AppEvent.log(
                        db,
                        app_id=app.id,
                        event_type=EventType.AUTO_RESTART_EXHAUSTED,
                        source=EventSource.WATCHDOG,
                        message=f"Restart attempts exhausted ({app.max_restarts} attempts)",
                    )
            return

        # Check backoff period
        if app.last_restart_at:
            backoff = app.get_restart_backoff_seconds()
            elapsed = (datetime.utcnow() - app.last_restart_at).total_seconds()
            if elapsed < backoff:
                return  # Still in backoff period

        # Attempt restart
        logger.info(f"Auto-restarting app '{app.name}' (attempt {app.restart_count + 1}/{app.max_restarts})")

        try:
            app.increment_restart_count()
            AppEvent.log(
                db,
                app_id=app.id,
                event_type=EventType.AUTO_RESTART_TRIGGERED,
                source=EventSource.WATCHDOG,
                message=f"Auto-restart attempt {app.restart_count}/{app.max_restarts}",
                details={"backoff_seconds": app.get_restart_backoff_seconds()},
            )

            # Trigger the restart
            app.start()  # This will transition to STARTING

        except Exception as e:
            logger.exception(f"Auto-restart failed for '{app.name}': {e}")
            AppEvent.log(
                db,
                app_id=app.id,
                event_type=EventType.AUTO_RESTART_TRIGGERED,
                source=EventSource.WATCHDOG,
                message=f"Auto-restart attempt {app.restart_count} failed: {e}",
                details={"error": str(e)},
            )
```

#### 4.2 Health Checker Implementation

```python
# packages/hop3-server/src/hop3/core/health.py (continued)

import asyncio
import subprocess
import time
from dataclasses import dataclass

import httpx

from hop3.orm.health_check import HealthStatus


@dataclass
class HealthCheckResponse:
    """Result of a health check execution."""
    status: HealthStatus
    response_time_ms: int | None = None
    error_message: str | None = None


class HealthChecker:
    """Executes health checks against applications."""

    async def check(self, app, config: HealthCheckConfig) -> HealthCheckResponse:
        """Execute a health check based on configuration."""
        if config.command:
            return await self._check_command(app, config)
        elif config.http_path:
            return await self._check_http(app, config)
        else:
            return HealthCheckResponse(status=HealthStatus.SKIPPED)

    async def _check_command(self, app, config: HealthCheckConfig) -> HealthCheckResponse:
        """Execute command-based health check."""
        start_time = time.monotonic()

        try:
            # Run command in app's environment
            env = app.get_live_env()
            env["PORT"] = str(app.port)

            proc = await asyncio.create_subprocess_shell(
                config.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=str(app.src_path),
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=config.timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                return HealthCheckResponse(
                    status=HealthStatus.TIMEOUT,
                    response_time_ms=int((time.monotonic() - start_time) * 1000),
                    error_message=f"Command timed out after {config.timeout}s",
                )

            elapsed_ms = int((time.monotonic() - start_time) * 1000)

            if proc.returncode == 0:
                return HealthCheckResponse(
                    status=HealthStatus.HEALTHY,
                    response_time_ms=elapsed_ms,
                )
            else:
                return HealthCheckResponse(
                    status=HealthStatus.UNHEALTHY,
                    response_time_ms=elapsed_ms,
                    error_message=f"Exit code {proc.returncode}: {stderr.decode()[:200]}",
                )

        except Exception as e:
            return HealthCheckResponse(
                status=HealthStatus.ERROR,
                error_message=str(e)[:200],
            )

    async def _check_http(self, app, config: HealthCheckConfig) -> HealthCheckResponse:
        """Execute HTTP-based health check."""
        start_time = time.monotonic()

        url = f"http://localhost:{app.port}{config.http_path}"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.request(
                    method=config.http_method,
                    url=url,
                    timeout=config.timeout,
                )

            elapsed_ms = int((time.monotonic() - start_time) * 1000)

            if response.status_code == config.expected_status:
                return HealthCheckResponse(
                    status=HealthStatus.HEALTHY,
                    response_time_ms=elapsed_ms,
                )
            else:
                return HealthCheckResponse(
                    status=HealthStatus.UNHEALTHY,
                    response_time_ms=elapsed_ms,
                    error_message=f"Expected {config.expected_status}, got {response.status_code}",
                )

        except httpx.TimeoutException:
            return HealthCheckResponse(
                status=HealthStatus.TIMEOUT,
                response_time_ms=int((time.monotonic() - start_time) * 1000),
                error_message=f"HTTP request timed out after {config.timeout}s",
            )
        except Exception as e:
            return HealthCheckResponse(
                status=HealthStatus.ERROR,
                error_message=str(e)[:200],
            )
```

### 5. Integration with Server Lifecycle

#### 5.1 Litestar Lifespan Integration

```python
# packages/hop3-server/src/hop3/server/app.py

from contextlib import asynccontextmanager
from hop3.services.watchdog import WatchdogService
from hop3.config import HopConfig

@asynccontextmanager
async def lifespan(app):
    """Application lifespan handler."""
    config = HopConfig()

    # Start watchdog if enabled
    watchdog = None
    if config.watchdog_enabled:
        watchdog = WatchdogService(
            reconciliation_interval=config.watchdog_interval,
            health_check_enabled=config.health_checks_enabled,
        )
        await watchdog.start()

    yield

    # Cleanup
    if watchdog:
        await watchdog.stop()


def create_app():
    app = Litestar(
        lifespan=[lifespan],
        # ... other config ...
    )
    return app
```

#### 5.2 Configuration Options

```python
# packages/hop3-server/src/hop3/config.py (additions)

class HopConfig:
    # ... existing config ...

    @property
    def watchdog_enabled(self) -> bool:
        """Enable/disable the watchdog service."""
        return os.environ.get("HOP3_WATCHDOG_ENABLED", "true").lower() == "true"

    @property
    def watchdog_interval(self) -> int:
        """Reconciliation interval in seconds."""
        return int(os.environ.get("HOP3_WATCHDOG_INTERVAL", "30"))

    @property
    def health_checks_enabled(self) -> bool:
        """Enable/disable health check execution."""
        return os.environ.get("HOP3_HEALTH_CHECKS_ENABLED", "true").lower() == "true"
```

### 6. CLI and API Integration

#### 6.1 New CLI Commands

```python
# packages/hop3-server/src/hop3/commands/health.py

from hop3.core.command import Command

class HealthStatusCommand(Command):
    """Show health status for an application."""
    name = "health:status"

    def run(self, app_name: str) -> dict:
        with get_session() as db:
            app = db.query(App).filter_by(name=app_name).first()
            if not app:
                return {"error": f"App '{app_name}' not found"}

            return {
                "app": app_name,
                "health_status": app.health_status,
                "last_check": app.last_health_check_at.isoformat() if app.last_health_check_at else None,
                "consecutive_failures": app.consecutive_health_failures,
                "restart_count": app.restart_count,
                "restart_policy": app.restart_policy.value,
            }


class HealthHistoryCommand(Command):
    """Show health check history for an application."""
    name = "health:history"

    def run(self, app_name: str, limit: int = 20) -> dict:
        with get_session() as db:
            app = db.query(App).filter_by(name=app_name).first()
            if not app:
                return {"error": f"App '{app_name}' not found"}

            results = db.query(HealthCheckResult).filter_by(
                app_id=app.id
            ).order_by(
                HealthCheckResult.created_at.desc()
            ).limit(limit).all()

            return {
                "app": app_name,
                "checks": [
                    {
                        "timestamp": r.created_at.isoformat(),
                        "status": r.status.value,
                        "response_time_ms": r.response_time_ms,
                        "error": r.error_message,
                    }
                    for r in results
                ]
            }


class EventsCommand(Command):
    """Show event history for an application."""
    name = "app:events"

    def run(self, app_name: str, limit: int = 50) -> dict:
        with get_session() as db:
            app = db.query(App).filter_by(name=app_name).first()
            if not app:
                return {"error": f"App '{app_name}' not found"}

            events = db.query(AppEvent).filter_by(
                app_id=app.id
            ).order_by(
                AppEvent.created_at.desc()
            ).limit(limit).all()

            return {
                "app": app_name,
                "events": [
                    {
                        "timestamp": e.created_at.isoformat(),
                        "type": e.event_type.value,
                        "source": e.source.value,
                        "message": e.message,
                        "old_state": e.old_state,
                        "new_state": e.new_state,
                    }
                    for e in events
                ]
            }


class ResetRestartsCommand(Command):
    """Reset restart counter for an application."""
    name = "app:reset-restarts"

    def run(self, app_name: str) -> dict:
        with get_session() as db:
            app = db.query(App).filter_by(name=app_name).first()
            if not app:
                return {"error": f"App '{app_name}' not found"}

            old_count = app.restart_count
            app.reset_restart_count()
            db.commit()

            return {
                "app": app_name,
                "message": f"Reset restart count from {old_count} to 0",
            }
```

#### 6.2 Dashboard Integration

The dashboard should display:
- Health status indicator (green/yellow/red) for each app
- Last health check timestamp
- Restart count and policy
- Event log timeline

### 7. Database Migrations

```python
# Alembic migration for new tables and columns

def upgrade():
    # Add columns to app table
    op.add_column('app', sa.Column('restart_policy', sa.String(20), default='on_failure'))
    op.add_column('app', sa.Column('restart_count', sa.Integer(), default=0))
    op.add_column('app', sa.Column('max_restarts', sa.Integer(), default=5))
    op.add_column('app', sa.Column('last_restart_at', sa.DateTime(), nullable=True))
    op.add_column('app', sa.Column('health_status', sa.String(20), default='unknown'))
    op.add_column('app', sa.Column('last_health_check_at', sa.DateTime(), nullable=True))
    op.add_column('app', sa.Column('consecutive_health_failures', sa.Integer(), default=0))

    # Create app_event table
    op.create_table(
        'app_event',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('app_id', sa.BigInteger(), sa.ForeignKey('app.id', ondelete='CASCADE'), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('source', sa.String(20), nullable=False),
        sa.Column('old_state', sa.String(20), nullable=True),
        sa.Column('new_state', sa.String(20), nullable=True),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('details', sa.JSON(), default={}),
        sa.Column('triggered_by', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('ix_app_event_app_id', 'app_event', ['app_id'])
    op.create_index('ix_app_event_event_type', 'app_event', ['event_type'])
    op.create_index('ix_app_event_created_at', 'app_event', ['created_at'])

    # Create health_check_result table
    op.create_table(
        'health_check_result',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('app_id', sa.BigInteger(), sa.ForeignKey('app.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('response_time_ms', sa.Integer(), nullable=True),
        sa.Column('error_message', sa.String(500), nullable=True),
        sa.Column('check_type', sa.String(20), default='command'),
        sa.Column('check_target', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('ix_health_check_result_app_id', 'health_check_result', ['app_id'])


def downgrade():
    op.drop_table('health_check_result')
    op.drop_table('app_event')
    op.drop_column('app', 'consecutive_health_failures')
    op.drop_column('app', 'last_health_check_at')
    op.drop_column('app', 'health_status')
    op.drop_column('app', 'last_restart_at')
    op.drop_column('app', 'max_restarts')
    op.drop_column('app', 'restart_count')
    op.drop_column('app', 'restart_policy')
```

## Consequences

### Benefits

1. **Self-Healing Platform**: Applications automatically recover from failures without manual intervention
2. **Proactive Detection**: Health checks detect problems before complete failure
3. **Operational Visibility**: Event log provides clear audit trail for debugging
4. **Consistent State**: Database always reflects actual system state
5. **Configurable Behavior**: Per-app restart policies allow appropriate handling for different workloads
6. **Minimal Overhead**: Single background task with configurable intervals

### Drawbacks

1. **Increased Complexity**: More code to maintain and test
2. **Resource Usage**: Background task consumes some CPU/memory
3. **Database Growth**: Event and health check tables grow over time (need retention policy)
4. **Potential for Restart Loops**: Misconfigured apps could restart repeatedly

### Risks

1. **Restart Storm**: Many apps failing simultaneously could overload the system
   - **Mitigation**: Stagger restarts, implement global rate limiting
2. **Health Check False Positives**: Transient failures triggering unnecessary restarts
   - **Mitigation**: Configurable thresholds and start periods
3. **Database Lock Contention**: Frequent writes from watchdog
   - **Mitigation**: Batch commits, optimize query patterns

## Action Items

### Phase 1: Core Infrastructure (Week 1-2)
- [ ] Create database migrations for new tables/columns
- [ ] Implement AppEvent model and logging
- [ ] Implement HealthCheckResult model
- [ ] Add restart policy fields to App model
- [ ] Write unit tests for new models

### Phase 2: Watchdog Service (Week 2-3)
- [ ] Implement WatchdogService class
- [ ] Implement HealthChecker class
- [ ] Integrate with Litestar lifespan
- [ ] Add configuration options
- [ ] Write integration tests

### Phase 3: CLI and Dashboard (Week 3-4)
- [ ] Implement health:status command
- [ ] Implement health:history command
- [ ] Implement app:events command
- [ ] Update dashboard UI with health indicators
- [ ] Add event log view to dashboard

### Phase 4: Documentation and Testing (Week 4)
- [ ] Update hop3.toml reference documentation
- [ ] Write operational guide for health checks
- [ ] End-to-end testing with failure scenarios
- [ ] Performance testing under load

## Alternatives Considered

### Alternative 1: External Monitoring Tool

Use Prometheus + Grafana or similar external monitoring.

**Pros**: Industry-standard, feature-rich
**Cons**: Additional infrastructure, complexity for single-server use case

**Decision**: Rejected for Phase 1; may integrate in future

### Alternative 2: Systemd Integration

Use systemd's built-in health checking and restart capabilities.

**Pros**: OS-level, well-tested
**Cons**: Tight coupling to systemd, less visibility, harder to customize

**Decision**: Rejected; uWSGI emperor already handles process supervision

### Alternative 3: Separate Watchdog Process

Run watchdog as separate systemd service instead of in-process.

**Pros**: Isolation, can restart independently
**Cons**: More operational complexity, IPC overhead

**Decision**: Deferred; start with in-process, can extract later if needed

## Related

- **ADR 017**: Agent-Based Architecture (future distributed version)
- **ADR 020**: Pluggable Architecture (strategy patterns used here)
- **ADR 027**: Config System Refactoring (Dishka DI integration)

## References

- "Build an Orchestrator in Go (From Scratch)" - Reconciliation loop patterns
- Kubernetes Health Probes: https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/
- Heroku Dyno Management: https://devcenter.heroku.com/articles/dynos
- Docker Health Checks: https://docs.docker.com/engine/reference/builder/#healthcheck
