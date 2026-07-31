# Lessons Learned

**Updated**: 2026-07-28 - added `verifying-an-app-works.md` (catalog acceptance campaign).

This directory collects lessons learned during Hop3 development, to help avoid repeating mistakes.

**Convention:** group each new lesson into the thematically closest file below; create a new file if none fits. Keep this `00README.md` an index - don't accumulate full lessons inline. (Everything below the "Topic deep dives" list - the numbered "Quick Reference" table *and* the full inline lessons - is legacy, predating the thematic-file convention. The topic files are canonical; several inline lessons are already superseded there - see the note above the table.)

## Topic deep dives

- [`app-deploy-runtime-model.md`](./app-deploy-runtime-model.md) - how an app behaves config → build → run: RPC session isolation, deploy-vs-redeploy state transitions, build-vs-runtime env, 502s, eventual consistency, HOST_NAME/proxy semantics.
- [`async-thread-boundaries.md`](./async-thread-boundaries.md) - cross-thread `asyncio` pitfalls (the "every deploy takes 30s" bug) and choosing the right primitive per producer/consumer boundary.
- [`cli-ergonomics.md`](./cli-ergonomics.md) - evolving the CLI command surface safely (rename via alias, deprecate by hiding) and clear help/error messages. (ADR 036)
- [`database-addon-portability.md`](./database-addon-portability.md) - PostgreSQL, MySQL and Redis connectivity (localhost vs 127.0.0.1, host-matching, Docker-bridge rewrites) and per-framework env-var mapping, across native and Docker deployment.
- [`deployment-diagnostics.md`](./deployment-diagnostics.md) - Making deployment failures actionable.
- [`e2e-test-infrastructure.md`](./e2e-test-infrastructure.md) - Building and running the E2E suite.
- [`multi-distribution-support.md`](./multi-distribution-support.md) - Debian / Red Hat / Fedora parity patterns.
- [`native-apps-caveats.md`](./native-apps-caveats.md) - Caveats specific to `builder = "local"` native deployments.
- [`nix-packaging.md`](./nix-packaging.md) - Gotchas from the Nix integration effort.
- [`privilege-and-isolation.md`](./privilege-and-isolation.md) - privileged ops behind the rootd daemon (default-deny allow-list) and path-list confinement via `realpath`. (ADR 046)
- [`uwsgi-daemon-management.md`](./uwsgi-daemon-management.md) - Emperor / vassal lifecycle, attach-daemon env propagation.
- [`verifying-an-app-works.md`](./verifying-an-app-works.md) - the ladder of false greens (build → deploy → 200 → login page → sign-in), why a check that cannot fail proves nothing, `[probe]` accounts, verifying effect over exit code, and why retry must be first-class when you don't roll back.
- [`web-auth-and-csrf.md`](./web-auth-and-csrf.md) - cookie-based CSRF/session auth pitfalls (Litestar): why rotating a password wedged login permanently (`CSRF token verification failed`), self-healing on failure, never showing raw JSON to a browser.

---

## Quick Reference (numbered lesson index)

*A numeric-ordered lookup into the theme-grouped inline lessons below (which are otherwise ordered by topic, not number). Some entries are now superseded by a topic file and duplicated here only for history: 2, 6, 7 → `multi-distribution-support.md`; 18 → `async-thread-boundaries.md`. The rest have no topic-file home yet - migrate them when a fitting file exists.*

| # | Lesson |
|---|--------|
| 1 | Enable strict validation modes; fail fast on invalid input |
| 2 | Test on multiple distributions; don't assume paths or versions |
| 3 | Use structured, removable debug logging with consistent prefixes |
| 4 | Document repository requirements; package names vary by distro |
| 5 | Review inherited code critically; don't assume it's correct |
| 6 | Use official backports, never mix distribution releases |
| 7 | Install via pip when packages differ across distributions |
| 8 | Always specify `ondelete` behavior on foreign keys |
| 9 | Escape user content before passing to formatting libraries |
| 10 | Use specific error patterns, not generic substring matches |
| 11 | Default to safe/offline options; test config differs from prod |
| 12 | Validate CLI arguments before confirmation prompts |
| 13 | Check port listening, not just process existence |
| 14 | Docker bridge and Compose use different network ranges |
| 15 | Use lazy imports when ORM models need business logic |
| 16 | Use `--yes`, `CI=true` for non-interactive CLI tools |
| 17 | Server provides runtimes; tutorials install frameworks |
| 18 | Bridge thread→coroutine with `call_soon_threadsafe`; never poke `asyncio` primitives cross-thread |

