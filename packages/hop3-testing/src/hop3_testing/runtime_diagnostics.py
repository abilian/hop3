# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Runtime diagnostic collection for failed tests.

Runs a set of shell commands on the target after a test fails (but
BEFORE cleanup destroys the app/container) so the per-app log file
contains everything a developer needs to diagnose the failure
without SSH'ing in.

Keep this module small and stable — every test failure calls into
it, so the cost of bad commands here shows up in test-suite time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hop3_testing.targets.base import DeploymentTarget


def collect_runtime_logs(
    target: DeploymentTarget | None,
    app_name: str | None,
) -> str:
    """Collect post-failure diagnostic output from the target.

    Args:
        target: The deployment target (remote or docker).
        app_name: The deployed app name (with timestamp suffix).

    Returns:
        A single string with labelled sections — empty string if
        either ``target`` or ``app_name`` is missing.
    """
    if target is None or not app_name:
        return ""

    # SH note: when a glob (``*.log``) doesn't match anything, POSIX sh
    # leaves the pattern literal — so a naive ``for f in <dir>/*.log``
    # iterates once with ``f`` set to the un-expanded glob and ``tail``
    # then errors with "cannot open ... No such file or directory".
    # That error then becomes the "diagnostic" we surface to the user,
    # which is worse than useless. The ``find ... | while read`` form
    # below short-circuits cleanly when there are no matches and emits
    # a helpful one-liner pointing at the docker logs section.
    sections: list[tuple[str, str]] = [
        (
            "App directory layout",
            f"ls -la /home/hop3/apps/{app_name}/ 2>&1 | head -30",
        ),
        (
            "App log files",
            (
                f"if [ -d /home/hop3/apps/{app_name}/log ]; then "
                f"  files=$(find /home/hop3/apps/{app_name}/log -maxdepth 1 "
                "    -type f -name '*.log' 2>/dev/null); "
                '  if [ -n "$files" ]; then '
                '    printf "%s\\n" "$files" | while IFS= read -r f; do '
                '      [ -n "$f" ] || continue; '
                '      echo "--- $f ---"; '
                '      tail -80 "$f" 2>&1; '
                "    done; "
                "  else "
                "    echo '(no native log files — typical for docker-based apps;'"
                "    echo ' see \"Docker container logs\" section below)'; "
                "  fi; "
                "else "
                f"  echo '(no log directory at /home/hop3/apps/{app_name}/log/)'; "
                "fi"
            ),
        ),
        (
            "Build log",
            (
                f"if [ -f /home/hop3/apps/{app_name}/log/build.log ]; then "
                f"  tail -80 /home/hop3/apps/{app_name}/log/build.log 2>&1; "
                "else "
                "  echo '(no build.log — app may use docker builder, "
                "which logs to stdout during deploy)'; "
                "fi"
            ),
        ),
        (
            "Nginx config",
            (f"cat /home/hop3/nginx/{app_name}.conf 2>&1 || echo '(no nginx config)'"),
        ),
        (
            "uWSGI config",
            (
                f"cat /home/hop3/uwsgi-enabled/{app_name}*.ini 2>&1 "
                f"|| cat /home/hop3/uwsgi-available/{app_name}*.ini 2>&1 "
                "|| echo '(no uwsgi config — typical for docker-based apps)'"
            ),
        ),
        (
            "Docker container state",
            (
                "if command -v docker >/dev/null 2>&1; then "
                f"  state=$(docker ps -a --filter name={app_name} --format "
                "    '{{.Names}}  {{.Status}}  {{.Image}}' 2>&1); "
                '  if [ -n "$state" ]; then '
                '    echo "$state"; '
                "  else "
                "    echo '(no docker containers matching app name)'; "
                "  fi; "
                "else echo '(docker not installed)'; fi"
            ),
        ),
        (
            "Docker container logs (last 80 lines per container)",
            (
                "if command -v docker >/dev/null 2>&1; then "
                f"  containers=$(docker ps -a --filter name={app_name} "
                "    --format '{{.Names}}' 2>/dev/null); "
                '  if [ -n "$containers" ]; then '
                '    printf "%s\\n" "$containers" | while IFS= read -r c; do '
                '      [ -n "$c" ] || continue; '
                '      echo "--- $c ---"; '
                '      docker logs --tail 80 "$c" 2>&1 || true; '
                "    done; "
                "  else "
                "    echo '(no docker containers matching app name)'; "
                "  fi; "
                "else echo '(docker not installed)'; fi"
            ),
        ),
    ]

    out: list[str] = ["=== Runtime Logs (collected from target) ==="]
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
