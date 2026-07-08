# Lessons Learned: Deployment Diagnostics

**Updated**: 2026-04-22 - CLI examples migrated from colon syntax to space form per ADR 036.

How to make deployment failures diagnosable, and the patterns that cause "silent nothing" failures.

## The Silent Timeout Anti-Pattern

The worst user experience in a PaaS is: deploy succeeds, app doesn't start, 60 seconds of "Still waiting...", then a generic "App failed to start within 60.0s timeout" with no explanation.

Every timeout path must attempt to diagnose WHY the app failed:

```python
def _handle_startup_timeout(app, timeout):
    log(f"App '{app.name}' failed to start within {timeout}s.")
    recent_logs = app.get_logs(lines=30)
    _diagnose_failure(app, recent_logs)  # pattern-based diagnosis
```

## Pattern-Based Diagnosis

Scan the last N log lines for known failure patterns and provide specific advice:

| Log Pattern | Diagnosis | Suggested Fix |
|-------------|-----------|---------------|
| `operational mode: no-workers` | No WSGI module configured | Add `wsgi = "app:app"` to `[run.workers]` |
| `throttling` | Daemon crashing repeatedly | Check daemon stderr, fix the crash |
| `ECONNREFUSED` / `connection refused` | Can't reach a required service | Check addon services are running |
| `ModuleNotFoundError` / `No such file` | Missing dependency or wrong path | Check virtualenv, file paths |

## The "Set 0 env var(s)" Trap

When env vars from hop3.toml aren't applied on redeploy, logging "Set 0 env var(s)" tells the user nothing. Always log WHAT was skipped and WHY:

```
Skipped 4 env var(s) already set: DEBUG, SECRET_KEY, DB_HOST, DB_PORT
(use 'hop3 env set' to update, or set _policy = "override" in [env])
```

The cost of a verbose skip message is zero. The cost of a user debugging "why didn't my config change take effect" is hours.

## Streaming Build Logs

Long-running build steps (nix-build, npm install, Docker build) must stream output in real-time. Capturing output silently and only showing it on failure means the user has no idea what's happening during a 10-minute build.

```python
# BAD - silent capture
result = subprocess.run(cmd, capture_output=True)

# GOOD - stream stderr, capture for later
proc = subprocess.Popen(cmd, stdout=PIPE, stderr=PIPE)
for line in proc.stderr:
    log(f"  [nix] {line.strip()}", level=1)
```

## Diagnostic Collection Pitfalls

### Path-Style Test Names

Test names like `apps/real-apps-nix/cryptpad` contain slashes. Using them as directory names creates nested dirs instead of flat files:

```python
# BAD - creates apps/real-apps-nix/cryptpad/ (nested)
app_log_dir = failed_apps_dir / test_name

# GOOD - creates cryptpad/ (flat)
base_name = Path(test_name).name
app_log_dir = failed_apps_dir / base_name
```

### Finding App Directories

Deployed app names have timestamp suffixes (`cryptpad-1774987859`). To find them:

```bash
find /home/hop3/apps -maxdepth 1 -name 'cryptpad*' -type d | head -1
```

Use the basename of the test name, not the full path.

## Error Message Format

Follow the pattern:

```
[Component] can't [action]: [plain language explanation], [next action]
```

Examples:
- `uWSGI has no workers - add wsgi = "app:app" to [run.workers] in hop3.toml`
- `Daemon exited with code 1. Last stderr: ImportError: No module named 'flask'`
- `Skipped 4 env vars already set: DEBUG, SECRET_KEY (use 'hop3 env set' to update)`

The message should tell the user: what happened, why, and what to do next. Never just say "failed" or "timeout" without context.

## The Structured `Diagnosis` Record

Enforce the error-message format with a dataclass rather than ad-hoc string formatting. Every failure point in the deployment pipeline should produce a `Diagnosis(component, action, reason, hint)`:

```python
@dataclass(frozen=True)
class Diagnosis:
    component: str  # "Deployer", "NixBuilder", "MySQL addon", …
    action: str     # "start app", "build derivation", "provision user", …
    reason: str     # plain-language explanation of what actually happened
    hint: str       # what the operator should do next
```

Rendering is uniform: `[{component}] can't {action}: {reason}. {hint}.`. The structured record makes two things easy that ad-hoc strings do not:

