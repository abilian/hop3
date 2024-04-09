# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS

from __future__ import annotations

from pathlib import Path

from hop3.core.env import Env
from hop3.system.constants import APP_ROOT, ENV_ROOT
from hop3.util import shell


class Builder:
    app_name: str

    # Class attitutes
    requirements: list[str]
    name: str

    def __init__(self, app_name: str) -> None:
        self.app_name = app_name

    def accept(self) -> bool:
        raise NotImplementedError

    def build(self) -> None:
        raise NotImplementedError

    @property
    def app_path(self) -> Path:
        return Path(APP_ROOT, self.app_name)

    @property
    def virtual_env(self) -> Path:
        return Path(ENV_ROOT, self.app_name)

    @property
    def env_file(self) -> Path:
        return Path(APP_ROOT, self.app_name, "ENV")

    def shell(self, command: str, cwd: str | Path = "", **kwargs) -> None:
        if not cwd:
            cwd = str(self.app_path)
        shell(command, cwd=str(cwd), **kwargs)

    def get_env(self) -> Env:
        env = Env()
        env.parse_settings(self.env_file)
        return env
