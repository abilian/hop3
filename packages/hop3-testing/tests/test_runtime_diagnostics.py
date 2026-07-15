# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""The on-failure runtime-log collector is tailored, not speculative.

Regressions this pins (all seen on a real Nix app's failure bundle):
- docker sections shown for a native/Nix app (no containers) → noise.
- build-log section guessing "may use docker builder" for a Nix build.
- a missing nginx vhost surfaced as a raw `cat: … No such file` error.
- a deploy that failed before app creation leaking a cascade of redundant
  per-subdir "No such file" errors instead of one accurate finding.
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


class _PresentAppTarget:
    """Target where the app dir exists but has no docker container.

    The fixed-output ``_FakeTarget`` can't model this: the app-dir probe and the
    docker probe need different answers. This one says the app dir exists and
    everything else is empty.
    """

    def exec_run(self, cmd):
        if "__APPDIR_EXISTS__" in cmd:
            return (0, "__APPDIR_EXISTS__\n", "")
        return (0, "", "")


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


def test_build_log_fallback_points_at_deploy_log_not_a_cli_command() -> None:
    # The testlab already captures the deploy log; telling the reader to run
    # `hop3 app build-logs` is useless noise (and impossible if the app dir is
    # gone). Point at what's already in the report instead.
    build = _by_title(has_docker=False)["Build log"]
    assert "build-logs" not in build
    assert "deploy log shown above" in build


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
    # App dir exists, container probe returns "" → native app → sections present,
    # no docker noise.
    blob = collect_runtime_logs(_PresentAppTarget(), "myapp")
    assert "=== Runtime Logs (collected from target) ===" in blob
    assert "--- App log files ---" in blob  # real per-app sections ran
    assert "Docker container" not in blob


def test_collect_runtime_logs_collapses_missing_app_dir() -> None:
    # Deploy failed before app creation → app dir absent. One accurate finding,
    # not a cascade of redundant per-subdir errors.
    blob = collect_runtime_logs(_FakeTarget(""), "myapp")
    assert "=== Runtime Logs (collected from target) ===" in blob
    assert "the app was never created on the server" in blob
    # The redundant per-subdir probe sections are skipped entirely.
    assert "no log directory" not in blob
    assert "--- App log files ---" not in blob
    assert "--- uWSGI config ---" not in blob
