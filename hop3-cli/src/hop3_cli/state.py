import dataclasses
import json
import os

from pathlib import Path
from typing import ClassVar

import toml
from platformdirs import user_config_dir, user_state_dir

PREFIX = "HOP3_"
APP_NAME = "hop3-cli"
APP_AUTHOR = "Abilian SAS"

_marker = object()


@dataclasses.dataclass(frozen=True)
class State:
    state_file: Path
    data: dict = dataclasses.field(default_factory=dict)

    def load_state(self):
        if not self.state_file.exists():
            return

        with self.state_file.open() as f:
            data = json.load(f)
            self.data.update(data)

    def get(self, key, default=_marker):
        if key in self.data:
            return self.data[key]

        if default is not _marker:
            return default

        raise KeyError(key)

    def set(self, key, value):
        self.data[key] = value

    def save_state(self):
        # TODO: lock or use atomic operation
        with self.state_file.open("w") as f:
            json.dump(self.data, f)


def get_state(state_file: Path | str | None = None) -> State:
    if state_file is None:
        state_dir = user_state_dir(APP_NAME, APP_AUTHOR)
        state_path = Path(state_dir) / "state.json"
    else:
        state_path = Path(state_file)
    state = State(state_path)
    state.load_state()
    return state
