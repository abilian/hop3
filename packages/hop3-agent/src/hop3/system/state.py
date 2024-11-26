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
    """State singleton object."""

    def get_app_env(self, app_name) -> dict[str, str]:
        """
        Retrieve environment settings for a given application.

        Input:
        - app_name: The name of the application for which to retrieve environment settings.

        Returns:
        - A dictionary containing key-value pairs of environment settings for the specified application.
        """
        from hop3.core.app import App

        app = App(app_name)
        settings = app.virtualenv_path / "ENV"
        return parse_settings(settings)

    def get_global(self, key: str):
        """
        Retrieve a global setting by key.

        Input:
        - key (str): The key for the setting to retrieve.

        Returns:
        - The value associated with the key in the global settings.

        Raises:
        - KeyError: If the key does not exist in the global settings.

        The function accesses a global settings file and retrieves the value
        associated with the provided key. It uses the `parse_settings` function
        to read and parse the settings file located at 'GLOBAL' within the
        HOP3_ROOT directory.

        NB: Not used. Will be removed in a future commit.
        """
        settings = HOP3_ROOT / "GLOBAL"
        return parse_settings(settings).get(key)


state = State()
