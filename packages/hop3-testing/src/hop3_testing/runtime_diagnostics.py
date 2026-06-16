# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Runtime diagnostic collection for failed tests.

Runs a set of shell commands on the target after a test fails (but BEFORE
cleanup destroys the app/container) so the per-app log file contains everything
a developer needs to diagnose the failure without SSH'ing in.

The collected sections are *tailored to the app*, not speculative:

- Docker sections are emitted only when a container for the app actually exists
  — a native/Nix app has none, so probing for them is pure noise.
- The build-log section knows a Nix build keeps its log in ``nix log <store
  path>`` (there is no per-app ``build.log``), instead of guessing "may use
  docker builder".
- A missing nginx vhost is reported as an actionable finding, not the raw
  ``cat: … No such file`` error the old ``cat … 2>&1 || echo`` form leaked.

Keep this module small and stable — every test failure calls into it, so the
cost of bad commands here shows up in test-suite time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hop3_testing.targets.base import DeploymentTarget

HOP3_APPS = "/home/hop3/apps"
HOP3_NGINX = "/home/hop3/nginx"
HOP3_UWSGI_ENABLED = "/home/hop3/uwsgi-enabled"
HOP3_UWSGI_AVAILABLE = "/home/hop3/uwsgi-available"


def _app_dir_exists(target: DeploymentTarget, app_name: str) -> bool:
    """Whether ``/home/hop3/apps/<app>`` exists on the target.

    When a deploy fails client-side (e.g. the upload is rejected before the
    server creates the app), this directory is absent. Probing it once lets the
    collector emit a single honest "app was never created" line instead of a
    cascade of redundant per-subdir errors ("ls: ... No such file", then "no log
    directory at .../log/", then "no per-app build log" — all saying the same
    thing). On a probe error, assume it exists: better a noisy bundle than a
    silently suppressed one.
    """
    cmd = f"[ -d {HOP3_APPS}/{app_name} ] && echo __APPDIR_EXISTS__ || true"
    try:
        _, out, _ = target.exec_run(cmd)
    except Exception:
        return True
    return "__APPDIR_EXISTS__" in (out or "")


def _has_docker_container(target: DeploymentTarget, app_name: str) -> bool:
    """Whether a docker container for this app exists on the target.

    Decides whether the docker sections are relevant at all: a native/Nix app
    has no containers, so probing for them only adds confusing "(no docker
    containers ...)" noise to a failure that has nothing to do with docker.
    """
    cmd = (
        "command -v docker >/dev/null 2>&1 && "
        f"docker ps -a --filter name={app_name} --format '{{{{.Names}}}}' "
        "2>/dev/null || true"
    )
    try:
        _, out, _ = target.exec_run(cmd)
    except Exception:
        return False
    return bool((out or "").strip())


