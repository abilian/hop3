# Lessons Learned: uWSGI Daemon Management

How Hop3 uses uWSGI to manage application processes, and the non-obvious behaviors that cause deployment failures.

## Architecture

Hop3 runs a uWSGI Emperor that watches `/home/hop3/uwsgi-enabled/` for `.ini` files. Each app gets one or more `.ini` files (one per worker type: wsgi, web, generic, cron). The Emperor spawns a vassal process for each config file.

## Daemon Types

| Worker Type | uWSGI Mechanism | Use Case |
|-------------|-----------------|----------|
| `wsgi` | `module` directive | Python WSGI apps (Flask, Django) |
| `web` | `attach-daemon` | Generic web process (Node.js, Go, Gunicorn) |
| `generic` | `attach-daemon` | Background workers, schedulers |
| `cron` | `cron` directive | Scheduled tasks |
| `static` | No uWSGI process | nginx serves files directly |

## The `attach-daemon` Working Directory Trap

uWSGI's `chdir` directive sets the working directory for WSGI workers, but **`attach-daemon` processes may not inherit it**. They fork from the Emperor, not from the chdir'd master.

**Symptom:** Daemon starts, immediately fails with "No such file or directory" for a relative path.

**Fix:** Explicitly `cd` in the daemon's shell command:

```python
shell_cmd = f'sh -c "cd {app.src_path} && {exports}; {command}"'
settings.add("attach-daemon", shell_cmd)
```

## Throttle State Survives Redeploy

When a daemon crashes, uWSGI increases the respawn delay exponentially: 4s → 8s → 29s → 111s → 232s. This throttle state lives in the Emperor's memory and is **per vassal config file path**.

If you fix a bug and redeploy, the new vassal config has the same path, so the Emperor may still throttle it for minutes.

**Symptom:** "I fixed the bug, redeployed, but the app still doesn't start."

**Fix:** Fully stop the vassal (unlink the `.ini` file) and wait for the old process to terminate before creating a new config:

```python
def stop(self):
    for config_file in UWSGI_ENABLED.glob(f"{app_name}*.ini"):
        config_file.unlink()
    self._wait_for_processes_to_stop()  # pgrep + wait loop
```

## The "no-workers" Silent Failure

If a Python app has no `wsgi` worker configured (e.g., missing Procfile entry or hop3.toml `[run.workers]`), uWSGI starts in "Operational MODE: no-workers". The master process runs, logs look normal, but no HTTP workers exist. Health checks time out after 60s with no useful error.

**Fix 1:** Detect early — check for web-facing workers before spawning:

```python
if not self.web_workers and artifact.kind in {"python", ...}:
    log("WARNING: No web-facing workers configured...")
```

**Fix 2:** Auto-discover WSGI modules — probe for `wsgi.py`, `app.py`, Django convention:

```python
if (src_path / "wsgi.py").exists():
    artifact.runtime.workers["wsgi"] = "wsgi:application"
```

## Environment Variable Propagation

uWSGI's `attach-daemon` processes do NOT inherit environment variables from the uWSGI config. The `env = KEY=VALUE` directives only apply to WSGI workers.

**Fix:** Explicitly export all env vars in the daemon's shell command:

```python
exports = [f"export {key}='{value}'" for key, value in env.items()]
shell_cmd = f'sh -c "{"; ".join(exports)}; {command}"'
```

## Health Check Timing

The default health check timeout (60s) is often too short for:
- Apps that run database migrations on first start (Gitea, HedgeDoc)
- Apps that compile assets on first run (Next.js, SonarQube)
- Apps that download additional resources on start

Set `start-timeout` in hop3.toml for these apps:

```toml
[run]
start-timeout = 180
```

## Debugging Daemon Failures

Daemon stderr is captured in `/home/hop3/apps/<app>/log/web.1.log`. When the health check times out, the last 20 lines of this log are shown in the deploy output.

To get more context:

```bash
# Full daemon log
cat /home/hop3/apps/<app>/log/web.1.log

# uWSGI emperor log
journalctl -u uwsgi-emperor -n 100

# Check if process is running
pgrep -f "apps/<app>"

# Check uWSGI config
cat /home/hop3/uwsgi-enabled/<app>_web.1.ini
```

## Runtime Binary Dependencies via `[build].packages`

Apps whose runtime needs a binary outside the language ecosystem (Owncast needs `ffmpeg` for transcoding; some PDF apps need `libreoffice` or `tesseract`) can declare the dependency in `hop3.toml`:

```toml
[build]
builder = "local"
packages = ["ffmpeg"]
```

Hop3 installs the declared packages with apt at build time. Without this, the native deploy starts the binary and then the binary crashes at startup with a message like "Unable to locate ffmpeg" — which surfaces only after the 60-second health-check timeout.

Two caveats:

- `[build].packages` runs apt-install and therefore requires the Hop3 server to be on a Debian-family host. On other distributions, the operator needs to install the dependency manually.
- Distinguish **runtime** binary dependencies (ffmpeg, libreoffice — needed when the app runs) from **build** binary dependencies (build-essential, pkg-config — needed only during build). Today `packages = [...]` covers both; a future split between `[build.packages]` and `[run.packages]` is a candidate refinement.

## SSH Key Collisions with Apps That Manage `authorized_keys`

Some self-hosted apps want full ownership of the hop3 user's `~/.ssh/authorized_keys`. Forgejo 14.x is the notable case: it refuses to start if the file contains any SSH public key it did not itself create, and exits with `An unexpected ssh public key was discovered. Forgejo will shutdown to require this to be fixed.` The keys Hop3 itself writes for CLI access get flagged as "unexpected".

**Fix:** in the app's config, disable the app's own SSH server:

```ini
[server]
DISABLE_SSH = true
```

For Forgejo / Gitea this lands in `custom/conf/app.ini`. The setting turns off the app's git-over-SSH server, not Hop3's CLI-over-SSH tunnel — those are different SSH services on different processes. The app still accepts git pushes over HTTPS; HTTPS is what most operators use anyway.

Apps that silently *scan* `~/.ssh/authorized_keys` rather than refuse to start are worse: the behaviour shows up as a logic bug later. If an app is strict about authorized_keys, the operator should know up front, so this deserves a note in the app's scaffolded `hop3.toml` or per-app README.
