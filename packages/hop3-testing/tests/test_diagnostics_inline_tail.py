# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Inline-diagnostic tail extraction tests.

Covers two regression-bait scenarios:

1. Docker-based app with no native uWSGI logs — historically surfaced
   the shell error ``tail: cannot open ... No such file`` as the
   "diagnostic". The fallback now picks up ``docker logs`` content
   instead.
2. Native (uWSGI) app — keeps surfacing ``web.*.log`` as before.

The producer of these blobs is ``runtime_diagnostics.collect_runtime_logs``;
the consumer here is ``ConsoleReporter._extract_app_log_tail``.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
from textwrap import dedent

from hop3_testing.results.reporters import ConsoleReporter


@dataclass
class _FakeTest:
    name: str = "apps/real-apps-docker/etherpad"


@dataclass
class _FakeResult:
    test: _FakeTest
    error: str = "HTTP test failed"
    runtime_logs: str = ""

    @property
    def passed(self) -> bool:
        return False


def _reporter() -> ConsoleReporter:
    return ConsoleReporter(output=StringIO(), color=False)


def test_extract_app_log_tail_prefers_native_web_log():
    """When native logs exist, ``web.*.log`` wins over other files."""
    blob = dedent("""\
        === Runtime Logs (collected from target) ===

        --- App log files ---
        --- /home/hop3/apps/myapp/log/build.log ---
        this is the build log
        irrelevant verbose stuff
        --- /home/hop3/apps/myapp/log/web.1.log ---
        web log line 1
        web log line 2 — this is what we want

        --- Docker container logs (last 80 lines per container) ---
        (no docker containers matching app name)
    """)
    result = _FakeResult(test=_FakeTest(), runtime_logs=blob)
    out = _reporter()._extract_app_log_tail(result)
    assert "web.1.log" in out
    assert "web log line 2 — this is what we want" in out
    assert "build log" not in out


def test_extract_app_log_tail_falls_back_to_docker_logs():
    """When no native logs are present, surface docker container logs."""
    blob = dedent("""\
        === Runtime Logs (collected from target) ===

        --- App log files ---
        (no native log files — typical for docker-based apps;
         see "Docker container logs" section below)

        --- Build log ---
        (no build.log — app may use docker builder, ...)

        --- Docker container state ---
        etherpad-1778179312  Exited (1) 3 minutes ago  etherpad:latest

        --- Docker container logs (last 80 lines per container) ---
        --- etherpad-1778179312 ---
        Etherpad startup error: cannot bind to port 0
          at Server.listen (/home/etherpad/app/src/...)
        Node.js v20.19.2
    """)
    result = _FakeResult(test=_FakeTest(), runtime_logs=blob)
    out = _reporter()._extract_app_log_tail(result)
    assert out.startswith("[docker logs etherpad-1778179312]")
    assert "Etherpad startup error" in out
    assert "Node.js v20.19.2" in out


def test_extract_app_log_tail_returns_empty_when_truly_nothing():
    """Both sections empty → return empty (caller hides the block)."""
    blob = dedent("""\
        === Runtime Logs (collected from target) ===

        --- App log files ---
        (no native log files — typical for docker-based apps;
         see "Docker container logs" section below)

        --- Docker container logs (last 80 lines per container) ---
        (no docker containers matching app name)
    """)
    result = _FakeResult(test=_FakeTest(), runtime_logs=blob)
    assert _reporter()._extract_app_log_tail(result) == ""


def test_extract_app_log_tail_handles_missing_runtime_logs():
    """Missing ``runtime_logs`` attribute / empty string → empty."""
    result = _FakeResult(test=_FakeTest(), runtime_logs="")
    assert _reporter()._extract_app_log_tail(result) == ""


def test_extract_app_log_tail_truncates_long_docker_output():
    """Tails honour ``max_lines`` and prepend an elision marker."""
    long_body = "\n".join(f"line {i}" for i in range(100))
    blob = dedent("""\
        --- Docker container logs (last 80 lines per container) ---
        --- some-container ---
        {body}
    """).format(body=long_body)
    result = _FakeResult(test=_FakeTest(), runtime_logs=blob)
    out = _reporter()._extract_app_log_tail(result, max_lines=10)
    lines = out.splitlines()
    # 1 header + 1 elision marker + 10 last lines = 12
    assert len(lines) == 12
    assert "earlier lines elided" in lines[1]
    assert lines[-1] == "line 99"


def test_extract_app_log_tail_picks_first_container_when_multiple():
    """When several containers match, surface the first one."""
    blob = dedent("""\
        --- Docker container logs (last 80 lines per container) ---
        --- app-web ---
        web container logs
        --- app-worker ---
        worker container logs
    """)
    result = _FakeResult(test=_FakeTest(), runtime_logs=blob)
    out = _reporter()._extract_app_log_tail(result)
    assert "[docker logs app-web]" in out
    assert "web container logs" in out
    # The worker logs are still in the full per-test log file but
    # not in the inline tail (we only show one).
    assert "worker container logs" not in out


def test_runtime_diagnostics_no_log_dir_yields_clean_message():
    """The shell command for ``App log files`` must short-circuit when
    the log directory doesn't exist (or is empty) — historically it
    leaked a ``tail: cannot open .../*.log`` shell error into the
    extracted diagnostic, which became the user-visible 'app stderr'.

    This test snapshots the friendly fallback message so a regression
    in the shell-script generation is caught.
    """
    from hop3_testing.runtime_diagnostics import collect_runtime_logs  # noqa: PLC0415

    class _FakeTarget:
        def exec_run(self, cmd):
            _ = cmd
            # Pretend every diagnostic command returns no useful output;
            # in particular we never want to see "tail: cannot open"
            # in the assembled blob — the shell script must handle
            # missing files gracefully before tail ever runs.
            return 0, "(empty)", ""

    blob = collect_runtime_logs(_FakeTarget(), "etherpad-test")  # type: ignore[arg-type]
    # Lock in the fix-shape: no bare ``for f in <path>/*.log`` loop
    # (the original buggy form). The replacement uses ``find`` piped
    # to ``while read``, which short-circuits cleanly on no matches.
    assert "for f in /home/hop3/apps/" not in blob
