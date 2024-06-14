# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

"""State singleton object.

Store the state of the system.
"""

from __future__ import annotations

from pathlib import Path

from hop3.system.constants import ENV_ROOT, HOP3_ROOT
from hop3.util.settings import parse_settings


class State:
    def get_app_env(self, app_name) -> dict[str, str]:
        virtualenv_path = Path(ENV_ROOT, app_name)
        settings = Path(virtualenv_path, "ENV")
        return parse_settings(settings)

    def get_global(self, key: str):
        settings = Path(HOP3_ROOT, "GLOBAL")
        return parse_settings(settings).get(key)


state = State()
