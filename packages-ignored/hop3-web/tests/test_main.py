# Copyright (c) 2023-2025, Abilian SAS
from __future__ import annotations

from hop3_web.web.main import create_app

from .conftest import TestConfig


def test_create_app() -> None:
    config = TestConfig()
    app = create_app(config)
    assert app
