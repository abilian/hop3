# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
`hop3 run` hands back a stream and lets the job run.

Reported from production:

    hop3 --context prod run annuaire-cli maintenance weekly
    Error while executing command:
    HTTPConnectionPool(host='localhost', port=61455): Read timed out.
    (read timeout=300.0)

The job was fine. It takes more than five minutes, which is what a weekly
maintenance task does, and there is no reason to kill it — nor to show the
operator nothing until it ends.
"""

from __future__ import annotations

import json
import sys
import threading
import time

import pytest

from hop3.commands import misc
from hop3.commands.misc import run_command_streaming
from hop3.server.streaming import create_stream, get_stream


def wait_until_complete(stream, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if stream.complete:
            return
        time.sleep(0.02)
    pytest.fail("the command never finished")


def start(script: str, tmp_path, stdin_data: str | None = None):
    item = run_command_streaming(
        "testapp",
        [sys.executable, "-u", "-c", script],
        tmp_path,
        {"PATH": "/usr/bin:/bin"},
        stdin_data,
    )
    stream = get_stream(item["stream_id"])
    assert stream is not None
    return item, stream


class TestItReturnsBeforeTheJobFinishes:
    def test_the_response_is_a_stream_the_cli_can_connect_to(self, tmp_path) -> None:
        item, stream = start("print('hello')", tmp_path)
        assert item["t"] == "stream"
        wait_until_complete(stream)

    def test_the_call_does_not_block_on_a_slow_job(self, tmp_path) -> None:
        """A five-minute job must not hold the request open for five minutes."""
        started = time.monotonic()
        _item, stream = start("import time; time.sleep(1.5); print('done')", tmp_path)
        assert time.monotonic() - started < 0.5
        wait_until_complete(stream)

    def test_output_is_visible_while_the_job_runs(self, tmp_path) -> None:
        _item, stream = start(
            "import time; print('step 1'); time.sleep(1.0); print('step 2')", tmp_path
        )
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and len(stream.logs) < 2:
            time.sleep(0.02)
        assert any(entry.msg == "step 1" for entry in stream.logs)
        assert not stream.complete, "step 1 only arrived once the job ended"
        wait_until_complete(stream)

    def test_the_command_line_is_echoed_first(self, tmp_path) -> None:
        _item, stream = start("pass", tmp_path)
        wait_until_complete(stream)
        assert next(iter(stream.logs)).msg.startswith("$ ")


class TestTheOutcomeReachesTheOperator:
    def test_success_completes_the_stream(self, tmp_path) -> None:
        _item, stream = start("print('ok')", tmp_path)
        wait_until_complete(stream)
        assert stream.success is True

    def test_a_failure_says_so_with_its_exit_code(self, tmp_path) -> None:
        _item, stream = start("print('partial'); raise SystemExit(3)", tmp_path)
        wait_until_complete(stream)
        assert stream.success is False
        assert "exit code 3" in stream.error_message
        assert any(entry.msg == "partial" for entry in stream.logs)

    def test_a_missing_executable_is_reported_not_swallowed(self, tmp_path) -> None:
        item = run_command_streaming(
            "testapp", ["definitely-not-a-real-binary"], tmp_path, {}, None
        )
        stream = get_stream(item["stream_id"])
        wait_until_complete(stream)
        assert stream.success is False
        assert "not found" in stream.error_message

    def test_stdin_data_still_reaches_the_command(self, tmp_path) -> None:
        _item, stream = start(
            "import sys; print(sys.stdin.read().strip())", tmp_path, "hunter2\n"
        )
        wait_until_complete(stream)
        assert any(entry.msg == "hunter2" for entry in stream.logs)

    def test_the_worker_thread_does_not_outlive_the_server(self, tmp_path) -> None:
        _item, stream = start("print('x')", tmp_path)
        wait_until_complete(stream)
        workers = [t for t in threading.enumerate() if t.name == "run-testapp"]
        assert all(t.daemon for t in workers)


class TestItDoesNotClaimToHaveDeployedAnything:
    """
    Deploys and one-off commands share the SSE path, and the client's default
    completion line is "App deployed successfully". Telling an operator their
    weekly maintenance job deployed is a claim about something that did not
    happen, so a job that is not a deploy says what it is.
    """

    def test_a_finished_command_says_it_completed(self, tmp_path) -> None:
        _item, stream = start("print('ok')", tmp_path)
        wait_until_complete(stream)
        assert stream.success_message == "Command completed"

    def test_the_completion_event_carries_it(self, tmp_path) -> None:
        _item, stream = start("print('ok')", tmp_path)
        wait_until_complete(stream)
        event = stream._completion_event()
        payload = json.loads(event.split("data: ", 1)[1])
        assert payload["success_message"] == "Command completed"

    def test_a_deploy_keeps_the_phrase_scripts_assert_on(self) -> None:
        deploy = create_stream("some-app")
        deploy.finish(success=True)
        assert deploy.success_message == ""


class TestTheStreamAlwaysEnds:
    """
    An exception escaping the worker thread is swallowed by `threading`, and
    the client is left waiting on a stream that never completes — the CLI
    hangs with no output and no error. Every exit path finishes the stream.
    """

    def test_an_unexpected_error_still_completes_the_stream(
        self, tmp_path, monkeypatch
    ) -> None:
        def explode(*_args, **_kwargs):
            msg = "disk went away"
            raise OSError(msg)

        monkeypatch.setattr(misc, "stream_command", explode)
        item = misc.run_command_streaming("testapp", ["true"], tmp_path, {}, None)
        stream = get_stream(item["stream_id"])
        wait_until_complete(stream)
        assert stream.success is False
        assert "disk went away" in stream.error_message
