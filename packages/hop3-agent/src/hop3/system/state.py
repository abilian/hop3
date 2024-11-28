# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""State singleton object.

Store the state of the system.
"""

from __future__ import annotations

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


state = State()
