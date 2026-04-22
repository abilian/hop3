# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""LocalBuilder - builds applications directly on host using language toolchains."""

from __future__ import annotations

import shutil
import subprocess
import time

from hop3.config import APP_ROOT
from hop3.core.plugins import get_plugin_manager
from hop3.core.protocols import BuildArtifact, BuildContext, LanguageToolchain
from hop3.lib import log
from hop3.lib.diagnostics import Diagnosis, log_diagnosis
from hop3.lib.logging import server_log


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
        """Accept if at least one language toolchain can handle this project.

        When an explicit toolchain is specified in hop3.toml, we accept immediately
        without checking source files (which might not exist until before-build runs).
        """
        src_path = self.context.source_path

        # Check if explicit toolchain is specified - trust user's config
        explicit_toolchain = self._get_explicit_toolchain()
        if explicit_toolchain:
            log(
                f"Explicit toolchain specified: {explicit_toolchain}",
                level=2,
                fg="cyan",
            )
            return True

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
        start_time = time.time()
        build_output: list[str] = []
        success = False

        # Probe declared host packages before invoking the toolchain.
        # Soft gate: logs a Diagnosis naming the missing package and
        # three remedies, but lets the build continue so the probe
        # can't create false negatives. The installer baseline
        # (see hop3_installer.server_installer.baseline) is supposed
        # to have covered these packages at server-provisioning time;
        # when it hasn't, the operator gets a useful signal *before*
        # the downstream pkg-config / linker error.
        missing = _probe_declared_packages(self.context)
        for package in missing:
            log_diagnosis(
                Diagnosis(
                    component="Native builder",
                    action=f"verify host package '{package}'",
                    reason=(
                        f"'{package}' is declared in [build].packages / "
                        "[run].packages but is not installed on this host."
                    ),
                    hint=(
                        "Run `hop3-install server` (or re-run on the target) "
                        f"— the catalogue baseline should install '{package}'."
                    ),
                    troubleshooting=[
                        f"Manually: apt-get install -y {package}",
                        (
                            "If the baseline is missing this package, add it to "
                            "apps/<app>/hop3.toml [build].packages and regenerate "
                            "with `python -m hop3_installer.server_installer.baseline`"
                        ),
                        (
                            "If the package is genuinely not installable "
                            "(alternate version, conflict), switch this app "
                            "to Docker or Nix."
                        ),
                    ],
                ),
                level=1,
                fg="yellow",
            )

        try:
            # 1. Discover applicable toolchains
            toolchains = self._discover_toolchains(self.context)

            if not toolchains:
                msg = "No language toolchain detected for this project"
                build_output.append(f"ERROR: {msg}")
                raise RuntimeError(msg)

            # Log detected toolchains
            toolchain_names = [getattr(tc, "name", tc.__name__) for tc in toolchains]
            msg = f"Detected toolchains: {', '.join(toolchain_names)}"
            log(msg, level=2, fg="cyan")
            build_output.append(msg)

            # 2. Build with each toolchain (supports multi-language apps)
            artifacts = []
            for toolchain_class in toolchains:
                toolchain_name = getattr(
                    toolchain_class, "name", toolchain_class.__name__
                )
                msg = f"Building with {toolchain_name} toolchain..."
                log(msg, level=2, fg="blue")
                build_output.append(msg)

                toolchain = toolchain_class(self.context)
                artifact = toolchain.build()
                artifacts.append(artifact)

                msg = f"Build with {toolchain_name} completed: {artifact.kind} at {artifact.location}"
                build_output.append(msg)

            success = True

            # 3. Single toolchain case
            if len(artifacts) == 1:
                return artifacts[0]

            # 4. Multi-toolchain case (e.g., Python + Node)
            return self._combine_artifacts(artifacts)

        except Exception as e:
            build_output.append(f"BUILD FAILED: {e}")
            raise

        finally:
            # Always save build log
            duration = time.time() - start_time
            self._save_build_log(build_output, duration, success=success)

    def _discover_toolchains(
        self, context: BuildContext
    ) -> list[type[LanguageToolchain]]:
        """Auto-detect which toolchains apply to this project.

        If an explicit toolchain is specified in hop3.toml (e.g., toolchain = "generic"),
        only that toolchain is used. Otherwise, auto-detect all applicable toolchains.

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

        # Import decision logger
        from hop3.lib.decision_log import get_decision_logger  # noqa: PLC0415

        decision_logger = get_decision_logger()

        # Check if explicit toolchain is specified in hop3.toml
        explicit_toolchain = self._get_explicit_toolchain()
        if explicit_toolchain:
            # Only use the explicitly specified toolchain
            # Don't call accept() - trust the user's configuration
            # (source files might not exist until before-build runs)
            for toolchain_class in toolchain_classes:
                name = getattr(toolchain_class, "name", "").lower()
                if name == explicit_toolchain.lower():
                    decision_logger.log_toolchain_decision(
                        explicit_toolchain,
                        "explicitly set in hop3.toml [build].toolchain",
                        explicit=True,
                    )
                    return [toolchain_class]
            # Toolchain not found
            log(
                f"Warning: Explicit toolchain '{explicit_toolchain}' not found",
                level=1,
                fg="yellow",
            )
            return []

        # Auto-detect: check which toolchains accept this project
        applicable = []
        for toolchain_class in toolchain_classes:
            # Create temporary instance to check acceptance
            toolchain = toolchain_class(context)
            if toolchain.accept():
                applicable.append(toolchain_class)

        # Log auto-detection decisions
        for toolchain_class in applicable:
            toolchain_name = getattr(toolchain_class, "name", toolchain_class.__name__)
            # Get detection info if available
            detected_files = getattr(toolchain_class, "detection_files", None)
            decision_logger.log_toolchain_decision(
                toolchain_name,
                "auto-detected from project files",
                explicit=False,
                detected_files=detected_files,
            )

        return applicable

    def _get_explicit_toolchain(self) -> str | None:
        """Get explicitly specified toolchain from hop3.toml if present.

        Returns the toolchain name if [build] toolchain is set, otherwise None.
        """
        app_config = self.context.app_config
        hop3_config = app_config.get("hop3_config", {})
        if not isinstance(hop3_config, dict):
            return None
        build_section = hop3_config.get("build", {})
        if not isinstance(build_section, dict):
            return None
        return build_section.get("toolchain")

    def _combine_artifacts(self, artifacts: list[BuildArtifact]) -> BuildArtifact:
        """Combine multiple artifacts for multi-language apps."""
        # Simple implementation: return composite artifact
        return BuildArtifact(
            kind="multi-language",
            location=str(self.context.source_path.parent),
            metadata={"artifacts": [a.__dict__ for a in artifacts]},
        )

    def _save_build_log(
        self, output: list[str], duration: float, *, success: bool = True
    ) -> None:
        """Save build log to app's log directory.

        Args:
            output: Build output messages
            duration: Build duration in seconds
            success: Whether build succeeded
        """
        try:
            # BuildContext.app_name is the authoritative source — the
            # app_config dict doesn't reliably carry it, so a previous
            # `.get("app_name", "unknown")` dropped every app's build
            # log into /home/hop3/unknown/log/ (without apps/).
            app_name = self.context.app_name

            # App log dir sits under APP_ROOT (= HOP3_ROOT/apps), not
            # HOP3_ROOT itself.
            app_log_dir = APP_ROOT / app_name / "log"
            app_log_dir.mkdir(parents=True, exist_ok=True)

            build_log_path = app_log_dir / "build.log"

            # Format log content
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            status = "SUCCESS" if success else "FAILED"
            output_text = "\n".join(output)
            content = f"""=== Local Build Log ===
