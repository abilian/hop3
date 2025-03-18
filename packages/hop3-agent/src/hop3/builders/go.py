# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Builder for Go projects."""

from __future__ import annotations

from ._base import Builder


class GoBuilder(Builder):
    """Builds Go projects.

    This is responsible for building Go projects by checking for Go
    dependencies or source files and then executing the necessary build
    commands.
    """

    name = "Go"
    requirements = ["go"]  # noqa: RUF012

    def accept(self) -> bool:
        """Check if the application has go dependencies or go source files."""
        # Check if "Godeps" directory exists or if there are any .go files
        return (self.src_path / "Godeps").exists() or len(
            list(self.src_path.glob("*.go"))
        ) > 0

    def build(self) -> None:
        """Build the Go application."""
        # This method would contain the implementation details
        # to compile and build a Go project
        # TODO: implement
