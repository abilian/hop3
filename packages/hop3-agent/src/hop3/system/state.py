# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""State singleton object.

Store the state of the system.
"""

from __future__ import annotations

from hop3.system.constants import HOP3_ROOT
from hop3.util.settings import parse_settings


class State:
    def get_app_env(self, app_name) -> dict[str, str]:
        from hop3.core.app import App

        app = App(app_name)
        settings = app.virtualenv_path / "ENV"
        return parse_settings(settings)

    def get_global(self, key: str):
        settings = HOP3_ROOT / "GLOBAL"
        return parse_settings(settings).get(key)


state = State()
