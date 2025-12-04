# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Language toolchain for static file applications."""

from __future__ import annotations

from hop3.core.protocols import BuildArtifact

from ._base import LanguageToolchain


class StaticToolchain(LanguageToolchain):
    """Language toolchain for static file applications.

    This builder handles applications that serve static files (HTML, CSS, JS, images, etc.)
    without requiring any build process. It detects static apps by looking for a Procfile
    with a "static:" entry.
    """

    name = "Static"
    requirements = []  # No special requirements for static files  # noqa: RUF012

    def accept(self) -> bool:
        """Check if this is a static file application.

        Returns:
            True if Procfile contains a "static:" entry, False otherwise
        """
        return self._parse_static_entry() is not None

    def build(self) -> BuildArtifact:
        """Build the static application (no actual build needed).

        For static apps, we just need to identify the static files directory.

        Returns:
            BuildArtifact containing the path to static files
        """
        # Parse Procfile to find static directory
        static_dir = self._get_static_dir()

        # Verify the directory exists
        static_path = self.src_path / static_dir
        if not static_path.exists():
            msg = f"Static directory '{static_dir}' not found at {static_path}"
            raise FileNotFoundError(msg)

        # Return a BuildArtifact describing the static files location
        return BuildArtifact(
            kind="static",
            location=str(static_path),
            metadata={
                "app_name": self.app_name,
                "static_dir": static_dir,
            },
        )

    def _get_static_dir(self) -> str:
        """Parse Procfile to get the static directory path.

        Returns:
            Path to the static directory relative to src_path
        """
        static_dir = self._parse_static_entry()
        # Default to "public" if not found (shouldn't happen if accept() passed)
        return static_dir or "public"

    def _parse_static_entry(self) -> str | None:
        """Parse Procfile to find static entry.

        Returns:
            The static directory path if found, None otherwise
        """
        procfile_path = self.src_path / "Procfile"
        if not procfile_path.exists():
            return None

        procfile_content = procfile_path.read_text()
        for line in procfile_content.splitlines():
            stripped_line = line.strip()
            if stripped_line.startswith("static:"):
                # Extract directory path after "static:"
                return stripped_line.split(":", 1)[1].strip()

        return None
