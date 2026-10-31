# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
The dashboard's live log stream tails the app's log directory.

Regression: ``App.log_path`` is a directory (one ``<worker>.log`` per worker),
and the stream opened it as a file. Every connection failed at once with
"Is a directory"; the page swallowed the error event and showed "Live" over a
stream that never delivered a line.
"""

from __future__ import annotations

import asyncio

import pytest

from hop3.server.controllers.dashboard import logs
from hop3.server.controllers.dashboard.logs import (
    _create_log_generator,
    _end_offsets,
    _read_appended,
)


def test_reads_only_what_was_appended(tmp_path):
    web = tmp_path / "web.1.log"
    web.write_text("old\n")
    offsets = _end_offsets(tmp_path)

    with web.open("a") as f:
        f.write("new one\nnew two\n")

    chunks, _ = _read_appended(tmp_path, offsets)
    assert chunks == [("web.1", ["new one", "new two"])]


def test_holds_back_a_line_still_being_written(tmp_path):
    web = tmp_path / "web.1.log"
    web.write_text("")
    offsets = _end_offsets(tmp_path)

    web.write_text("done\npart")
    chunks, offsets = _read_appended(tmp_path, offsets)
    assert chunks == [("web.1", ["done"])]

    with web.open("a") as f:
        f.write("ial\n")
    chunks, _ = _read_appended(tmp_path, offsets)
    assert chunks == [("web.1", ["partial"])]


def test_rereads_a_truncated_file_from_its_start(tmp_path):
    web = tmp_path / "web.1.log"
    web.write_text("a long line before rotation\n")
    offsets = _end_offsets(tmp_path)

    web.write_text("fresh\n")
    chunks, _ = _read_appended(tmp_path, offsets)
    assert chunks == [("web.1", ["fresh"])]


def test_reads_a_new_worker_file_from_its_start(tmp_path):
    offsets = _end_offsets(tmp_path)
    (tmp_path / "worker.1.log").write_text("first\n")

    chunks, _ = _read_appended(tmp_path, offsets)
    assert chunks == [("worker.1", ["first"])]


@pytest.mark.asyncio
async def test_stream_delivers_an_appended_line(tmp_path):
    web = tmp_path / "web.1.log"
    web.write_text("history the page already shows\n")
    stream = _create_log_generator(tmp_path)

    async def first_event() -> str:
        return await anext(stream)

    pending = asyncio.ensure_future(first_event())
    await asyncio.sleep(0.2)  # the stream records where the files end
    with web.open("a") as f:
        f.write("served /index\n")

    try:
        assert await asyncio.wait_for(pending, timeout=5) == "data: ==> web.1 <==\n\n"
        assert await asyncio.wait_for(anext(stream), timeout=5) == (
            "data: served /index\n\n"
        )
    finally:
        await stream.aclose()


def test_caps_a_large_new_file_at_its_tail(tmp_path, monkeypatch):
    monkeypatch.setattr(logs, "MAX_TAIL_BYTES", 16)
    offsets = _end_offsets(tmp_path)
    # 36 bytes; the last 16 start on the "9\n" ending the second line.
    (tmp_path / "web.1.log").write_text("0123456789\n" * 2 + "abcdefgh\n" + "tail\n")

    chunks, new_offsets = _read_appended(tmp_path, offsets)

    # The partial line opening the window is skipped with what precedes it.
    assert chunks == [
        (
            "web.1",
            [
                logs._skipped_marker(22),
                "abcdefgh",
                "tail",
            ],
        )
    ]
    assert new_offsets == {tmp_path / "web.1.log": 36}


def test_cap_keeps_a_line_that_starts_on_the_window_boundary(tmp_path, monkeypatch):
    monkeypatch.setattr(logs, "MAX_TAIL_BYTES", 5)
    web = tmp_path / "web.1.log"
    web.write_text("")
    offsets = _end_offsets(tmp_path)
    web.write_text("old\n" * 3 + "last\n")

    chunks, _ = _read_appended(tmp_path, offsets)

    assert chunks == [
        (
            "web.1",
            [
                logs._skipped_marker(12),
                "last",
            ],
        )
    ]
