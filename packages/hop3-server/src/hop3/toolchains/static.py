# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Language toolchain for static file applications."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3.project.hop3_config import Hop3Config

from ._base import LanguageToolchain

if TYPE_CHECKING:
    from hop3.core.protocols import BuildArtifact


class StaticToolchain(LanguageToolchain):
    """Language toolchain for static file applications.

    This builder handles applications that serve static files (HTML, CSS, JS,
    images, etc.) without requiring any build process. A static app is declared
    either by a Procfile ``static: <dir>`` line or, equivalently, by a ``static``
    worker in ``hop3.toml`` (``[run.workers]`` with ``static = "<dir>"``) — so a
    Procfile is not required.
    """

    name = "Static"
    requirements = []  # No special requirements for static files  # noqa: RUF012

    def accept(self) -> bool:
        """Check if this is a static file application.

        Returns:
            True if a static directory is declared (Procfile ``static:`` entry
            or hop3.toml ``[run.workers]`` ``static``), False otherwise.
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

        # Static files - no runtime config needed
        return self._make_build_artifact(
            kind="static",
            metadata={"static_dir": static_dir},
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
        """Find the declared static directory, from hop3.toml or the Procfile.

        Two equivalent declarations are accepted, so a Procfile is not required:

        - a ``static`` worker in ``hop3.toml`` (``[run.workers]`` with
          ``static = "<dir>"``);
        - a Procfile line ``static: <dir>``.

        ``hop3.toml`` takes precedence when both are present: it is Hop3's own
        config file, whereas a Procfile is a generic, cross-tool convention that
        may belong to something else. This matches the worker precedence used
        everywhere else (``AppConfig.workers``: hop3.toml > Procfile).

        Returns:
            The static directory path (relative to src_path) if declared, else None
        """
        # 1. hop3.toml [run.workers] static = "<dir>" (Hop3-specific config wins)
        hop3_toml_path = self.src_path / "hop3.toml"
        if hop3_toml_path.exists():
            config = Hop3Config.from_file(hop3_toml_path)
            static_dir = config.named_workers.get("static")
            if static_dir:
                return static_dir

        # 2. Procfile "static:" entry (generic, cross-tool fallback)
        procfile_path = self.src_path / "Procfile"
        if procfile_path.exists():
            for line in procfile_path.read_text().splitlines():
                stripped_line = line.strip()
                if stripped_line.startswith("static:"):
                    return stripped_line.split(":", 1)[1].strip()

        return None
