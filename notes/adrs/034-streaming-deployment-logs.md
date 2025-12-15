# ADR 034: Streaming Deployment Logs

**Status**: Accepted
**Type**: Feature
**Created**: 2025-12-15
**Related-ADRs**: 018, 022, 025

## Context

Currently, the `hop deploy` command returns immediately after initiating a deployment, with output like:

```
$ hop deploy myapp
Deploying myapp...
✓ Deployment started
```

This "fire-and-forget" pattern creates several problems:

1. **No visibility**: Users don't see build logs (dependency installation, compilation, errors)
2. **False confidence**: The "success" message appears before the build actually completes
3. **Debugging difficulty**: When builds fail, users must manually check server logs
4. **Poor UX**: Users don't know if the app is actually running

This affects **all deployment types** supported by Hop3:
- **Python apps**: pip install, virtualenv creation
- **Node.js apps**: npm/yarn install, build scripts
- **Go apps**: go mod download, go build
- **Ruby apps**: bundle install
- **Docker apps**: docker build
- **Static sites**: asset processing

The CLI communicates with the server via JSON-RPC over HTTP. JSON-RPC's request-response model doesn't support streaming responses, which contributed to the current fire-and-forget pattern.

## Decision

Implement deployment log streaming in two phases:

### Phase 1: Synchronous Deployment (Quick Win)

Change the deploy command to **block until the build completes**, capturing and returning all output in the response.

**Server changes:**
- Modify `deploy_app()` to capture stdout/stderr from the build process
- Return build output as part of the JSON-RPC response
- Include success/failure status in response

**CLI changes:**
- Wait for the full response (with appropriate timeout)
- Display build output as it's received
- Show clear success/failure indication

```python
# Current behavior (fire-and-forget)
def deploy_app(app_name: str) -> dict:
    app = get_or_create_app(app_name)
    app.deploy()  # Returns immediately, build happens async
    return {"status": "started"}

# Phase 1 behavior (synchronous)
def deploy_app(app_name: str) -> dict:
    app = get_or_create_app(app_name)
    output = app.deploy()  # Blocks until complete, captures output
    return {
        "status": "success" if output.success else "failed",
        "output": output.logs,
        "duration": output.duration,
    }
```

**Pros:**
- Minimal changes required
- Works within existing JSON-RPC framework
- Immediate improvement to user experience
- Output captured in single response

**Cons:**
- Long builds may hit HTTP/proxy timeouts
- No incremental output during build
- Client must wait for full response

### Phase 2: Server-Sent Events Streaming (Full Solution)

Add a streaming endpoint that sends build logs in real-time using Server-Sent Events (SSE).

**Architecture:**

```
CLI                           Server                          Build Process
 │                              │                                   │
 │  POST /rpc {"method":"deploy"} │                                │
 │──────────────────────────────▶│                                  │
 │                              │  Start build, return stream_id    │
 │  {"stream_id": "abc123"}     │◀─────────────────────────────────│
 │◀──────────────────────────────│                                  │
 │                              │                                   │
 │  GET /stream/abc123          │                                   │
 │──────────────────────────────▶│                                  │
 │                              │  SSE: data: Installing deps...   │
 │  data: Installing deps...    │◀─────────────────────────────────│
 │◀──────────────────────────────│                                  │
 │                              │  SSE: data: Building app...      │
 │  data: Building app...       │◀─────────────────────────────────│
 │◀──────────────────────────────│                                  │
 │                              │  SSE: event: complete            │
 │  event: complete             │◀─────────────────────────────────│
 │◀──────────────────────────────│                                  │
```

**New endpoint: `GET /api/stream/{stream_id}`**

Returns an SSE stream with build output:

```
event: log
data: {"line": "Installing dependencies...", "timestamp": "2025-12-15T10:30:00Z"}

event: log
data: {"line": "Building application...", "timestamp": "2025-12-15T10:30:05Z"}

event: complete
data: {"status": "success", "duration": 45.2}
```

**Server implementation:**

