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
from litestar.response import Redirect, Response, Stream, Template

from hop3.server.guards import auth_guard
from hop3.server.lib.database import get_session

from .helpers import get_app_or_none

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


async def _create_log_generator(log_path: Path) -> AsyncIterator[str]:
    """Create async generator for log streaming."""
    try:
        log_path_anyio = anyio.Path(log_path)

        async for event in _send_initial_logs(log_path_anyio):
            yield event

        file_size = await _get_file_size(log_path_anyio)

        while True:
            if await log_path_anyio.exists():
                current_size = (await log_path_anyio.stat()).st_size

                if current_size > file_size:
                    async for event in _send_new_log_lines(log_path, file_size):
                        yield event
                    file_size = current_size
                elif current_size < file_size:
                    file_size = 0

            await asyncio.sleep(1)

    except asyncio.CancelledError:
        pass
    except Exception as e:
        yield f"event: error\ndata: Error streaming logs: {e}\n\n"


async def _get_file_size(log_path_anyio: anyio.Path) -> int:
    """Get file size or 0 if file doesn't exist."""
    if await log_path_anyio.exists():
        return (await log_path_anyio.stat()).st_size
    return 0


async def _send_initial_logs(log_path_anyio: anyio.Path) -> AsyncIterator[str]:
    """Send initial log lines (last 50) as SSE events."""
    if not await log_path_anyio.exists():
        return

    content = await log_path_anyio.read_text()
    lines = content.splitlines(keepends=True)
    initial_lines = lines[-50:] if len(lines) > 50 else lines

    for line in initial_lines:
        if line:
            escaped_line = line.rstrip().replace("\n", "\\n")
            yield f"data: {escaped_line}\n\n"


async def _send_new_log_lines(log_path: Path, file_size: int) -> AsyncIterator[str]:
    """Read and send new log lines from file."""
    async with await anyio.open_file(log_path, "r") as f:
        await f.seek(file_size)
        new_content = await f.read()
        new_lines = new_content.splitlines(keepends=True)

        for line in new_lines:
            if line:
                escaped_line = line.rstrip().replace("\n", "\\n")
                yield f"data: {escaped_line}\n\n"


class LogsController(Controller):
    """Controller for app log viewing routes."""

    path = "/dashboard/apps/{app_name:str}/logs"
    guards = [auth_guard]  # noqa: RUF012

    @get("/", sync_to_thread=False)
    def app_logs(self, app_name: str) -> Template | Redirect:
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
    def app_logs_download(self, app_name: str) -> Response | Redirect:
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
    async def app_logs_stream(self, app_name: str) -> Stream | Response:
        """Stream application logs via Server-Sent Events (SSE)."""
        with get_session() as db_session:
            app = get_app_or_none(db_session, app_name)

            if not app:
                return Response(
                    content="App not found",
                    status_code=404,
                    media_type="text/plain",
                )

            log_path = Path(app.log_path)

        return Stream(
            content=_create_log_generator(log_path),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
