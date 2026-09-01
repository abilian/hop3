# Lessons Learned: Async ↔ Thread Boundaries

**Updated**: 2026-06-07 - Written after the "every deploy takes ~30s" investigation.

How a background thread talking to an `asyncio` primitive made *every* deployment appear to take ~30s, how it was diagnosed (after a wrong first guess), and the rule that prevents the whole class.

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

`asyncio.Queue` is **not thread-safe**. A `put_nowait()` from another thread appends the item, but it does **not** wake the event loop's awaiting `get()`; only operations on the loop's own thread (or `call_soon_threadsafe`) do. So the consumer stayed parked until its `wait_for(..., timeout=30.0)` keepalive fired; on the next iteration the item was finally drained. Result: logs delivered in 30s batches and the completion event ~30s late. The displayed "duration" is computed when the consumer emits completion → a near-exact 30.0s, every time.

## The fix

Capture the consumer's loop when it subscribes, and route every cross-thread put back onto that loop:

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

`call_soon_threadsafe` is the thread-safe bridge: it schedules the `put` on the loop thread *and* wakes the loop. Deploy time dropped from ~30s to ~2s (static) / ~9s (real pip build), and durations became meaningful again.

See `packages/hop3-server/src/hop3/server/streaming.py` and the regression test `test_cross_thread_notify_is_scheduled_on_the_loop` in `packages/hop3-server/tests/a_unit/server/test_streaming.py`.

## The rule: pick the primitive by who talks to whom

The whole bug class is "wrong primitive for the boundary". Choose by which side produces and which consumes:

| Producer → Consumer | Use | Wake mechanism |
|---------------------|-----|----------------|
| thread → thread | `queue.Queue`, `threading.Event` | built-in (`threading.Condition`) - thread-safe |
| coroutine → coroutine (same loop) | `asyncio.Queue`, `asyncio.Event` | the loop |
| **thread → coroutine** | `loop.call_soon_threadsafe(...)` or `asyncio.run_coroutine_threadsafe(...)` | explicitly bridges onto the loop |
| coroutine → thread | a thread-safe object (`queue.Queue`, `threading.Event`) | the thread's blocking wait |

`asyncio.Queue/Event/Future/Condition/Semaphore` are loop-owned: only touch them from the loop thread. The moment a `threading.Thread`, `ThreadPoolExecutor`/`run_in_executor`, an APScheduler job, or a subprocess callback needs to hand data to a coroutine, you need `call_soon_threadsafe`/`run_coroutine_threadsafe`; never a bare `put_nowait`/`set`/`set_result`.

Litestar/Granian handlers run on the event loop; any `threading.Thread` you spawn does not. This bug lives at that boundary.

## Diagnosis lesson: instrument, don't theorize

The first hypothesis was **wrong**: SQLite uses `busy_timeout=30000`, and a blocked writer waits *exactly* 30s - a seductive match for the observed 30.0s. A reproduction even confirmed the mechanism *exists*. But it wasn't the cause.

Instrumentation found it, in order:
1. Per-phase timing inside `do_deploy` → the deploy work was ~2s. (Killed the "slow build/cert/nginx" theories.)
2. A slow-SQL listener (`before/after_cursor_execute`) logged **nothing** ≥2s → no statement, and  `commit()` is *not* a cursor execute, so a slow commit would have been invisible. Timing the commit showed 0.0s. (Killed the DB-lock theory.)
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

- `server/state_sync.py` - background sync thread coordinates via `threading.Event` and a per-thread **sync** SQLAlchemy session; nothing is awaited.
- `hop3_testing/util/streaming.py` - subprocess reader thread feeds a stdlib `queue.Queue` drained by a synchronous caller; no event loop involved.
- `hop3_testlab` scheduler/worker - APScheduler fires jobs on a worker thread that only touch a **sync** sessionmaker (`check_same_thread=False`) and `subprocess`; no asyncio primitive is shared with the async web handlers.
- `hop3_installer` `Spinner` - daemon thread signalled by `threading.Event`; the package has no asyncio at all.

Match the primitive to the boundary, and the one boundary that always needs an explicit bridge is **thread → coroutine**.