```python
# Build log capture
class BuildOutputStream:
    """Captures build output and streams to connected clients."""

    def __init__(self, stream_id: str):
        self.stream_id = stream_id
        self.logs: list[str] = []
        self.subscribers: list[asyncio.Queue] = []
        self.complete = False
        self.success = False

    def write(self, line: str) -> None:
        self.logs.append(line)
        for queue in self.subscribers:
            queue.put_nowait({"event": "log", "data": line})

    def finish(self, success: bool) -> None:
        self.complete = True
        self.success = success
        for queue in self.subscribers:
            queue.put_nowait({"event": "complete", "data": {"status": "success" if success else "failed"}})

# Stream registry
_streams: dict[str, BuildOutputStream] = {}

# SSE endpoint
async def stream_logs(request: Request) -> StreamingResponse:
    stream_id = request.path_params["stream_id"]
    stream = _streams.get(stream_id)
    if not stream:
        raise HTTPException(404, "Stream not found")

    async def generate():
        queue = asyncio.Queue()
        stream.subscribers.append(queue)
        try:
            # Send existing logs first
            for line in stream.logs:
                yield f"event: log\ndata: {json.dumps({'line': line})}\n\n"

            # Stream new logs
            while not stream.complete:
                msg = await queue.get()
                yield f"event: {msg['event']}\ndata: {json.dumps(msg['data'])}\n\n"
        finally:
            stream.subscribers.remove(queue)

    return StreamingResponse(generate(), media_type="text/event-stream")
```

**CLI implementation:**

```python
async def deploy_with_streaming(app_name: str) -> int:
    # Start deployment, get stream ID
    response = await rpc_call("deploy", {"app": app_name})
    stream_id = response.get("stream_id")

    if not stream_id:
        # Fallback to Phase 1 behavior
        print(response.get("output", ""))
        return 0 if response.get("status") == "success" else 1

    # Connect to SSE stream
    async with httpx.AsyncClient() as client:
        async with client.stream("GET", f"{server_url}/api/stream/{stream_id}") as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data:"):
                    data = json.loads(line[5:])
                    if "line" in data:
                        print(data["line"])
                    elif "status" in data:
                        return 0 if data["status"] == "success" else 1
```

### Build Cancellation (Future)

Build cancellation is explicitly deferred to a future phase. For now:
- **Builds continue even if the client disconnects**
- Server-side build process runs to completion
- Logs are retained for later retrieval

Future implementation would add:
- `POST /api/stream/{stream_id}/cancel` endpoint
- Signal handling in build process
- Cleanup of partial builds

### SSH Tunneling

SSH tunneling is deprecated. The CLI now communicates with the server over HTTP. This simplifies streaming implementation as we don't need to handle SSH tunnel limitations.

## Implementation Status

| Component | Status | Notes |
|-----------|--------|-------|
| Phase 1: Log capture | ✅ Implemented | `shell()` routes output through `log()` |
| Phase 1: CLI display | ✅ Existing | `print_log()` handles `t: "log"` entries |
| Phase 1: Deploy command | ✅ Existing | Uses `capture_logs()` context manager |
| Phase 2: SSE streaming | ❌ Not implemented | Future enhancement |
| Build cancellation | ❌ Not implemented | Future enhancement |

## Implementation Plan

### Phase 1 Tasks (Completed)

1. **Modify build process to capture output** ✅
   - Modified `shell()` in `hop3/lib/util.py` to route output through `log()`
   - All subprocess output now gets captured by `capture_logs()` context manager
   - Error output includes both stdout and stderr at appropriate log levels

2. **Deploy command already captures logs** ✅
   - `DeployCmd.call()` uses `capture_logs()` context manager
   - Returns logs as `t: "log"` entries in response

3. **CLI already displays logs** ✅
   - `RichPrinter.print_log()` handles `t: "log"` entries
   - Filters by verbosity level (0-3)
   - Applies color styling from server

### Phase 2 Tasks

1. **Add streaming infrastructure**
   - `BuildOutputStream` class for log capture
   - Stream registry with cleanup
   - SSE endpoint implementation

2. **Modify deploy command**
   - Return `stream_id` in response
   - Start build in background task
   - Connect output to stream

