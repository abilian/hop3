# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS

from __future__ import annotations

from pathlib import Path

from hop3.system.constants import ENV_ROOT
from hop3.util import shell
from hop3.util.console import log


def build_go(app_name: str) -> None:
    """Deploy a Go application"""
    go_path = Path(ENV_ROOT, app_name)

    if not go_path.exists():
        log(f"Creating GOPATH for '{app_name}'", level=5, fg="blue")
        go_path.mkdir(parents=True)
        # copy across a pre-built GOPATH to save provisioning time
        shell(f"cp -a $HOME/gopath {app_name}", cwd=ENV_ROOT)

    # return spawn_app(app_name, deltas)
