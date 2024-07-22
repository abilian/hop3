# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from pathlib import Path

from hop3.builders.base import Builder
from hop3.system.constants import ENV_ROOT
from hop3.util import shell
from hop3.util.console import log


class GoBuilder(Builder):
    """Builds Go projects.

    Attributes
    ----------
        name (str): The name of the builder.
        requirements (list): A list of requirements needed for the builder.

    """

    name = "Go"
    requirements = ["go"]

    def accept(self) -> bool:
        """Check if the application has go dependencies or go source files.

        Returns
        -------
            bool: True if the application has dependencies or go files, False otherwise.

        """
        return (
            Path(self.app_path, "Godeps").exists()
            or len(list(self.app_path.glob("*.go"))) > 0
        )

    def build(self) -> None:
        """Build the object.

        This method triggers the build process.
        """
        self.build_go()

    def build_go(self) -> None:
        """Deploy a Go application."""
        go_path = Path(ENV_ROOT, self.app_name)

        if not go_path.exists():
            log(f"Creating GOPATH for '{self.app_name}'", level=5, fg="blue")
            go_path.mkdir(parents=True)
            # copy across a pre-built GOPATH to save provisioning time
            shell(f"cp -a $HOME/gopath {self.app_name}", cwd=ENV_ROOT)