---

## Configuration & Validation

### 1. Validate Configuration and Data Early (Fail Fast)

**Lesson**: Always enable strict validation modes and fail fast on invalid input. Silent failures waste debugging time.

**Case Study - uWSGI `project` directive (March 2026)**:

The codebase included a `project` directive in uWSGI configuration inherited from piku. This directive does not exist in uWSGI - it was silently ignored for months because uWSGI's default behavior is to ignore unknown directives. The problem only surfaced when `strict = true` was added.

**Best practices**:
- Enable strict/validation modes by default (e.g., `strict = true` in uWSGI)
- Validate configuration against schemas when possible
- Fail loudly on invalid input rather than silently ignoring it
- Test with strict modes enabled in CI

### 5. Inherited Code Requires Validation

**Lesson**: Code inherited from other projects (like nua or piku) may contain bugs or assumptions that don't apply to your context.

**Best practices**:
- Review inherited code critically - don't assume it's correct just because it's been working
- Test with strict/validation modes enabled

### 10. Avoid Generic Error Detection Patterns

**Lesson**: When detecting errors in logs or output, use specific patterns rather than generic ones. Generic patterns like "error" will match normal log output.

**Case Study - Crash detection false positives (February 2026)**:

The crash detector was marking apps as crashed because they logged `ERROR:searx:` or similar standard Python logging output containing the word "error".

**Best practices**:
- Use specific error patterns, not generic substring matches
- For crash detection, match actual crash indicators from the process manager (e.g., `"throttling"`, `"respawning"`, `"fatal error"`)
- Consider context: is this pattern from the app (normal) or from the process manager (critical)?

### 11. Test Configuration Should Differ from Production Defaults

**Lesson**: Safe defaults for testing (non-destructive, offline-capable) often differ from production defaults. Make this explicit in configuration.

**Case Study - ACME/certbot failing in system tests (March 2026)**:

System tests failed because the server defaulted to using `certbot` for SSL certificates, but test domains (like `test-app.hop.local`) couldn't pass ACME challenges.

**Best practices**:
- Default to safe/offline options (`self-signed` instead of `certbot`)
- Only enable production features when explicitly configured
- Document which settings differ between test and production

---

## Cross-Platform & Distribution

### 2. Cross-Distribution Testing Reveals Hidden Assumptions

**Lesson**: Code that works on one distribution may fail on others due to different package versions, paths, or default configurations.

**Case Study - Python version on RHEL 9 clones (March 2026)**:

The Python toolchain hardcoded `/usr/bin/python3` for creating virtualenvs. This worked on Debian/Ubuntu/Fedora where python3 is 3.10+, but failed on Rocky 9 where `/usr/bin/python3` is Python 3.9.

**Best practices**:
- Test on multiple distributions (Debian, Ubuntu, Fedora, RHEL clones)
- Don't assume specific paths or versions
- Implement version detection with fallbacks or early failure
- Document minimum version requirements

### 4. Package Availability Varies by Distribution

**Lesson**: Package names and repository availability differ significantly across distributions.

**Case Study - libyaml-devel on RHEL 9 (March 2026)**:

The `libyaml-devel` package required for building Python packages was not available in Rocky 9's base repositories - it required enabling the CRB (CodeReady Builder) repository.

**Best practices**:
- Document repository requirements (EPEL, CRB, etc.)
- Test package installation on minimal/fresh systems
- Have fallback strategies for missing packages

### 6. Never Mix Distribution Releases - Use Backports

**Lesson**: Adding a newer release's repository (e.g., trixie) to an older release (e.g., bookworm) is effectively a partial upgrade that can break the system. Use official backports instead.

**Case Study - Debian 12 Go version (March 2026)**:

To get a newer Go version on Debian 12 (bookworm), the installer was adding the trixie (Debian 13) repository. This is dangerous because APT's dependency resolver may pull trixie versions of other packages.

**Best practices**:
- Use official backports: `deb http://deb.debian.org/debian bookworm-backports main`
- Install specific packages from backports: `apt install -t bookworm-backports golang-go`
- If a package isn't in backports, consider installing from upstream or documenting the limitation

