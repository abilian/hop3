# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from ._base import Builder


class GoBuilder(Builder):
    """Builds Go projects."""

    name = "Go"
    requirements = ["go"]  # noqa: RUF012

    def accept(self) -> bool:
        """Check if the application has go dependencies or go source files."""
        return (self.src_path / "Godeps").exists() or len(
            list(self.src_path.glob("*.go"))
        ) > 0

    def build(self) -> None:
        """Build the Go application."""
        # TODO: implement
