# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The request body must not be bounded by the handshake timeout.

urllib3 keeps the socket at the connect timeout while writing the body, so a
flat connect bound silently caps how big a `hop3 deploy` can be: a 19.6 MB
archive on a 2 Mbit/s uplink needs ~70 s and died at the 30 s bound, reported
as "Could not connect ... Is it running?" against a live server.
"""

from __future__ import annotations

import pytest
from hop3_cli.rpc.client import (
    _RPC_CONNECT_TIMEOUT_SECONDS,
    upload_timeout_seconds,
)

MB = 1024 * 1024


def test_empty_body_keeps_the_handshake_bound() -> None:
    assert upload_timeout_seconds(0) == _RPC_CONNECT_TIMEOUT_SECONDS


def test_the_deploy_that_failed_now_fits() -> None:
    # 19.6 MB measured at 0.28 MB/s -> 69 s of sendall.
    assert upload_timeout_seconds(int(19.6 * MB)) > 69.0


@pytest.mark.parametrize("size_mb", [50, 100, 200])
def test_allowance_grows_with_the_archive(size_mb: int) -> None:
    """A bigger archive gets more time — no cap for a larger one to outgrow."""
    assert upload_timeout_seconds(size_mb * MB) > upload_timeout_seconds(MB)
