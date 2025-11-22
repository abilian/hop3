# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Test utilities for dependency injection."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from dishka import make_container

from hop3.di.providers import ConfigProvider, HopServicesProvider

if TYPE_CHECKING:
    from dishka import Container


@pytest.fixture
def di_container() -> Container:
    """Create a DI container for testing.

    This fixture provides a fresh Dishka container for each test,
    ensuring test isolation.

    Yields:
        Container: A fresh Dishka container with all providers registered

    Example:
        def test_my_service(di_container):
            service = di_container.get(MyService)
            assert service is not None
    """
    container = make_container(
        ConfigProvider(),
        HopServicesProvider(),
    )

    yield container

    container.close()
