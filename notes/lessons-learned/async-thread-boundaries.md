# Lessons Learned: Async ↔ Thread Boundaries

**Updated**: 2026-06-07, written after the "every deploy takes ~30s" investigation.

How a background thread talking to an `asyncio` primitive made *every* deployment appear to take ~30s, how it was diagnosed (after a wrong first guess), plus the rule that prevents the whole class.

## The symptom

Every app deployment (trivial static site or real pip build alike) reported almost exactly the same duration (~30–40s). The uniformity was the tell: real work is never that consistent. A no-build static app and a Go build finishing in the same time means a **fixed cost**.

The client showed `Deployment completed successfully in 30.1s`; the deploy *work* on the server was ~2s.

## Root cause: `asyncio.Queue` is not thread-safe

The deploy runs in a background OS thread (`DeployCmd._deploy_streaming` → `threading.Thread(target=run_deployment)`). Logs and the completion signal were pushed to connected CLI clients through a `DeploymentStream` that used an **`asyncio.Queue`**, consumed by the async SSE handler:

```python
# consumer - async handler, on the event loop
event_type, data = await asyncio.wait_for(queue.get(), timeout=30.0)

# producer - runs in the deploy's background thread
queue.put_nowait(("log", entry))   # ❌ cross-thread
```

`asyncio.Queue` is **not thread-safe**. A `put_nowait()` from another thread appends the item, but it does **not** wake the event loop's awaiting `get()`; only operations on the loop's own thread (or `call_soon_threadsafe`) do. So the consumer stayed parked until its `wait_for(..., timeout=30.0)` keepalive fired; on the next iteration the item was finally drained. As a result, logs arrived in 30s batches and the completion event arrived ~30s late. The displayed "duration" is computed when the consumer emits completion → a near-exact 30.0s, every time.

## The fix

Capture the consumer's loop when it subscribes and route every cross-thread put back onto that loop:

```python
# in subscribe() - runs on the event loop
self._loop = asyncio.get_running_loop()

# the single producer chokepoint, called from the background thread
def _notify(self, item):
    loop = self._loop
    for queue in self.subscribers:
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(self._safe_put, queue, item)  # ✅ wakes the loop
        else:
            self._safe_put(queue, item)  # sync/test path, no awaiting consumer
```

`call_soon_threadsafe` is the thread-safe bridge: it schedules the `put` on the loop thread *and* wakes the loop. Deploy time dropped from ~30s to ~2s (static) / ~9s (real pip build). Durations became meaningful again.

See `packages/hop3-server/src/hop3/server/streaming.py` and the regression test `test_cross_thread_notify_is_scheduled_on_the_loop` in `packages/hop3-server/tests/a_unit/server/test_streaming.py`.

## The rule: pick the primitive by who talks to whom

The whole bug class is "wrong primitive for the boundary". Choose by which side produces and which consumes:

| Producer → Consumer | Use | Wake mechanism |
|---------------------|-----|----------------|
| thread → thread | `queue.Queue`, `threading.Event` | built-in (`threading.Condition`), thread-safe |
| coroutine → coroutine (same loop) | `asyncio.Queue`, `asyncio.Event` | the loop |
| **thread → coroutine** | `loop.call_soon_threadsafe(...)` or `asyncio.run_coroutine_threadsafe(...)` | explicitly bridges onto the loop |
| coroutine → thread | a thread-safe object (`queue.Queue`, `threading.Event`) | the thread's blocking wait |

`asyncio.Queue/Event/Future/Condition/Semaphore` are loop-owned: only touch them from the loop thread. The moment a `threading.Thread`, `ThreadPoolExecutor`/`run_in_executor`, an APScheduler job, or a subprocess callback needs to hand data to a coroutine, you need `call_soon_threadsafe`/`run_coroutine_threadsafe`; never a bare `put_nowait`/`set`/`set_result`.

Litestar/Granian handlers run on the event loop; any `threading.Thread` you spawn does not. This bug lives at that boundary.

## Diagnosis lesson: instrument first

The first hypothesis was **wrong**: SQLite uses `busy_timeout=30000`. A blocked writer waits *exactly* 30s, a seductive match for the observed 30.0s. A reproduction even confirmed the mechanism *exists*. But it wasn't the cause.

Instrumentation found it, in order:
1. Per-phase timing inside `do_deploy` → the deploy work was ~2s. (Killed the "slow build/cert/nginx" theories.)
2. A slow-SQL listener (`before/after_cursor_execute`) logged **nothing** ≥2s → no statement; `commit()` is *not* a cursor execute, so a slow commit would have been invisible. Timing the commit showed 0.0s. (Killed the DB-lock theory.)
3. The HTTP access log: `GET /api/stream 200 30033ms` → the 30s lived in the SSE stream.

Takeaways:
- A numeric coincidence (30.0s ≈ a known timeout) is a lead. Confirm the mechanism is on the actual code path before committing to it.
- **Measure each phase.** Every phase here was fast *in isolation*. The cost was in the orchestration/transport, which no single-component probe would reveal.
- **Know your tool's blind spots.** SQLAlchemy `before/after_cursor_execute` does not fire for `commit()`/`rollback()` (DBAPI-level), so "no slow SQL logged" did not mean "no slow DB op".
- **Trust the transport timing.** The web server's own access log (request duration) is ground truth and is immune to application-level log buffering, which was actively misleading here (journald batched the app's log lines tens of seconds apart).

