# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Dishka container creation (mirrors ``hop3.di.container``).

``LitestarProvider()`` is required so providers/handlers can access the
Litestar ``Request`` (playbook COMMON-GOTCHAS). Wire to the app with
``setup_dishka(container, app)`` in the ASGI factory.
"""

from __future__ import annotations

from dishka import AsyncContainer, make_async_container
from dishka.integrations.litestar import LitestarProvider

from hop3_testlab.di.providers import (
    ConfigProvider,
    DatabaseProvider,
    RepositoryProvider,
)


def create_async_container() -> AsyncContainer:
    """Build the Test Lab's async DI container for web requests."""
    return make_async_container(
        ConfigProvider(),
        DatabaseProvider(),
        RepositoryProvider(),
        LitestarProvider(),
    )
