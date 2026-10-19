# Lessons Learned: Deployment Diagnostics

**Updated**: 2026-09-08, adding the rootd reload check and disk exhaustion. 2026-04-22: CLI examples migrated from colon syntax to space form per ADR 036.

How deployment failures become diagnosable, and the patterns behind "silent nothing" failures.

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

Test names like `apps/real-apps-nix/cryptpad` contain slashes. Using them as directory names creates nested dirs. Use the basename to produce a flat file:

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

Use the basename of the test name.

## Error Message Format

Follow the pattern:

```
[Component] can't [action]: [plain language explanation], [next action]
```

Examples:
- `uWSGI has no workers - add wsgi = "app:app" to [run.workers] in hop3.toml`
- `Daemon exited with code 1. Last stderr: ImportError: No module named 'flask'`
- `Skipped 4 env vars already set: DEBUG, SECRET_KEY (use 'hop3 env set' to update)`

The message should tell the user: what happened, why, and what to do next.

## The Structured `Diagnosis` Record

Enforce the error-message format with a dataclass. Every failure point in the deployment pipeline should produce a `Diagnosis(component, action, reason, hint)`:

```python
@dataclass(frozen=True)
class Diagnosis:
    component: str  # "Deployer", "NixBuilder", "MySQL addon", …
    action: str     # "start app", "build derivation", "provision user", …
    reason: str     # plain-language explanation of what actually happened
    hint: str       # what the operator should do next
```

Rendering is uniform: `[{component}] can't {action}: {reason}. {hint}.`. The structured record makes two things easy:

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

To avoid one practical pitfall, store the deployed app name on the `TestResult` when the deploy starts, and store it in preference to the test path. A test at `apps/real-apps-docker/bookstack` deploys to a timestamped `/home/hop3/apps/bookstack-<timestamp>/`; the debug output then locates it with the glob from "Finding App Directories" above.

## What to Show on Failure

When a deploy fails, gather and display (in order):

1. **Recent logs** (last 20 lines from app log files)
2. **Pattern diagnosis** (match known failure patterns)
3. **Runtime hints** (uWSGI config path, Docker logs command, etc.)
4. **Timeout suggestion** (`start-timeout = 120` in hop3.toml)
5. **Full logs command** (`hop3 app logs --app <app>` for the complete output)

## Verify the running process: "stored" ≠ "what the process sees"

**Updated 2026-06-25.** When debugging "I changed config X but the app behaves as if I didn't", the question is what the *live process* sees. `hop3 env show` lists the stored config; it does **not** prove the running worker has it. The definitive check is the process's own environment:

```bash
ssh root@<host> 'tr "\0" "\n" < /proc/$(pgrep -f "uvicorn <app>")/environ | grep <VAR>'
```

`hop3 env set` + `hop3 app restart` *does* re-bake env into the uWSGI daemon command (the `sh -c "export VAR=...; exec uvicorn ..."` that uWSGI runs in no-workers mode) and recycles the process. For this platform, stored == live after a restart. (See [`uwsgi-daemon-management.md`](./uwsgi-daemon-management.md) for the attach-daemon env mechanism.)

The moment your own evidence contradicts a hypothesis, drop the hypothesis. During this bug the first analysis floated "a restart may not re-bake the env" *after* having already shown the new password worked at login (which only happens if the running process sees it). The maintainer's correction ("don't guess, verify") was right: read `/proc/<pid>/environ` and move on. A plausible-sounding maybe, left next to evidence that disproves it, is worse than silence.

## A queued user action that nothing advances is a silent failure

**Updated 2026-06-25.** In hop3-testlab, the queue-drain (the dispatch poll that runs UI-triggered builds) was bundled into the **nightly scheduler**, which only starts when `[schedule].enabled`. On a server with the nightly off, a build the user explicitly clicked "Start" on sat `pending` **forever**; nothing would ever pick it up or say so.

Two rules:

- **A user-initiated action must not be gated behind an unrelated background-feature toggle.** Clicking "Start" enqueued the work; whether the *nightly cron* is enabled is irrelevant to whether that manual build runs. Decouple them: the dispatcher runs whenever the app serves for real; only the nightly *enqueue* is gated.
- **A `pending`/`queued` state that nothing can advance is a silent lie** ("fail loud"). Either make it run, or surface *why* it can't (no worker available) where the user looks. Never leave it sitting with a `-` detail.

## Match the process manager's words

A crash detector that searched app output for "error" marked apps as crashed because their own logging wrote `ERROR:searx:` on ordinary lines. Detect crashes from the process manager's vocabulary (`throttling`, `respawning`, `fatal error`), and keep in mind whose line it is: the app's `ERROR` is ordinary output, while the Emperor's `throttling` is a crash.

## A timing ceiling is a false failure under load

**September 2026.** rootd verifies an nginx reload by watching for fresh worker processes, because `nginx -s reload` returns 0 whether or not nginx accepted the new configuration. The check gave nginx two seconds. On a host running an e2e alongside a Nix build, a reload that nginx had accepted forked its workers later than that. The deploy was refused with "did not apply the new config". Nothing was wrong with the config.

