---
date: 2026-05-15
template: blog_post.html
description: Plugin-based health checks for the platform and deployed apps.
tags:
  - Operations
  - Monitoring
---

# Knowing When Things Break (Before Users Tell You)

Here's how you find out your PaaS is broken: a user emails saying "the app is down." You check the logs. The database connection pool exhausted itself three hours ago. The app has been returning 500 errors ever since. Nobody noticed.

Hop3's health checks exist to shorten that gap. The goal is one command that tells you whether the platform underneath your apps is actually working.

## The Dashboard on Your Terminal

```bash
$ hop3 system status

Hop3 server: hop3-dev (135.181.203.156) — v0.5.0.dev3 — up 14d 3h

Services
  Hop3 Server      ✓ running
  Nginx            ✓ running
  uWSGI Emperor    ✓ running

Backing services
  PostgreSQL       ✓ ok
  MySQL            ✓ ok
  Redis            ⚠ unreachable — connection refused (127.0.0.1:6379)
  S3 (minio)       ✓ ok

Filesystem
  HOP3_ROOT        ✓ writable
  Apps directory   ✓ writable
  Disk usage       ⚠ 86%

Certificates
  SSL              ⚠ self-signed (Let's Encrypt not configured)

Status: ⚠ 2 warnings
```

One glance tells you what's healthy, what's degraded, and what's broken. The identity header up top — host, IP, version, uptime — answers "which server am I even looking at?" before the checks answer "is it OK?".

The severity legend is `✓` ok, `⚠` warning, `✗` failure. Optional services like Redis report `⚠` when unreachable rather than `✗`, so a server that doesn't use Redis reads as *degraded* rather than *failed*. The bottom-line summary rolls everything up to the worst severity seen.

## Each Service Knows Its Own Health

Here's the design decision worth dwelling on: there's no monolithic health checker that knows about everything. Each plugin contributes its own health check, discovered through the `get_health_checks()` hook.

The PostgreSQL addon knows how to verify PostgreSQL is working:

```python
class PostgresHealthCheck:
    name = "postgresql"

    def is_configured(self) -> bool:
        # Skip the check entirely when this server has no PostgreSQL.
        admin = PostgresAdmin.from_config()
        return admin.superuser_password is not None

    def check(self) -> HealthCheckResult:
        try:
            admin = PostgresAdmin.from_config()
            conn = psycopg2.connect(**admin.get_connection_params())
            conn.close()
            return HealthCheckResult(
                name="PostgreSQL",
                passed=True,
                message="ok",
            )
        except Exception as e:
            return HealthCheckResult(
                name="PostgreSQL",
                passed=False,
                message=f"connection failed: {e}",
            )
```

When we add a new addon — say, MongoDB — it ships with its own health check. There's no central list to update: the plugin system handles discovery. `system status` runs every registered check and renders the results.

## A Simple Protocol

Every health check satisfies the same small interface:

```python
@dataclass
class HealthCheckResult:
    name: str
    passed: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    severity: Severity | None = None  # "ok" | "warn" | "fail"


class HealthCheck(Protocol):
    name: str
    def is_configured(self) -> bool: ...
    def check(self) -> HealthCheckResult: ...
```

A check reports `passed`, and severity is derived from it — `passed=True` renders as `ok`, `passed=False` as `fail`. The one nuance worth its own field: a check can set `severity` explicitly to override that default. An optional service that's unreachable returns `passed=False` but `severity="warn"` — the result is unacceptable from the check's point of view, yet the operator can still ship. That's how Redis shows up as a yellow warning instead of a red failure.

`is_configured()` is the other half of keeping the report accurate: a check that doesn't apply to this server says so, and is skipped rather than reported as a spurious failure.

## Reporting at Startup

The same addon checks run when the server starts. If PostgreSQL isn't accepting connections, or Redis is configured but unreachable, the failure is logged with a pointed message — *apps using this service will fail to deploy* — so the problem surfaces in the logs before the first deploy hits it, rather than after.

```python
def verify_addon_health() -> dict[str, HealthCheckResult]:
    results = {}
    for check in get_all_health_checks():
        result = run_health_check(check)
        results[check.name] = result
        if not result.passed:
            logger.warning(
                "%s health check failed: %s. "
                "Apps using this service will fail to deploy.",
                result.name, result.message,
            )
    return results
```

## Your Apps Get a Startup Probe Too

Platform health is one thing; what about the applications running on Hop3? An app can declare a health endpoint in `hop3.toml`:

```toml
[healthcheck]
path = "/health"
timeout = 5
retries = 3
```

At deploy time, Hop3 probes that path before declaring the app up. If `/health` doesn't return a 200 within the window, the deploy doesn't quietly succeed — it fails loudly, with the app reported as not having responded to health checks. That's the difference between "deployed" meaning *the process started* and "deployed" meaning *the app actually answers requests*.

What "healthy" means is up to you. A trivial endpoint:

```python
@app.route("/health")
def health():
    return "OK", 200
```

A better one that checks the dependencies your app can't run without:

```python
@app.route("/health")
def health():
    try:
        db.session.execute("SELECT 1")
        redis_client.ping()
        return "OK", 200
    except Exception as e:
        return f"Unhealthy: {e}", 503
```

The second version is the one that catches the connection-pool scenario from the opening paragraph — *at deploy time*, before you route traffic to a broken release.

## Machine-Readable Output

For automation, `system status` speaks JSON:

```bash
hop3 system status --json
```

This emits the same identity, per-section items, and overall severity as a structured document — feed it to a dashboard or an external monitor. And for the shell-script case, the command sets its exit code from the worst severity it found:

```bash
hop3 system status --quiet

if [ $? -ne 0 ]; then
    echo "System degraded or failed!"
    exit 1
fi
```

Zero means everything's OK; non-zero means there's at least a warning. `--quiet` collapses the report to a single line, which is all a cron job or CI gate needs.

## Where This Is Going

The checks above are the foundation. The direction we're building toward — designed in [ADR 029](https://github.com/abilian/hop3/blob/main/notes/adrs/029-reconciliation-health-checks.md), not yet shipped — turns this from a tool you run into a platform that watches itself:

- **Continuous reconciliation.** A background watchdog that periodically compares each app's recorded state against its actual process state, so a process that dies overnight is detected in seconds rather than when a user complains. Hop3 already has the state-sync primitive (`App.sync_state()`); today it runs when you view the dashboard or issue a lifecycle command, not on a timer.
- **Restart policies.** Per-app `on_failure` / `always` / `never` policies, with exponential backoff and a cap, so transient crashes recover automatically without flapping forever.
- **An event log.** An immutable audit trail of state changes, health results, and restarts — the history you wish you had when something broke at 3 AM.
- **Certificate-expiry monitoring.** Today the certificate check reports whether a real certificate is configured at all (self-signed vs. Let's Encrypt). Tracking days-until-expiry — and warning before a renewal silently fails — is the natural next step.

We're calling those out explicitly because the gap between "designed" and "running" is exactly the kind of thing health checks are supposed to make visible. We'd rather be clear about which is which.

## Try It Now

Check your Hop3 server:

```bash
hop3 system status
```

Add a health endpoint to your app:

```toml
[healthcheck]
path = "/health"
timeout = 5
retries = 3
```

Then build a `/health` that actually checks your dependencies, rather than one that only returns 200.

---

Health checks aren't glamorous, but they're the difference between "we noticed and fixed it" and "a customer told us it was down for three hours." Build the observability in from the start.

*For more on operating Hop3, see the [Administration Guide](/guides/administration/).*
