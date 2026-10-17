# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
A deploy's transcript goes to a log; the console gets its steps.

The installer prints hundreds of lines on a successful deploy. The console
shows one line per step and the log's path. It shows the transcript's end only
when the deploy fails.
"""

from __future__ import annotations

from hop3_testing.targets import helpers
from hop3_testing.util.streaming import StreamingResult

_TRANSCRIPT = [
    "Hop3 Server Installer",
    "[1/11] Installing system dependencies...",
    "      ... Installing base packages (this may take a while)...",
    "      ✓ Installed 56 base packages",
    "[4] Installing Hop3",
]


def _deploy(monkeypatch, tmp_path, returncode: int) -> bool:
    def run(cmd, on_output, **_kw):
        for line in _TRANSCRIPT:
            on_output(line)
        return StreamingResult(
            returncode=returncode, stdout="\n".join(_TRANSCRIPT), stderr=""
        )

    monkeypatch.setattr(helpers, "run_streaming", run)
    monkeypatch.setattr(helpers, "DEFAULT_RUNS_DIR", tmp_path)
    ok, _ = helpers.run_hop3_deploy(docker=True, cwd=tmp_path)
    return ok


def test_a_successful_deploy_prints_its_steps_and_logs_the_rest(
    monkeypatch, tmp_path, capsys
):
    assert _deploy(monkeypatch, tmp_path, 0)

    out = capsys.readouterr().out
    assert "[1/11] Installing system dependencies" in out
    assert "[4] Installing Hop3" in out
    assert "base packages" not in out
    (log,) = tmp_path.glob("deploy-*.log")
    assert f"Full output: {log}" in out
    assert log.read_text().splitlines() == _TRANSCRIPT


def test_a_failed_deploy_prints_the_end_of_its_transcript(
    monkeypatch, tmp_path, capsys
):
    assert not _deploy(monkeypatch, tmp_path, 1)

    assert "✓ Installed 56 base packages" in capsys.readouterr().out
