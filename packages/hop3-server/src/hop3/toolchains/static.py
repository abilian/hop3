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
    """
    Language toolchain for static file applications.

    This builder handles applications that serve static files (HTML, CSS, JS,
    images, etc.) without requiring any build process. The served directory is
    configured in ``hop3.toml`` — a Procfile is never required:

    - ``[build].static-dir = "<dir>"`` — the first-class key (e.g. "site",
      "html", "dist"); defaults to "public" when unset.
    - ``[run.workers].static = "<dir>"`` — back-compat (worker-flavored).
    - a Procfile ``static: <dir>`` line — generic, cross-tool fallback.
    """

    name = "Static"
    requirements = []  # No special requirements for static files  # ruff:ignore[mutable-class-default]

    def accept(self) -> bool:
        """
        Check if this is a static file application.

        Returns:
            True if a static directory is declared (Procfile ``static:`` entry
            or hop3.toml ``[run.workers]`` ``static``), False otherwise.
        """
        return self._parse_static_entry() is not None

    def build(self) -> BuildArtifact:
        """
        Build the static application (no actual build needed).

        For static apps, we just need to identify the static files directory.

        Returns:
            BuildArtifact containing the path to static files
        """
        # Resolve the served directory (hop3.toml [run.workers].static, a
        # Procfile `static:` line, or the "public" default).
        # A static site is often generated (mkdocs, hugo, a bundler), and that
        # generator is exactly what [build].build declares. Ignoring it served
        # the un-built sources — or nothing at all.
        self._run_declared_build()

        static_dir = self._get_static_dir()

        # Verify the directory exists
        static_path = self.src_path / static_dir
        if not static_path.exists():
            msg = f"Static directory '{static_dir}' not found at {static_path}"
            raise FileNotFoundError(msg)

        # Declare the served directory as a "static" worker in the artifact
        # runtime — the same channel every other toolchain uses for its process
        # model. This is how the deployer and nginx learn the app is served
        # statically (and from where) without a Procfile: nginx keys both its
        # static-only detection and its file mapping off this worker. Without
        # it, an app selected via `[build].toolchain = "static"` (no Procfile,
        # no [run.workers]) reached nginx with no workers, so nginx fell through
        # to the proxy path and emitted an invalid `upstream 127.0.0.1:0`.
        runtime = self._make_runtime_config(workers={"static": static_dir})
        return self._make_build_artifact(
            kind="static",
            runtime=runtime,
            metadata={"static_dir": static_dir},
        )

    def _get_static_dir(self) -> str:
        """
        Parse Procfile to get the static directory path.

        Returns:
            Path to the static directory relative to src_path
        """
        static_dir = self._parse_static_entry()
        # Default to "public" if not found (shouldn't happen if accept() passed)
        return static_dir or "public"

    def _parse_static_entry(self) -> str | None:
        """
        Find the declared static directory. A Procfile is never required.

        Declarations are tried in order of precedence (hop3.toml — Hop3's own
        config — beats the generic, cross-tool Procfile, matching
        ``AppConfig.workers``):

        1. ``[build].static-dir`` — the first-class, Procfile-free key, e.g.
           ``static-dir = "site"``. The canonical spelling.
        2. ``[run.workers].static`` — the worker-flavored spelling (back-compat).
        3. a Procfile line ``static: <dir>``.

        Returns:
            The static directory path (relative to src_path) if declared, else None
        """
        # 1./2. hop3.toml (Hop3-specific config wins over the Procfile)
        hop3_toml_path = self.src_path / "hop3.toml"
        if hop3_toml_path.exists():
            config = Hop3Config.from_file(hop3_toml_path)
            # 1. [build].static-dir — the first-class, Procfile-free key.
            if static_dir := config.static_dir:
                return static_dir
            # 2. [run.workers].static worker (back-compat; worker-flavored).
            if static_dir := config.named_workers.get("static"):
                return static_dir

        # 3. Procfile "static:" entry (generic, cross-tool fallback)
        procfile_path = self.src_path / "Procfile"
        if procfile_path.exists():
            for line in procfile_path.read_text().splitlines():
                stripped_line = line.strip()
                if stripped_line.startswith("static:"):
                    return stripped_line.split(":", 1)[1].strip()

        return None
