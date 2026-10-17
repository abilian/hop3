# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
The migrations the server runs in-process leave its logging alone.

Alembic's env.py called `fileConfig`, whose default disables every logger
created before it: once the server had migrated its database, the catalog
loader's report of the apps it excluded, and every other `hop3.*` logger
imported by then, went nowhere.
"""

from __future__ import annotations

import logging

from hop3.config import HopConfig
from hop3.orm import get_session_factory, reset_session_factory_cache


def test_migrating_keeps_existing_loggers_enabled(tmp_path, monkeypatch):
    logger = logging.getLogger("hop3.test.created-before-migrations")
    monkeypatch.setenv("HOP3_DATABASE_URI", f"sqlite:///{tmp_path}/test.db")
    HopConfig.reset_instance()
    reset_session_factory_cache()
    HopConfig.set_instance(HopConfig(hop3_root=tmp_path))
    try:
        get_session_factory()().close()
    finally:
        HopConfig.reset_instance()
        reset_session_factory_cache()

    assert not logger.disabled
