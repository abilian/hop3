# Copyright (c) 2024-2025 Abilian SAS
# SPDX-License-Identifier: AGPL-3.0-only

"""NixBuilder - Build applications using user-provided hop3.nix."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from hop3.core.protocols import BuildArtifact, BuildContext, RuntimeConfig

# Nix profile scripts to try (single-user and multi-user modes)
# Note: Single-user path is evaluated at runtime via _get_nix_profile_paths()
# to ensure we use the correct HOME for the current process
NIX_DAEMON_PROFILE = Path("/nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh")


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
        workers = runtime_data.get("workers", {})
        runtime = RuntimeConfig(
            env_vars=runtime_data.get("env", {}),
            path_prepend=runtime_data.get("path", []),
            working_dir=store_path,
            workers=workers,
        )

        # 4. Determine artifact kind based on workers
        # Static sites have only a "static" worker pointing to a directory
        if list(workers.keys()) == ["static"]:
            artifact_kind = "static"
        else:
            artifact_kind = "nix"

        # 5. Return BuildArtifact
        return BuildArtifact(
            kind=artifact_kind,
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
        result = self._run_nix_command("nix --version")
        return result.returncode == 0

    def _nix_build(self, nix_file: Path) -> str:
        """Run nix-build and return the store path.

        Args:
            nix_file: Path to the hop3.nix file.

        Returns:
            The Nix store path of the built package.

        Raises:
            RuntimeError: If nix-build fails.
        """
        cmd = f"nix-build {nix_file} -A package --no-out-link"
        result = self._run_nix_command(cmd, cwd=nix_file.parent)

        if result.returncode != 0:
            msg = f"nix-build failed: {result.stderr}"
            raise RuntimeError(msg)

        return result.stdout.strip()

    def _run_nix_command(
        self,
        cmd: str,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess:
        """Run a Nix command with the Nix profile sourced.

        Nix commands require the profile to be sourced to set PATH correctly.
        This handles both single-user (~/.nix-profile) and multi-user
        (/nix/var/nix/profiles/default) installations.

        Args:
            cmd: The Nix command to run.
            cwd: Working directory for the command.

        Returns:
            CompletedProcess with stdout, stderr, and returncode.
        """
        # Find available Nix profile script
        profile_script = self._find_nix_profile()

        if profile_script:
            # Source the profile and run the command
            shell_cmd = f'. "{profile_script}" && {cmd}'
        else:
            # No profile found, try running directly (might work if in PATH)
            shell_cmd = cmd

        return subprocess.run(
            ["bash", "-c", shell_cmd],
            capture_output=True,
            text=True,
            cwd=cwd,
            env=self._get_nix_env(),
        )

    def _get_nix_profile_paths(self) -> list[Path]:
        """Get potential Nix profile script paths.

        Evaluates paths at runtime to ensure HOME is correct for the
        current process context (important when running as hop3 user).

        Returns:
            List of profile script paths to try.
        """
        return [
            Path.home() / ".nix-profile/etc/profile.d/nix.sh",
            NIX_DAEMON_PROFILE,
        ]

    def _find_nix_profile(self) -> Path | None:
        """Find the Nix profile script.

        Returns:
            Path to the profile script, or None if not found.
        """
        for script in self._get_nix_profile_paths():
            if script.exists():
                return script
        return None

    def _get_nix_env(self) -> dict[str, str]:
        """Get environment variables for Nix commands.

        The Nix profile script requires HOME and USER to be set.
        Supervisor may not set PATH, so we provide a minimal one.

        Returns:
            Environment dict with HOME, USER, and PATH set correctly.
        """
        env = os.environ.copy()

        # Ensure HOME is set for profile sourcing
        if "HOME" not in env:
            env["HOME"] = str(Path.home())

        # Ensure USER is set - required by Nix profile script
        if "USER" not in env:
            import pwd
            try:
                env["USER"] = pwd.getpwuid(os.getuid()).pw_name
            except (KeyError, OSError):
                env["USER"] = "hop3"  # Fallback

        # Ensure PATH includes essential directories
        # Supervisor may not set PATH, so we need to provide a minimal one
        if "PATH" not in env:
            env["PATH"] = "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

        return env

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
