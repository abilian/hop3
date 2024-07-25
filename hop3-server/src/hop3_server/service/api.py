# Copyright (c) 2023-2024, Abilian SAS

from __future__ import annotations

from hop3_server.service.model import App


def list_apps() -> list[App]:
    return []


def get_app(app_name: str) -> App:
    return App(name=app_name)
