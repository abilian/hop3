# Copyright (c) 2023-2024, Abilian SAS

from __future__ import annotations

from pathlib import Path

from .constants import APP_ROOT
from .model import App


def get_app(name: str) -> App:
    app = App(name)
    app.check_exists()
    return app


def list_apps() -> list[App]:
    app_root = Path(APP_ROOT)
    return [App(path.name) for path in sorted(app_root.iterdir())]
