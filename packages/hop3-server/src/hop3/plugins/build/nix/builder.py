# Copyright (c) 2024-2025 Abilian SAS
# SPDX-License-Identifier: AGPL-3.0-only

"""NixBuilder - Build applications using user-provided hop3.nix."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from hop3.core.protocols import BuildArtifact, BuildContext, RuntimeConfig


class NixBuilder:
    """Build applications using user-provided hop3.nix.

    This builder handles applications that include a hop3.nix file,
    which defines how to build the application using Nix. The hop3.nix
    must produce a package containing $out/hop3/runtime.json with
    resolved store paths.

    Phase 1 of Nix integration - supports explicit hop3.nix files only.
    """

    name: str = "nix"

    def __init__(self, context: BuildContext) -> None:
        """Initialize NixBuilder with build context.

        Args:
            context: Build context containing app info and source path.
        """
        self.context = context
        self.rejection_reason: str = ""

    def accept(self) -> bool:
        """Check if this builder can handle the application.

        Returns True if:
        - hop3.nix file exists in the source directory
        - nix command is available on the system

        Returns:
            True if builder can handle this application.
        """
        source = self.context.source_path

        # Check for hop3.nix
        if not (source / "hop3.nix").exists():
            self.rejection_reason = "no hop3.nix file found"
            return False

        # Check nix is available
        if not self._nix_available():
            self.rejection_reason = "nix command not found"
            return False

        return True

    def build(self) -> BuildArtifact:
        """Build the application with nix-build.

        Runs nix-build on hop3.nix, then reads the runtime configuration
        from $out/hop3/runtime.json in the built package.

        Returns:
            BuildArtifact containing build metadata and RuntimeConfig.

        Raises:
            RuntimeError: If nix-build fails or runtime.json is missing.
        """
        source = self.context.source_path
        nix_file = source / "hop3.nix"

        # 1. Build the package
        store_path = self._nix_build(nix_file)

        # 2. Read runtime config from built package
        runtime_json = Path(store_path) / "hop3" / "runtime.json"
        if not runtime_json.exists():
            msg = (
                f"hop3.nix must create $out/hop3/runtime.json, "
                f"but {runtime_json} not found"
            )
            raise RuntimeError(msg)

        runtime_data = json.loads(runtime_json.read_text())

        # 3. Build RuntimeConfig
        runtime = RuntimeConfig(
            env_vars=runtime_data.get("env", {}),
            path_prepend=runtime_data.get("path", []),
            working_dir=store_path,
            workers=runtime_data.get("workers", {}),
        )

        # 4. Return BuildArtifact
        return BuildArtifact(
            kind="nix",
            builder="nix",
            app_name=self.context.app_name,
            built_at=datetime.now(timezone.utc).isoformat(),
            build_id=self._get_build_id(store_path),
            location=store_path,
            runtime=runtime,
            metadata={
                "nix_file": str(nix_file),
                "store_path": store_path,
            },
        )

    def _nix_available(self) -> bool:
        """Check if nix command is available on the system."""
        try:
            subprocess.run(
                ["nix", "--version"],
                capture_output=True,
                check=True,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def _nix_build(self, nix_file: Path) -> str:
        """Run nix-build and return the store path.

        Args:
            nix_file: Path to the hop3.nix file.

        Returns:
            The Nix store path of the built package.

        Raises:
            RuntimeError: If nix-build fails.
        """
        try:
            result = subprocess.run(
                [
                    "nix-build",
                    str(nix_file),
                    "-A",
                    "package",
                    "--no-out-link",
                ],
                capture_output=True,
                text=True,
                check=True,
                cwd=nix_file.parent,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            msg = f"nix-build failed: {e.stderr}"
            raise RuntimeError(msg) from e

    def _get_build_id(self, store_path: str) -> str:
        """Extract Nix hash from store path.

        Args:
            store_path: Full Nix store path like /nix/store/abc123-myapp

        Returns:
            The hash portion (abc123) of the store path.
        """
        # /nix/store/abc123-myapp -> abc123
        name = Path(store_path).name
        return name.split("-")[0] if "-" in name else name
