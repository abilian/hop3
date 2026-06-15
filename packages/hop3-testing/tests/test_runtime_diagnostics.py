# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""The on-failure runtime-log collector is tailored, not speculative.

Regressions this pins (all seen on a real Nix app's failure bundle):
- docker sections shown for a native/Nix app (no containers) → noise.
- build-log section guessing "may use docker builder" for a Nix build.
- a missing nginx vhost surfaced as a raw `cat: … No such file` error.
"""

from __future__ import annotations

from hop3_testing.runtime_diagnostics import (
    _diagnostic_sections,
    _has_docker_container,
    collect_runtime_logs,
)


class _FakeTarget:
    """Minimal target: exec_run returns the same (code, out, err) every call."""

    def __init__(self, out: str = "") -> None:
        self._out = out

    def exec_run(self, _cmd: str):
        return (0, self._out, "")


def _by_title(has_docker: bool) -> dict[str, str]:
    return dict(_diagnostic_sections("myapp", has_docker_container=has_docker))


def test_no_docker_sections_for_native_app() -> None:
    titles = _by_title(has_docker=False)
    assert not any("Docker" in t for t in titles)
    # The console reporter parses this exact title — keep it stable.
    assert "App log files" in titles


def test_docker_sections_present_for_containerised_app() -> None:
    titles = _by_title(has_docker=True)
    assert "Docker container state" in titles
    assert "Docker container logs (last 80 lines per container)" in titles


def test_build_log_is_nix_aware_not_speculative() -> None:
    build = _by_title(has_docker=False)["Build log"]
    assert "may use docker builder" not in build  # old speculation is gone
    assert ".nix-result" in build  # Nix builds are recognised
    assert "nix log" in build  # …and their log is fetched the Nix way


def test_missing_nginx_is_a_finding_not_a_cat_error() -> None:
    nginx = _by_title(has_docker=False)["Nginx config"]
    assert "if [ -f" in nginx  # guarded — the raw cat error never leaks
    assert "2>&1 ||" not in nginx
    assert "no nginx vhost" in nginx  # actionable finding


def test_has_docker_container() -> None:
    assert _has_docker_container(_FakeTarget("myapp\n"), "myapp") is True
    assert _has_docker_container(_FakeTarget(""), "myapp") is False


def test_collect_runtime_logs_empty_without_target_or_app() -> None:
    assert collect_runtime_logs(None, "myapp") == ""
    assert collect_runtime_logs(_FakeTarget(), None) == ""


def test_collect_runtime_logs_native_has_no_docker_noise() -> None:
    # Container probe returns "" → native app → no docker sections in output.
    blob = collect_runtime_logs(_FakeTarget(""), "myapp")
    assert "=== Runtime Logs (collected from target) ===" in blob
    assert "Docker container" not in blob
