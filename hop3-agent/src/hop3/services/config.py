# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations


class ConfigService:
    def __init__(self, config: dict):
        self.config = config

    def get(self, key: str):
        return self.config.get(key)

    def set(self, key: str, value):
        self.config[key] = value

    def get_all(self):
        return self.config
