# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations


class ConfigService:
    def __init__(self, config: dict) -> None:
        """
        Initialize the class with configuration data.

        Input:
        - config (dict): Configuration settings to initialize the class.
        """
        self.config = config

    def get(self, key: str):
        """
        Retrieve the value associated with a given key from the configuration.

        Input:
            key (str): The key for which the value needs to be retrieved from the configuration.

        Returns:
            The value associated with the given key if it exists, or None if the key is not found.

        """
        return self.config.get(key)

    def set(self, key: str, value) -> None:
        """
        Add or update a configuration setting.

        Input:
        - key (str): The key for the configuration setting.
        - value: The value to be associated with the key.
        """
        self.config[key] = value  # Set the value in the configuration dictionary

    def get_all(self) -> dict:
        """
        Retrieve all configuration settings.

        Returns:
            dict: A dictionary containing all the configuration settings.
        """
        return self.config
