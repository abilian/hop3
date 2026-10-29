# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
No route handler blocks the event loop.

hop3-server runs one worker (server/cli/serve.py). A sync handler declared
`sync_to_thread=False` runs *on the event loop*, so a database query, a file
read or a subprocess in it freezes /rpc, sign-in and every SSE deploy stream
until it returns: opening a backup's page checksummed the whole archive there.

A sync handler must therefore run on a worker thread, unless it is listed
below as doing no I/O at all. Async handlers (every `@inject` one) cannot be
checked from the route map; they hand their blocking work to
`anyio.to_thread` by convention.
"""

from __future__ import annotations

import pytest

from hop3.server.asgi import create_app

FRAMEWORK_PREFIXES = ("/static", "/schema")

# Sync handlers allowed on the loop, because they touch no database, file,
# socket or process. Justify each one; "it is fast" is not a justification.
NO_IO_HANDLERS = frozenset({
    # Renders a form from a constant.
    ("GET", "/dashboard/apps/new"),
    # Redeems a code from an in-memory store and signs a cookie (HMAC).
    ("GET", "/_hop3/auth/callback"),
})


@pytest.fixture(scope="module")
def loop_bound_sync_handlers() -> set[tuple[str, str]]:
    """(method, path) of every sync handler that would run on the loop."""
    app = create_app()
    found = set()
    for route in app.routes:
        if route.path.startswith(FRAMEWORK_PREFIXES):
            continue
        for handler in getattr(route, "route_handlers", ()):
            if not handler.has_sync_callable or handler.sync_to_thread:
                continue
            found.update(
                (method, route.path)
                for method in handler.http_methods - {"OPTIONS", "HEAD"}
            )
    return found


def test_no_sync_handler_blocks_the_loop(loop_bound_sync_handlers) -> None:
    offenders = loop_bound_sync_handlers - NO_IO_HANDLERS
    assert not offenders, (
        f"Sync handlers declared sync_to_thread=False: {sorted(offenders)}. "
        "They run on the single event loop; any I/O there freezes every other "
        "request. Use sync_to_thread=True (or an async handler that offloads "
        "with anyio.to_thread), or add it to NO_IO_HANDLERS if it does no I/O."
    )


def test_the_allow_list_has_not_gone_stale(loop_bound_sync_handlers) -> None:
    departed = NO_IO_HANDLERS - loop_bound_sync_handlers
    assert not departed, f"NO_IO_HANDLERS names no such handler: {sorted(departed)}"
