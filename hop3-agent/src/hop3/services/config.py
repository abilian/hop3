# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only


class ConfigService:
    def __init__(self, config: dict):
        self.config = config

    def get(self, key: str):
        return self.config.get(key)

    def set(self, key: str, value):
        self.config[key] = value

    def get_all(self):
        return self.config