1. **Review gate.** A missing `hint` is visible in code review; `raise Abort("deploy failed")` is not.
2. **Machine-readable failure.** The CLI and the test runner can surface the component and the action to log files and test reports without string-parsing the rendered message.

Treat bare `raise Abort("deploy failed")` or logger-only failures as regressions. Every path that ends in failure should carry a diagnosis to the CLI.

## Runtime Log Collection Before Cleanup

On an end-to-end test failure, the operator needs the app's directory layout, uWSGI worker logs, build log, generated nginx and uWSGI configs, and (for Docker apps) container state and `docker logs`. Collect all of this *inside* the test's try-block, **before** the test session's cleanup step destroys the app directory and container state:

```python
def run_test(test, session):
    try:
        result = _deploy_and_verify(test, session)
    except Exception as e:
        result = TestResult(test=test, passed=False, error=str(e))
        # Must happen BEFORE session.cleanup() - containers and app dirs
        # will be gone by the time the `finally:` runs.
        result.runtime_logs = collect_runtime_logs(test, session)
        raise
    finally:
        session.cleanup()
    return result
```

The collected context travels back via `TestResult.runtime_logs` and is written to a per-test log file (`test-logs/<mode>-<timestamp>/app-logs/<test>.log`). A single test-suite run is then self-sufficient for post-mortem: no SSH-into-the-target-to-reconstruct-state step is needed.

One practical pitfall: **store the deployed app name (not the test path) on the `TestResult` when the deploy starts.** A test at `apps/real-apps-docker/bookstack` deploys to a timestamped `/home/hop3/apps/bookstack-<timestamp>/`; the debug output then locates it with the glob from "Finding App Directories" above.

## What to Show on Failure

When a deploy fails, gather and display (in order):

1. **Recent logs** (last 20 lines from app log files)
2. **Pattern diagnosis** (match known failure patterns)
3. **Runtime hints** (uWSGI config path, Docker logs command, etc.)
4. **Timeout suggestion** (`start-timeout = 120` in hop3.toml)
5. **Full logs command** (`hop3 app logs --app <app>` for the complete output)

## Verify the running process - "stored" ≠ "what the process sees"

**Updated 2026-06-25.** When debugging "I changed config X but the app behaves as if I didn't", the question is never what's *stored* - it's what the *live process* sees. `hop3 env show` lists the stored config; it does **not** prove the running worker has it. The definitive check is the process's own environment:

```bash
ssh root@<host> 'tr "\0" "\n" < /proc/$(pgrep -f "uvicorn <app>")/environ | grep <VAR>'
```

Confirmed finding worth keeping: **`hop3 env set` + `hop3 app restart` *does* re-bake env into the uWSGI daemon command** (the `sh -c "export VAR=...; exec uvicorn ..."` that uWSGI runs in no-workers mode) and recycles the process - so for this platform, stored == live after a restart. (See [`uwsgi-daemon-management.md`](./uwsgi-daemon-management.md) for the attach-daemon env mechanism.)

The meta-lesson is sharper than the finding: **the moment your own evidence contradicts a hypothesis, drop the hypothesis - don't leave a hedge standing.** During this exact bug I floated "a restart may not re-bake the env" *after* having already shown the new password worked at login (which only happens if the running process sees it). The user's correction - "don't guess, verify" - was right: read `/proc/<pid>/environ`, settle it, move on. A plausible-sounding maybe, left next to evidence that disproves it, is worse than silence.

## A queued user action that nothing advances is a silent failure

**Updated 2026-06-25.** In hop3-testlab, the queue-drain (the dispatch poll that runs UI-triggered builds) was bundled into the **nightly scheduler**, which only starts when `[schedule].enabled`. On a server with the nightly off, a build the user explicitly clicked "Start" on sat `pending` **forever** - nothing would ever pick it up, and nothing said so.

Two rules:

- **A user-initiated action must not be gated behind an unrelated background-feature toggle.** Clicking "Start" enqueued the work; whether the *nightly cron* is enabled is irrelevant to whether that manual build runs. Decouple them: the dispatcher runs whenever the app serves for real; only the nightly *enqueue* is gated.
- **A `pending`/`queued` state that nothing can advance is a silent lie** (CLAUDE.md "fail loud"). Either make it run, or surface *why* it can't (no worker, no credentials, no free target) where the user looks - never leave it sitting with a `-` detail.