### 7. Prefer pip-Installed Packages Over Distro Packages for Consistency

**Lesson**: When a package behaves differently across distributions (different versions, build options, or plugin architectures), install it via pip instead of relying on distro packages.

**Case Study - uWSGI plugin complexity (March 2026)**:

System-packaged uWSGI uses a modular plugin architecture with different paths on each distro. This led to 70+ lines of fragile plugin detection code.

**Best practices**:
- When a tool has cross-distro inconsistencies, install via pip in the project's venv
- pip-installed packages are identical across all distros
- Eliminates detection/compatibility code
- Version is controlled by the project, not the distro

---

## Database & ORM

### 8. Database Foreign Keys Need CASCADE for Proper Deletion

**Lesson**: When defining foreign key relationships, always consider what should happen when the parent record is deleted. Missing CASCADE constraints cause constraint violation errors.

**Case Study - App deletion failing (March 2026)**:

Deleting an app failed with `FOREIGN KEY constraint failed` because `EnvVar` and `Backup` tables had foreign keys without `ondelete="CASCADE"`.

**Best practices**:
- Always specify `ondelete` behavior on foreign keys
- Use `CASCADE` when children should be deleted with parent
- Use `SET NULL` when children should be orphaned
- Use `RESTRICT` when deletion should be prevented
- Test deletion scenarios, not just creation

### 15. Circular Imports via ORM - Use Lazy Imports

**Lesson**: When ORM models need to call business logic that imports the same ORM, use lazy imports inside methods rather than at module level.

**Case Study - Circular import in app.py (January 2026)**:

Adding a method to `App` model that called `do_deploy()` caused a circular import because `deployer.py` imports `App`.

**Best practices**:
- Keep ORM models thin - they shouldn't contain complex business logic
- When ORM methods need external functionality, import inside the method body
- Use `if TYPE_CHECKING:` for type hints, lazy import for runtime

```python
def deploy(self):
    # Lazy import to avoid circular dependency
    from hop3.deployers.deployer import do_deploy
    do_deploy(self.name)
```

---

## Deployment & Runtime

### 13. Verify Deployment Success by Checking Port, Not Process

**Lesson**: For web applications, checking if the port is listening is more reliable than checking if a process exists. Processes can start but fail to bind their port.

**Case Study - False positive deployments (December 2025)**:

The uWSGI deployer's `check_status()` was returning success if `pgrep` found uWSGI processes, even when the app had failed to bind to its port.

**Best practices**:
- Use port check as the primary health indicator for web apps
- Process existence is necessary but not sufficient
- Poll actual state (port listening) before declaring deployment success
- Set database state to RUNNING only after verifying the port is bound

### 14. Docker and Docker Compose Use Different Network Ranges

**Lesson**: Docker bridge networks (172.17.x.x) and Docker Compose networks (192.168.x.x) use different IP ranges. Services that whitelist network access must allow both.

**Case Study - PostgreSQL connection failures in Docker Compose (December 2025)**:

Docker-based apps using Docker Compose couldn't connect to the host PostgreSQL because pg_hba.conf only allowed 172.17.0.0/16, but Compose used 192.168.x.x addresses.

**Best practices**:
- Configure database access for both Docker bridge (172.17.0.0/16) and Compose (192.168.0.0/16)
- Test database connectivity from both Docker run and Docker Compose deployments
- When changing Docker daemon network configuration, verify all service configurations are updated

---

## CLI & User Experience

### 3. Debug Logging Should Be Structured and Removable

**Lesson**: When adding debug logging, make it structured and easy to identify for later removal.

**Best practices**:
- Use consistent prefixes for debug logs (e.g., `[DEBUG]` or specific log levels)
- Use a debug flag that can be toggled
- Remove investigation-specific logging before merging; keep essential operational logging

### 9. Escape User Content Before Passing to Formatting Libraries

**Lesson**: User-provided content (log messages, filenames, etc.) may contain characters that formatting libraries interpret as markup. Always escape before formatting.

**Case Study - Rich markup parsing bug (February 2026)**:

Log messages containing brackets (like `[database]` or `[2026-02-27]`) were being parsed as Rich markup tags, causing formatting errors or garbled output.

