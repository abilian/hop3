# Copyright (c) 2024, Abilian SAS
from __future__ import annotations

from pathlib import Path

from hop3.config.config import Config


def test_1():
    config = Config()

    assert config.nginx_root == Path("/home/hop3/nginx")
