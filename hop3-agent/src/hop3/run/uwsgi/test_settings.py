# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from .settings import UwsgiSettings


def test_settings():
    settings = UwsgiSettings()
    settings.add("module", "command")
    settings.add("threads", "4")
    settings += [
        ("plugin", "python3"),
    ]
    assert settings.values == [
        ("module", "command"),
        ("threads", "4"),
        ("plugin", "python3"),
    ]