**Best practices**:
- Escape user content with the library's escape function (e.g., `rich.markup.escape()`)
- Treat all external input as potentially containing special characters
- Apply escaping at the boundary before formatting

### 12. Validate CLI Arguments Before Confirmation Prompts

**Lesson**: For destructive commands, validate that required arguments are present before asking for confirmation. Users shouldn't confirm an action that will fail anyway.

**Case Study - `hop3 app destroy` UX issue (March 2026)**:

Running `hop3 app destroy` without an app name (and with no app resolvable from the D7 chain) would ask "Are you sure?", user types "yes", then command fails because no app name was provided.

**Best practices**:
- Check required arguments FIRST, before any user interaction
- Fail fast with helpful error message if arguments are missing
- Don't perform expensive operations until you know the command can succeed
- Order of operations: parse args → validate args → confirm → execute

### 16. Interactive CLI Prompts Fail in CI Environments

**Lesson**: Modern framework scaffolding tools often have interactive prompts that hang or fail in non-TTY environments like CI pipelines.

**Case Study - JavaScript framework tutorials failing (December 2025)**:

Tutorials for Next.js, Nuxt.js, and NestJS were failing because `npm init` or framework CLIs prompted for options and hung waiting for input.

**Best practices**:
- Use non-interactive flags: `--yes`, `--default`, `-y`
- Set `CI=true` environment variable (many tools detect this)
- Provide all required options via command-line arguments
- Test scaffolding commands in non-TTY environments

---

## Testing & Architecture

### 17. Tutorials Should Install Their Own Framework Dependencies

**Lesson**: The server/installer should provide base language runtimes, not pre-installed frameworks. Tutorials install their own dependencies as part of setup.

**Case Study - Framework "not found" errors (January 2026)**:

Tutorials were failing with "rails not found" or "jekyll not found" because we expected frameworks to be pre-installed on the server.

**Best practices**:
- Server provides: Ruby, Python, Node, PHP, Go, Elixir, .NET, Java
- Tutorials provide: `gem install rails`, `pip install flask`, `npm install express`
- This matches real developer workflow (fresh server doesn't have Rails)
- Each tutorial is self-contained and documents its dependencies

**Architecture:**

| Layer | Provides | Examples |
|-------|----------|----------|
| Server/Installer | Base language runtimes | ruby, python, node, php, go |
| Tutorials | Framework dependencies | rails, jekyll, phoenix, django |

---

## Concurrency & Async

### 18. Bridge thread→coroutine with `call_soon_threadsafe`

**Lesson**: `asyncio` primitives (`Queue`, `Event`, `Future`, …) are owned by the event loop and are **not thread-safe**. A background thread must never mutate one directly - it must marshal the call onto the loop with `loop.call_soon_threadsafe(...)` (or `asyncio.run_coroutine_threadsafe(...)`). Full write-up: [`async-thread-boundaries.md`](./async-thread-boundaries.md).

**Case Study - "every deploy takes ~30s" (June 2026)**:

The deploy runs in a `threading.Thread`, but pushed SSE logs to clients through an `asyncio.Queue` consumed by the async handler. A cross-thread `queue.put_nowait()` doesn't wake the loop's awaiting `get()`, so the consumer only advanced on its 30s keepalive - making *every* deployment report ~30s regardless of real work (~2s).

**Best practices**:
- Pick the primitive by boundary: thread↔thread → `queue.Queue`/`threading.Event`; loop↔loop → `asyncio.*`; **thread→coroutine → `call_soon_threadsafe`/`run_coroutine_threadsafe`**.
- Litestar/Granian handlers run on the loop; any `threading.Thread` you spawn does not - that seam is where this bug lives.
- A numeric coincidence (30.0s ≈ a known timeout, here SQLite `busy_timeout`) is a *lead*, not a verdict. Instrument each phase and trust the web server's access-log durations over app-level logs (which buffer and mislead).

| Producer → Consumer | Use | Why |
|---------------------|-----|-----|
| thread → thread | `queue.Queue`, `threading.Event` | thread-safe (built on `threading.Condition`) |
| coroutine → coroutine (same loop) | `asyncio.Queue`, `asyncio.Event` | the loop schedules wakeups |
| **thread → coroutine** | `loop.call_soon_threadsafe` / `run_coroutine_threadsafe` | the only boundary needing an explicit bridge |