The discriminator was already in reach: a rejected reload logs `[emerg]` to the error log at once, an accepted one logs nothing. The check now fails immediately on a logged rejection and waits up to fifteen seconds only when nginx logged nothing, since an accepted reload always forks. When a check has a timing budget, ask what evidence distinguishes "slow" from "refused" and use it before giving up.

**The corollary, learned the hard way in September 2026.** Because that signal stays ambiguous (the fifteen-second path means "accepted, no error, no worker yet", which is *probably* slow and *possibly* broken), nothing that repairs state may hang off it.

Rolling a rejected config out of the include directory is right: `nginx -t` refusing it is unambiguous, so the config was certainly not applied. Leaving it breaks every later validation. Extending the same rollback to a failed *reload* looks symmetrical and is wrong. nginx forks its workers asynchronously, so a reload reported as failed may already have been applied. Rolling the file back then leaves disk disagreeing with what nginx is serving. The next reload, another app's deploy or a certificate renewal, silently reverts the app's routes. The repair turns a slow reload into a lost one.

The rule is that a recovery action needs a signal that is certain. Ask what the signal actually proves. "Rejected" proves the config is not live. "The reload did not take within a budget" proves nothing about whether it is live, so the only safe response is to fail the deploy and change nothing. That costs nothing here, since a validated config on disk passes `nginx -t` and the next reload picks it up.

## Disk exhaustion presents as a PostgreSQL PANIC

`PANIC: could not write to file "pg_wal/...": No space left on device` takes PostgreSQL down and every addon-backed app with it. Recovery is manual and ordered: free space, start PostgreSQL, start hop3-server, redeploy. A deploy should refuse to start when free space is below a floor; the platform should say so before the database does. The guard is on the 0.8 list.

## A probe that does not identify itself is refused by some apps

**September 2026.** Both GoToSocial variants failed a catalog run at the readiness gate: sixty seconds of polling, every request answered `418 I'm a teapot`, deploy refused. The app was fine; it served the test harness's `curl` on the same path a moment later. GoToSocial refuses any request that arrives without a `User-Agent` (a common enough bot filter). `http.client` sends none unless asked. Every other HTTP client in the tree said who it was (`hop3-fetch`, `hop3-ping/1.0`); the one that gates every deploy did not.

An anonymous request is not a neutral one. A probe is a client: give it a name. Prefer a stand-in server that reproduces the app's actual rejection over checking a header dict, because the header matters only if it passes through the client library intact.

## Name the port the app actually bound

The commonest deploy failure there is: the app ignores `$PORT` and binds one of its own (Grafana's 3000 without `GF_SERVER_HTTP_PORT`). It starts cleanly, logs `HTTP Server Listen`, and is invisible to both the probe and the proxy. The platform said only "did not respond to health checks within 60.0s" and offered a longer deadline. That is the one remedy that cannot work, for an app that was already up.

The evidence was a procfs read away the whole time: `/proc/net/tcp{,6}` lists every listening socket with its inode and `/proc/<pid>/fd` says who holds it, so the app's own sockets can be named against the port it was assigned. When a check times out, ask what the system can still be *asked* before falling back to "it didn't answer"; an unanswered question is not the same as an absent one.

## `${VAR}` in a literal section is a silent misconfiguration

Grafana's recipe carried `GF_DATABASE_HOST = "${PGHOST}:${PGPORT}"` and `GF_SERVER_HTTP_PORT = "${PORT:-8080}"` under `[env]`, which is literal (the values were exported verbatim). The app fell back to SQLite and to its own port 3000, so the PostgreSQL addon Hop3 had provisioned sat empty and the proxy pointed at a port nothing bound. Everything up to the readiness gate reported success.

Three sections, three different behaviours, and only the deploy log could tell them apart: `[env]` is literal, `[env.computed]` interpolates `${VAR}` (no `:-default` form) against the app's environment after addons, and `$PORT` exists in neither because it is allocated later; it belongs in `[run].start`, which runs through a shell. A schema validator can only police a difference that exists in the schema. The check now lives in the schema, so `hop3check` catches it before a deploy with an error naming which of the three the value actually wants.

## A diagnosis is a measurement, not an inference

A deploy timed out and the platform said "the app's port is listening but it did not answer an HTTP request: the server bound its socket but no worker is serving (the worker failed to boot, or is hung)". The app had answered 173 requests in the previous 100 seconds, each logged at ~0s by its own framework. The diagnosis was drawn from one fact (the port is listening). The writer of that branch had a specific failure in mind (gunicorn's master binds before the workers fork). He did not consider the other way to reach the same line: with `[healthcheck].contains` set, an app that answers everything still fails the gate when no page carries the marker.

The cost is not the wrong words. The message routed the reader to workers, boot order and the timeout, and offered a longer deadline, when the answer was one string in the recipe. A named cause is trusted more than a generic one, so a confidently wrong name costs more than "failed to start".

The failure path now asks the app one more question before it speaks, and reports what came back: the path probed, the status, the marker that did not match, and the first 200 characters served instead. When a diagnosis has two possible causes and distinguishing them costs one request, make the request. Write the fallback so it is true whenever it is reached, including cases outside the one you had in mind.
