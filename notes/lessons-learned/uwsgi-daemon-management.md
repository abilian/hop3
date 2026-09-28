# Lessons Learned: uWSGI Daemon Management

Hop3 manages application processes with uWSGI. This file records the non-obvious behaviors that cause deployment failures.

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

uWSGI's `chdir` directive sets the working directory for WSGI workers, but `attach-daemon` processes may not inherit it; they fork from the Emperor.

**Symptom:** Daemon starts, immediately fails with "No such file or directory" for a relative path.

**Fix:** Explicitly `cd` in the daemon's shell command:

```python
shell_cmd = f'sh -c "cd {app.src_path} && {exports}; {command}"'
settings.add("attach-daemon", shell_cmd)
```

## Throttle State Persists Across Redeploy

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

If a Python app has no `wsgi` worker configured (e.g., missing Procfile entry or hop3.toml `[run.workers]`), uWSGI starts in "Operational MODE: no-workers". The master process runs, logs look normal, but no WSGI workers exist. Health checks time out after 60s with no useful error.

**Fix 1:** Detect early: the deployer checks for WSGI workers before spawning:

```python
if not self.web_workers and self.artifact.kind in {"python", "buildpack", "virtualenv"}:
    log_diagnosis(...)  # name the missing worker and how to add one
```

**Fix 2:** Auto-discover WSGI modules: probe for `wsgi.py`, `app.py`, Django convention:

```python
if (src_path / "wsgi.py").exists():
    artifact.runtime.workers["wsgi"] = "wsgi:application"
```

Both fixes treat the missing WSGI worker as the condition to repair, since without it no request is ever answered.

## Environment Variable Propagation

uWSGI's `attach-daemon` processes do NOT inherit environment variables from the uWSGI config. The `env = KEY=VALUE` directives only apply to WSGI workers.

**Fix:** write the environment to a file only its owner can read, and have the daemon's shell source it by path:

```python
env_file.write_text("".join(f"export {k}={shlex.quote(v)}\n" for k, v in env.items()))  # mode 0600
shell_cmd = f'sh -c "cd {src} && . {env_file} && exec {command}"'
```

**Never put the environment on the command line.** The first fix exported every variable on the daemon's shell line. uWSGI keeps that `sh -c` alive as the daemon's parent, and `/proc/<pid>/cmdline` is readable by every local user, so `ps` showed every app's database password and secret key to `www-data`, `postgres` and every other app, for as long as the app ran. `/proc/<pid>/environ` is readable only by the process's owner, which is where secrets belong. Found by `scripts/emperor-caps-probe.py`, which plants a secret and reads it back as `nobody`.

## Health Check Timing

The default health check timeout (60s) is too short for apps that:
- Run database migrations on first start (Gitea, HedgeDoc)
- Compile assets on first run (Next.js, SonarQube)
- Download additional resources on start

Set `start-timeout` in hop3.toml for these apps, so the health check waits for a slow first start:

```toml
[run]
start-timeout = 180
```

## Debugging Daemon Failures

Daemon stdout and stderr are both captured in `/home/hop3/apps/<app>/log/web.1.log` (the shell command redirects with `>>file 2>&1`, since Node and PHP apps often write startup errors to stdout). When the health check times out, the deploy output shows the last 20 lines of this log.

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

## Host Binary Dependencies via `[build].packages` / `[run].packages`

Apps whose build or runtime needs a binary outside the language ecosystem declare it in `hop3.toml`. Build-only tools (`build-essential`, `pkg-config`) go in `[build].packages`; binaries the app needs while running (Owncast's `ffmpeg` for transcoding, `libreoffice` or `tesseract` for PDF apps) go in `[run].packages`:

```toml
[run]
packages = ["ffmpeg"]
```

These are declarations. Nothing is installed at deploy time. Instead, the installer unions `[build].packages` + `[run].packages` across the *whole* app catalogue at server-provisioning time and installs the result once: `hop3_installer.server_installer.baseline` computes the union, and `installer.py` runs the apt/dnf call. Adding a package to an app's `hop3.toml` therefore requires regenerating the committed baseline (`python -m hop3_installer.server_installer.baseline`); a CI check fails if `baselines.py` has drifted from the catalogue.

At build time the native builder only **probes** the declared packages against the local package DB (`dpkg` on Debian-family, `rpm` on Fedora-family). A missing package makes the builder log a Diagnosis naming it and the remedy, but the build continues (a soft gate: the probe must never create a false negative). Without the package the native deploy starts the binary, which crashes at startup with a message like "Unable to locate ffmpeg" and is surfaced only after the 60-second health-check timeout. The probe replaces that opaque timeout with a named cause.

Package names are canonical (Debian) and translated to the local OS family right before install (`package_aliases.py`), so both Debian and Fedora families are supported. A package with no known alias on the target family is the operator's to install manually.

## SSH Key Collisions with Apps That Manage `authorized_keys`

Some self-hosted apps want full ownership of the hop3 user's `~/.ssh/authorized_keys`. Forgejo 14.x refuses to start if the file contains any SSH public key it did not itself create, and exits with `An unexpected ssh public key was discovered. Forgejo will shutdown to require this to be fixed.` The keys Hop3 itself writes for CLI access get flagged as "unexpected".

**Fix:** in the app's config, disable the app's own SSH server:

```ini
[server]
DISABLE_SSH = true
```

For Forgejo / Gitea the setting lands in `custom/conf/app.ini`. It turns off the app's git-over-SSH server; Hop3's CLI-over-SSH tunnel is unaffected. The app still accepts git pushes over HTTPS, which is what most operators use anyway.

Some apps go further and silently *scan* `~/.ssh/authorized_keys`: the behaviour shows up as a logic bug later. An operator provisioning an app that is strict about `authorized_keys` should know up front, so the scaffolded `hop3.toml` or per-app README should say so.

## Strict Mode, and the Directive That Never Existed

The uWSGI configuration inherited from piku carried a `project` directive that uWSGI does not have. uWSGI ignores unknown directives by default, so it did nothing for months; `strict = true` turned it into an error on the next start. Run uWSGI strict. Treat any configuration a tool accepts silently as unverified.

## Two Quoting Layers on the attach-daemon Line

Every exported value used to sit inside `'…'`, which sat inside the double-quoted argument of `sh -c "…"`. Escaping the apostrophe handled the inner layer only; inside double quotes the shell still interprets `$`, a backtick, a backslash and a double quote. A JSON-valued setting lost its quotes outright, paperless-ngx received `[HTTP_X_FORWARDED_PROTO,https]` for `["HTTP_X_FORWARDED_PROTO","https"]` and crashed every worker on `json.loads`. A generated password containing `$` would have been mangled into an unreproducible credential. Moving the environment into a sourced file (above) removed the outer layer: each value is one `shlex.quote` in a file, and `test_env_quoting.py` round-trips the hard cases through a real `/bin/sh`. Leave the command itself alone: a start command is written to use `$PORT` and must keep expanding it.