def _diagnostic_sections(
    app_name: str, *, has_docker_container: bool
) -> list[tuple[str, str]]:
    """The (title, shell-command) pairs to collect for ``app_name``.

    A pure function of the app name and whether it is containerised, so the
    section set is unit-testable without a target. Titles are stable — the
    console reporter keys off "App log files" and "Docker container logs …".
    """
    app_dir = f"{HOP3_APPS}/{app_name}"

    sections: list[tuple[str, str]] = [
        (
            "App directory layout",
            f"ls -la {app_dir}/ 2>&1 | head -30",
        ),
        (
            "App log files",
            # `find | while read` short-circuits cleanly when there are no
            # matches; a naive `for f in <dir>/*.log` would iterate once with the
            # un-expanded glob and make `tail` error "No such file".
            (
                f"if [ -d {app_dir}/log ]; then "
                f"  files=$(find {app_dir}/log -maxdepth 1 -type f -name '*.log' "
                "    2>/dev/null); "
                '  if [ -n "$files" ]; then '
                '    printf "%s\\n" "$files" | while IFS= read -r f; do '
                '      [ -n "$f" ] || continue; '
                '      echo "--- $f ---"; '
                '      tail -80 "$f" 2>&1; '
                "    done; "
                "  else "
                "    echo '(no per-app .log files yet — the app may not have started)'; "
                "  fi; "
                "else "
                f"  echo '(no log directory at {app_dir}/log/)'; "
                "fi"
            ),
        ),
        (
            "Build log",
            # Nix keeps build logs in the store, not a per-app build.log — fetch
            # them with `nix log` instead of guessing about a docker builder.
            (
                f"if [ -f {app_dir}/log/build.log ]; then "
                f"  tail -80 {app_dir}/log/build.log 2>&1; "
                f"elif [ -L {app_dir}/.nix-result ]; then "
                "    echo '(Nix build — no per-app build.log; showing nix log for "
                "the built store path)'; "
                f'    nix log "$(readlink -f {app_dir}/.nix-result)" 2>&1 '
                "      | tail -80 || echo '(nix log unavailable)'; "
                "else "
                "  echo '(no per-app build log — the build output is in the deploy "
                "log shown above.)'; "
                "fi"
            ),
        ),
        (
            "Nginx config",
            # `if [ -f ]` so a missing vhost is an actionable finding, not the
            # raw `cat: … No such file` error the old form leaked.
            (
                f"if [ -f {HOP3_NGINX}/{app_name}.conf ]; then "
                f"  cat {HOP3_NGINX}/{app_name}.conf; "
                "else "
                f"  echo '(no nginx vhost for {app_name} — the app is not exposed "
                "via the reverse proxy.)'; "
                "  echo '(A vhost is created once HOST_NAME is set and the app is "
                "(re)deployed; if the app should be HTTP-reachable, this is a likely "
                "cause of the failure.)'; "
                "fi"
            ),
        ),
        (
            "uWSGI config",
            (
                f"if ls {HOP3_UWSGI_ENABLED}/{app_name}*.ini >/dev/null 2>&1; then "
                f"  cat {HOP3_UWSGI_ENABLED}/{app_name}*.ini; "
                f"elif ls {HOP3_UWSGI_AVAILABLE}/{app_name}*.ini >/dev/null 2>&1; then "
                f"  cat {HOP3_UWSGI_AVAILABLE}/{app_name}*.ini; "
                "else "
                f"  echo '(no uWSGI config for {app_name})'; "
                "fi"
            ),
        ),
    ]

    # Docker sections only when the app actually has a container — otherwise
    # they are pure noise on a native/Nix failure.
    if has_docker_container:
        sections += [
            (
                "Docker container state",
                (
                    f"docker ps -a --filter name={app_name} "
                    "--format '{{.Names}}  {{.Status}}  {{.Image}}' 2>&1"
                ),
            ),
            (
                "Docker container logs (last 80 lines per container)",
                (
                    f"docker ps -a --filter name={app_name} "
                    "--format '{{.Names}}' 2>/dev/null "
                    "| while IFS= read -r c; do "
                    '  [ -n "$c" ] || continue; '
                    '  echo "--- $c ---"; '
                    '  docker logs --tail 80 "$c" 2>&1 || true; '
                    "done"
                ),
            ),
        ]

    return sections


def collect_runtime_logs(
    target: DeploymentTarget | None,
    app_name: str | None,
) -> str:
    """Collect post-failure diagnostic output from the target.

    Args:
        target: The deployment target (remote or docker).
        app_name: The deployed app name (with timestamp suffix).

    Returns:
        A single string with labelled sections — empty string if either
        ``target`` or ``app_name`` is missing.
    """
    if target is None or not app_name:
        return ""

    header = "=== Runtime Logs (collected from target) ==="

    # If the app dir is absent the deploy never reached app creation. Say so once
    # — every per-app section below would otherwise just restate "not found".
    if not _app_dir_exists(target, app_name):
        return (
            f"{header}\n\n"
            f"--- App directory ---\n"
            f"(no app directory at {HOP3_APPS}/{app_name} — the app was never "
            f"created on the server. The deploy failed before or during upload, "
            f"so there are no per-app logs, nginx/uWSGI configs, or containers to "
            f"show. See the deploy log above for the actual error.)\n"
        )

    has_docker = _has_docker_container(target, app_name)
    sections = _diagnostic_sections(app_name, has_docker_container=has_docker)

    out: list[str] = [header]
    for title, cmd in sections:
        out.append("")
        out.append(f"--- {title} ---")
        try:
            _, stdout, _ = target.exec_run(cmd)
            body = (stdout or "").rstrip()
            out.append(body or "(empty)")
        except Exception as exc:
            out.append(f"(failed to collect: {exc})")
    out.append("")
    return "\n".join(out)
