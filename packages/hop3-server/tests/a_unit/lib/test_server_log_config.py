# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The server log reads its settings from the live config, without a fallback.

It used to read them at import time under `except Exception: pass`, which
during bootstrap (hop3.config half-initialised) silently pinned the level to
INFO and the file to /home/hop3/log — and `hop3 system logs` read that pinned
path even on a server whose HOP3_ROOT was elsewhere.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hop3.config import HopConfig
from hop3.lib import logging as server_logging
from hop3.lib.config import Config

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def config_at(tmp_path: Path):
    previous = HopConfig.get_instance()
    HopConfig.set_instance(
        HopConfig(
            config_loader=Config(environ={"HOP3_LOG_LEVEL": "debug"}),
            hop3_root=tmp_path,
        )
    )
    yield tmp_path
    HopConfig.set_instance(previous)


def test_log_file_follows_the_configured_root(config_at: Path):
    assert server_logging.server_log_file() == config_at / "log" / "server.log"


def test_log_level_comes_from_config(config_at: Path):
    assert server_logging._get_log_level() == "DEBUG"
