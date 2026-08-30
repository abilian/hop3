# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Progress reporting for the request body of a `hop3 deploy`.

A deploy uploads its whole source tree in one POST, so on a slow uplink the CLI
goes silent for a long time between "About to deploy" and the first line of
server output — a 19.6 MB archive takes ~70 s at 2 Mbit/s. Silence there is
indistinguishable from a hang, which is how a plain upload timeout got read as
a dead server.

The bar is driven by the body being *read* off the buffer, which runs slightly
ahead of the bytes the far end has actually taken: urllib3 reads a block then
writes it, the kernel socket buffer holds more, and over an SSH tunnel ssh's
channel window (2 MB by default) buffers more still. So the bar can reach 100%
a few seconds before the request completes. Reporting bytes genuinely
acknowledged would mean owning the transport instead of handing a body to
`requests`, which is not worth it for an indicator.
"""

from __future__ import annotations

import contextlib
import io
import sys
from typing import TYPE_CHECKING, Final

from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

# Under this, the upload is over before a bar would earn its space.
MIN_BODY_BYTES_FOR_PROGRESS: Final = 2 * 1024 * 1024


class ProgressBody(io.BytesIO):
    """
    A request body that reports how much of itself has been handed over.

    `requests` accepts any file-like object as `data=` and still sets a real
    Content-Length for it (it measures via seek), so this streams without
    falling back to chunked transfer encoding.
    """

    def __init__(self, data: bytes, advance: Callable[[int], None]) -> None:
        super().__init__(data)
        self._advance = advance

    def read(self, size: int | None = -1) -> bytes:
        chunk = super().read(size)
        self._advance(len(chunk))
        return chunk


@contextlib.contextmanager
def upload_body(data: bytes) -> Iterator[bytes | ProgressBody]:
    """
    Yield the POST body, wrapped in a progress bar when one is worth drawing.

    Falls back to the plain bytes for a small body or a non-tty stderr (CI logs,
    pipes), where an animated bar is noise rather than information.
    """
    if len(data) < MIN_BODY_BYTES_FOR_PROGRESS or not sys.stderr.isatty():
        yield data
        return

    progress = Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=Console(stderr=True),
    )
    with progress:
        task = progress.add_task("Uploading", total=len(data))
        yield ProgressBody(data, lambda n: progress.advance(task, n))