## Auditing for the class

The whole monorepo was swept for the pattern. Useful searches:

```bash
# loop-owned primitives - must only be touched on the loop thread
grep -rnE "asyncio\.(Queue|Event|Future|Condition|Semaphore)\(" packages/*/src
# non-threadsafe loop pokes that might be reached cross-thread
grep -rnE "\.call_soon\(|loop\.create_task\(" packages/*/src
# background execution that might reach into the loop
grep -rnE "threading\.Thread|run_in_executor|asyncio\.to_thread|BackgroundScheduler" packages/*/src
# async DB engines would be loop-owned too
grep -rnE "create_async_engine|async_sessionmaker|AsyncSession" packages/*/src
```

A hit is a **real bug only if** a non-loop thread *mutates* a loop-owned primitive that a coroutine awaits. It is **fine** when:
- the primitive is touched only on the loop (`asyncio.Queue` produced and consumed by coroutines), or
- the cross-thread channel is a thread-safe primitive (`queue.Queue`, `threading.Event`), or
- there's no running loop at all (pure sync CLI / installer code).

As of this writing the only `asyncio.Queue` in the codebase is the (now-fixed) `DeploymentStream`. Examples of the boundary done **correctly** elsewhere (use these as the reference pattern):

- `server/state_sync.py`: background sync thread coordinates via `threading.Event` and a per-thread **sync** SQLAlchemy session; nothing is awaited.
- `hop3_testing/util/streaming.py`: subprocess reader thread feeds a stdlib `queue.Queue` drained by a synchronous caller; no event loop involved.
- `hop3_testlab` scheduler/worker: APScheduler fires jobs on a worker thread that only touch a **sync** sessionmaker (`check_same_thread=False`) and `subprocess`; no asyncio primitive is shared with the async web handlers.
- `hop3_installer` `Spinner`: daemon thread signalled by `threading.Event`; the package has no asyncio at all.

Match the primitive to the boundary. Only the **thread → coroutine** boundary always needs an explicit bridge.

## A second boundary in the same class: iterating what a thread is appending to

The stream's log buffer is written by the producer thread and read by the SSE coroutine, which replays it to a client that connects mid-job. That read is a plain `for` loop suspended at every `yield`. The producer appends *during* the iteration, every time.

That was fine for as long as the buffer was a `list`. It stopped being fine the moment it became a `collections.deque`, which was done for an unrelated reason: `hop3 run` can stream for hours, so the replay buffer needed `maxlen` to stop one chatty job growing the server's memory without limit.

```python
# list: append during iteration is tolerated, silently
# deque: RuntimeError: deque mutated during iteration
for entry in self.logs:
    yield entry.to_sse()
```

The generator died on its first catch-up, before emitting a single event. On a deploy that was working, the operator saw:

```
⚠ Stream ended unexpectedly. Check server logs.
```

The fix is one word: `for entry in list(self.logs)`. But the lesson is not about `deque`:

- **Swapping a container type changes its concurrency contract, not just its capacity.** `list`, `deque`, `dict` and `set` each have their own answer to "what happens if this is mutated while iterated"; only `list` says "nothing visible". A change that reads as a capacity tweak is a concurrency change whenever a second thread can touch the object.
- **Snapshot anything a thread may append to before iterating it**, whether or not today's type complains. The snapshot is also the more correct read: a replay is a statement about the past; the live subscription covers everything after it.
- **Single-threaded tests cannot see this.** Every unit test wrote to the buffer and then read it, which is the one ordering that never fails. The test that catches it writes *from inside the consuming loop*; that is what an awaited generator actually experiences.

### Why it reached the operator and not a test run

The in-process layers passed: 4740 tests, nothing red. Only `tests/c_e2e/` runs a real deploy through a real SSE connection. It was not run before the change was called done. A streaming path has no meaningful in-process coverage of its own concurrency: the layer that exercises it is the one with a container in it.

**Run the e2e layer for any change to the streaming path, the process model, or a shared mutable structure.** Its slowness is the reason it gets skipped and the reason it is the only thing that would have caught this.

## A third boundary: two sessions writing one row

**September 2026.** After a deploy failed in proxy setup, the next deploy of the same app failed once with `Cannot transition app 'x' from STOPPED to RUNNING`, then worked: an outcome that depended on the run before it. Reading the state machine found nothing; instrumenting `transition_state`, `mark_stopped` and SQLAlchemy's `refresh` event on `App` found it in one run.

The deploy request stopped the previous instance in its own session (STARTING → STOPPED) and handed the app's id to the build thread, which opened a second session. The request committed only when it returned, after `build_queue.submit()`. The build thread had already loaded STARTING. It moved the app to STOPPED and back to STARTING, and since the value ended where it was loaded, SQLAlchemy wrote no UPDATE for it. The request's STOPPED, committed in between, persisted. The thread's next reload of the expired object read it back.

- **Commit before a hand-off.** The build helper's docstring already required the app to be committed before the call; nothing enforced it. `deploy_app_streaming` now takes the request session and commits it before submitting, so the contract is kept by the code that relies on it.
- **An ORM write is a diff against what was loaded.** A value that returns to its loaded value is not written, so a concurrent writer's change stands. Two sessions updating the same row is a lost update whichever order they commit in.
- **A failure path records the failure.** The readiness gate set FAILED in memory and raised, and the caller's rollback discarded it, leaving STARTING. A failed deploy now records FAILED, with the underlying error, after the rollback.
