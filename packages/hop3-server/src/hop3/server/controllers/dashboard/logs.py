# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Dashboard logs controller - log viewing and streaming."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import anyio
from litestar import Controller, get

# Runtime import (not TYPE_CHECKING): Litestar resolves the FromPath path-param
# annotation at route registration via get_type_hints, so it must exist at runtime.
from litestar.params import FromPath  # ruff:ignore[typing-only-third-party-import]
from litestar.response import Redirect, Response, Stream, Template

from hop3.core.roles import Role
from hop3.server.guards import RoleGuard
from hop3.server.lib.database import get_session

from .helpers import get_app_or_none

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


async def _create_log_generator(log_dir: Path) -> AsyncIterator[str]:
    """
    Stream, as SSE events, the lines the app's workers append to ``log_dir``.

    The page already shows the recent history, so the stream starts at the end
    of every file present on connect; a file that appears later (a new worker)
    is read from its start. A ``==> worker <==`` line marks each change of
    source, as in the page's history.
    """
    try:
        offsets = await anyio.to_thread.run_sync(_end_offsets, log_dir)
        source = ""
        while True:
            chunks, offsets = await anyio.to_thread.run_sync(
                _read_appended, log_dir, offsets
            )
            for worker, lines in chunks:
                if worker != source:
                    source = worker
                    yield _sse(f"==> {worker} <==")
                for line in lines:
                    yield _sse(line)
            await asyncio.sleep(1)
    except Exception as e:
        yield f"event: error\ndata: Error streaming logs: {e}\n\n"


def _sse(line: str) -> str:
    return f"data: {line}\n\n"


def _end_offsets(log_dir: Path) -> dict[Path, int]:
    """Current size of each log file, i.e. where tailing starts."""
    return {path: path.stat().st_size for path in sorted(log_dir.glob("*.log"))}


def _read_appended(
    log_dir: Path, offsets: dict[Path, int]
) -> tuple[list[tuple[str, list[str]]], dict[Path, int]]:
    """
    Read the complete lines written to each log file since ``offsets``.

    Returns ``(worker, lines)`` pairs and the new offsets. A line still being
    written (no newline yet) is left for the next read; a file smaller than
    its offset was truncated or rotated and is read again from its start.
    """
    chunks = []
    new_offsets = {}
    for path in sorted(log_dir.glob("*.log")):
        start = offsets.get(path, 0)
        size = path.stat().st_size
        if size < start:
            start = 0
        with path.open("rb") as f:
            f.seek(start)
            data = f.read(size - start)
        complete = data[: data.rfind(b"\n") + 1]
        new_offsets[path] = start + len(complete)
        lines = complete.decode("utf-8", errors="replace").splitlines()
        if lines:
            chunks.append((path.stem, lines))
    return chunks, new_offsets


class LogsController(Controller):
    """Controller for app log viewing routes."""

    path = "/dashboard/apps/{app_name:str}/logs"
    guards = [RoleGuard(Role.DEPLOYER)]  # ruff:ignore[mutable-class-default]

    @get("/", sync_to_thread=False)
    def app_logs(self, app_name: FromPath[str]) -> Template | Redirect:
        """Display application logs page."""
        with get_session() as db_session:
            app = get_app_or_none(db_session, app_name)

            if not app:
                return Redirect(path="/dashboard")

            logs = app.get_logs(lines=500)

            ctx = {
                "app_name": app.name,
                "logs": logs,
                "log_count": len(logs),
                "now": datetime.now(timezone.utc),
            }

        return Template(template_name="dashboard/logs.html", context=ctx)

    @get("/download", sync_to_thread=False)
    def app_logs_download(self, app_name: FromPath[str]) -> Response | Redirect:
        """Download application logs as a text file."""
        with get_session() as db_session:
            app = get_app_or_none(db_session, app_name)

            if not app:
                return Redirect(path="/dashboard")

            logs = app.get_logs(lines=10000)
            log_content = "\n".join(logs)

            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"{app_name}_logs_{timestamp}.txt"

            return Response(
                content=log_content,
                media_type="text/plain",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                },
            )

    @get("/stream")
    async def app_logs_stream(self, app_name: FromPath[str]) -> Stream | Response:
        """Stream application logs via Server-Sent Events (SSE)."""
        with get_session() as db_session:
            app = get_app_or_none(db_session, app_name)

            if not app:
                return Response(
                    content="App not found",
                    status_code=404,
                    media_type="text/plain",
                )

            log_dir = Path(app.log_path)

        return Stream(
            content=_create_log_generator(log_dir),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