Timestamp: {timestamp}
App: {app_name}
Status: {status}
Duration: {duration:.1f}s
Builder: local

=== BUILD OUTPUT ===
{output_text}
"""
            build_log_path.write_text(content)
            log(f"Build log saved to: {build_log_path}", level=2)

        except Exception as e:
            # Don't fail the build if log saving fails
            server_log.warning(
                "Failed to save build log",
                app_name=self.context.app_name,
                error=str(e),
            )


def _probe_declared_packages(context: BuildContext) -> list[str]:
    """Return the packages declared in hop3.toml that are NOT installed.

    Checks `[build].packages` + `[run].packages` against the local
    package database (dpkg on Debian-family, rpm on Fedora-family).
    On unknown/unsupported systems, returns an empty list (no probe).
    """
    hop3_config = context.app_config.get("hop3_config", {})
    if not isinstance(hop3_config, dict):
        return []

    declared: list[str] = []
    for field in ("build", "run"):
        section = hop3_config.get(field, {})
        if isinstance(section, dict):
            packages = section.get("packages", [])
            if isinstance(packages, list):
                declared.extend(p for p in packages if isinstance(p, str))

    if not declared:
        return []

    if shutil.which("dpkg") is not None:
        return [p for p in declared if not _is_installed_dpkg(p)]
    if shutil.which("rpm") is not None:
        return [p for p in declared if not _is_installed_rpm(p)]
    return []


def _is_installed_dpkg(package: str) -> bool:
    """`dpkg -s` returns 0 iff the package is installed + configured."""
    result = subprocess.run(
        ["dpkg", "-s", package],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    if result.returncode != 0:
        return False
    return "Status: install ok installed" in result.stdout


def _is_installed_rpm(package: str) -> bool:
    """`rpm -q` exits 0 iff the package is installed."""
    result = subprocess.run(
        ["rpm", "-q", package],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    return result.returncode == 0