3. **Update CLI**
   - Detect streaming support
   - Connect to SSE endpoint
   - Display logs in real-time
   - Handle reconnection

## Consequences

### Positive

- Users see build output in real-time (Phase 2) or after completion (Phase 1)
- Build failures are immediately visible
- Debugging deployments becomes much easier
- Better UX aligns with user expectations from other PaaS platforms
- Works over HTTP without SSH tunneling

### Negative

- Phase 1: Long builds may hit timeouts
- Phase 2: More complex server architecture
- SSE requires maintaining connection state
- Build logs consume memory until stream closes

### Neutral

- Builds continue server-side regardless of client connection
- Log retention policy will need definition
- Web UI can use same streaming endpoint

## Example Usage

### Python App

```bash
$ hop deploy -v myflask
> Starting deployment for app 'myflask'
-> Using builder: 'LocalBuilder'
--> Creating virtualenv...
--> Installing from requirements.txt
    Collecting Flask==3.0.0
    Collecting gunicorn==21.2.0
    Successfully installed Flask-3.0.0 gunicorn-21.2.0
-> Build successful. Artifact: /home/hop3/apps/myflask/venv
-> Using deployment strategy: 'uwsgi'
> Deployment for 'myflask' finished successfully.

✓ App 'myflask' deployed successfully.
```

### Node.js App

```bash
$ hop deploy -v myexpress
> Starting deployment for app 'myexpress'
-> Using builder: 'LocalBuilder'
--> Running: npm install
    added 57 packages in 3.2s
-> Build successful. Artifact: /home/hop3/apps/myexpress/node_modules
-> Using deployment strategy: 'uwsgi'
> Deployment for 'myexpress' finished successfully.

✓ App 'myexpress' deployed successfully.
```

### Go App

```bash
$ hop deploy -v mygin
> Starting deployment for app 'mygin'
-> Using builder: 'LocalBuilder'
--> Running: go mod download
--> Running: go build -o app
-> Build successful. Artifact: /home/hop3/apps/mygin/src/app
-> Using deployment strategy: 'uwsgi'
> Deployment for 'mygin' finished successfully.

✓ App 'mygin' deployed successfully.
```

### Docker App

```bash
$ hop deploy -v mydocker
> Starting deployment for app 'mydocker'
-> Using builder: 'DockerBuilder'
--> Running: docker build -t hop3/mydocker:latest .
    #1 [internal] load build definition from Dockerfile
    #2 [internal] load metadata for docker.io/library/python:3.12-slim
    #3 [1/4] FROM docker.io/library/python:3.12-slim
    #4 [2/4] COPY requirements.txt .
    #5 [3/4] RUN pip install -r requirements.txt
    #6 [4/4] COPY . .
-> Build successful. Artifact: hop3/mydocker:latest
-> Using deployment strategy: 'docker-compose'
> Deployment for 'mydocker' finished successfully.

✓ App 'mydocker' deployed successfully.
```

### Failed Build (Python)

```bash
$ hop deploy myapp
> Starting deployment for app 'myapp'
-> Using builder: 'LocalBuilder'
--> Installing from requirements.txt
    ERROR: Could not find a version that satisfies the requirement nonexistent-package

✗ Deployment failed (5.1s)
Error: Dependency installation failed
```

### Failed Build (Docker)

```bash
$ hop deploy mydocker
> Starting deployment for app 'mydocker'
-> Using builder: 'DockerBuilder'
--> Running: docker build -t hop3/mydocker:latest .
    #1 [internal] load build definition from Dockerfile
    #2 ERROR: failed to solve: python:3.99: not found

> Docker build failed with exit code 1:
-> Build output:
  ERROR: failed to solve: python:3.99: image not found

✗ Deployment failed
Error: Docker build failed: ERROR: failed to solve: python:3.99: image not found
```

## References

- ADR 018: CLI Architecture
- ADR 022: Build-Deploy Plugin System
- Server-Sent Events specification: https://html.spec.whatwg.org/multipage/server-sent-events.html
- httpx SSE client: https://www.python-httpx.org/
