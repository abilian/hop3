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

    sections: list[tuple[str, str]] = [
        (
            "App directory layout",
            f"ls -la /home/hop3/apps/{app_name}/ 2>&1 | head -30",
        ),
        (
            "App log files",
            (
                f"for f in /home/hop3/apps/{app_name}/log/*.log; do "
                'echo "--- $f ---"; tail -80 "$f" 2>&1; done'
            ),
        ),
        (
            "Build log",
            f"tail -80 /home/hop3/apps/{app_name}/log/build.log 2>&1 || true",
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
                "|| echo '(no uwsgi config)'"
            ),
        ),
        (
            "Docker container state",
            (
                "if command -v docker >/dev/null 2>&1; then "
                f"  docker ps -a --filter name={app_name} --format "
                "'{{.Names}}  {{.Status}}  {{.Image}}' 2>&1; "
                "else echo '(docker not installed)'; fi"
            ),
        ),
        (
            "Docker container logs (last 80 lines per container)",
            (
                "if command -v docker >/dev/null 2>&1; then "
                f"  for c in $(docker ps -a --filter name={app_name} "
                "--format '{{.Names}}' 2>&1); do "
                '    echo "--- $c ---"; '
                '    docker logs --tail 80 "$c" 2>&1 || true; '
                "  done; "
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
