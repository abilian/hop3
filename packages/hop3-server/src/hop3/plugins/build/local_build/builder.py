# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""LocalBuilder - builds applications directly on host using language toolchains."""

from __future__ import annotations

from hop3.core.plugins import get_plugin_manager
from hop3.core.protocols import BuildArtifact, BuildContext, LanguageToolchain
from hop3.lib import log


class LocalBuilder:
    """Build directly on host using native language toolchains.

    This is the ONLY builder that uses LanguageToolchains.
    Other builders (Docker, Nix) encapsulate their build logic differently.

    This builder:
    1. Auto-detects which language toolchains apply (Python, Node, etc.)
    2. Invokes each toolchain to build the respective components
    3. Combines artifacts if multiple toolchains are used
    """

    name = "local"

    def __init__(self, context: BuildContext) -> None:
        """Initialize local builder with build context."""
        self.context = context
        self.rejection_reason = ""  # Set by accept() if rejected

    def accept(self) -> bool:
        """Accept if at least one language toolchain can handle this project."""
        src_path = self.context.source_path

        if not src_path.exists():
            self.rejection_reason = f"source path does not exist: {src_path}"
            return False

        # Discover applicable toolchains
        toolchains = self._discover_toolchains(self.context)

        if toolchains:
            names = [getattr(tc, "name", tc.__name__) for tc in toolchains]
            log(f"Detected toolchains: {names}", level=2, fg="cyan")
        else:
            self.rejection_reason = (
                "no language toolchain detected "
                "(checked for package.json, requirements.txt, Cargo.toml, etc.)"
            )

        return len(toolchains) > 0

    def build(self) -> BuildArtifact:
        """Build using local toolchains."""
        # 1. Discover applicable toolchains
        toolchains = self._discover_toolchains(self.context)

        if not toolchains:
            msg = "No language toolchain detected for this project"
            raise RuntimeError(msg)

        # Log detected toolchains
        toolchain_names = [getattr(tc, "name", tc.__name__) for tc in toolchains]
        log(f"Detected toolchains: {', '.join(toolchain_names)}", level=2, fg="cyan")

        # 2. Build with each toolchain (supports multi-language apps)
        artifacts = []
        for toolchain_class in toolchains:
            toolchain_name = getattr(toolchain_class, "name", toolchain_class.__name__)
            log(f"Building with {toolchain_name} toolchain...", level=2, fg="blue")
            toolchain = toolchain_class(self.context)
            artifact = toolchain.build()
            artifacts.append(artifact)

        # 3. Single toolchain case
        if len(artifacts) == 1:
            return artifacts[0]

        # 4. Multi-toolchain case (e.g., Python + Node)
        return self._combine_artifacts(artifacts)

    def _discover_toolchains(
        self, context: BuildContext
    ) -> list[type[LanguageToolchain]]:
        """Auto-detect which toolchains apply to this project.

        Example: A Python backend + Node frontend would return both
        PythonToolchain and NodeToolchain.
        """
        # Get all available language toolchains from plugins
        pm = get_plugin_manager()
        toolchain_classes_list = pm.hook.get_language_toolchains()

        # Flatten the list of lists into a single list of classes
        toolchain_classes: list[type[LanguageToolchain]] = [
            cls for sublist in toolchain_classes_list for cls in sublist
        ]

        # Check which toolchains accept this project
        applicable = []
        for toolchain_class in toolchain_classes:
            # Create temporary instance to check acceptance
            toolchain = toolchain_class(context)
            if toolchain.accept():
                applicable.append(toolchain_class)
        return applicable

    def _combine_artifacts(self, artifacts: list[BuildArtifact]) -> BuildArtifact:
        """Combine multiple artifacts for multi-language apps."""
        # Simple implementation: return composite artifact
        return BuildArtifact(
            kind="multi-language",
            location=str(self.context.source_path.parent),
            metadata={"artifacts": [a.__dict__ for a in artifacts]},
        )
