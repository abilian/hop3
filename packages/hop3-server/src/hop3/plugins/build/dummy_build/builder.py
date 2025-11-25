# Copyright (c) 2025, Abilian SAS
from __future__ import annotations

from hop3.core.hooks import hop3_hook_impl
from hop3.core.protocols import BuildArtifact, Builder, DeploymentContext


class DummyBuilder(Builder):
    name = "dummy"

    def __init__(self, context: DeploymentContext):
        self.context = context

    def accept(self) -> bool:
        """Only accept if explicitly requested via .dummy-build marker file."""
        marker_file = self.context.source_path / ".dummy-build"
        return marker_file.exists()

    def build(self) -> BuildArtifact:
        """Doesn't do anything and return a dummy artifact."""
        return BuildArtifact(kind="dummy-artifact", location="/tmp")


class DummyPlugin:
    @hop3_hook_impl
    def get_build_strategies(self) -> list[type[Builder]]:
        return [DummyBuilder]
