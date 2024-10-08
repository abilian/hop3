# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

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
