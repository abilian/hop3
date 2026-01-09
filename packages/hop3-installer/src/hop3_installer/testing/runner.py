# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Test runner for installer tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from . import common
from .common import (
    C,
    log_error,
    log_header,
    log_info,
    log_subheader,
    log_success,
    log_warning,
)
from .validators import validate_cli_installation, validate_server_installation

if TYPE_CHECKING:
    from .backends.base import Backend

# Installation methods
INSTALL_METHODS = ["pypi", "git", "local"]


@dataclass
class TestConfig:
    """Configuration for a test run."""

    # Installation method: pypi, git, or local
    method: str = "git"

    # Git branch (for git method)
    branch: str = "devel"

    # Version (for pypi method)
    version: str | None = None

    # Path to local packages (for local method)
    local_packages_dir: Path | None = None

    # Path to installer scripts
    installer_dir: Path = field(default_factory=lambda: Path(__file__).parent.parent)

    # Whether to skip ACME setup in server tests
    skip_acme: bool = True


@dataclass
class TestResult:
    """Result of a test run."""

    name: str
    passed: bool
    error: str | None = None


class TestRunner:
    """Runs installer tests using a backend."""

    def __init__(self, backend: Backend, config: TestConfig | None = None):
        """Initialize test runner.

        Args:
            backend: The backend to use for running tests
            config: Test configuration
        """
        self.backend = backend
        self.config = config or TestConfig()
        self.results: list[TestResult] = []

    def run_cli_tests(self, methods: list[str] | None = None) -> dict[str, bool]:
        """Run CLI installer tests.

        Args:
            methods: List of installation methods to test

        Returns:
            Dict mapping test name to pass/fail
        """
        methods = methods or [self.config.method]
        results = {}

        for method in methods:
            test_name = f"cli-{method}"
            if method == "pypi" and self.config.version:
                test_name = f"cli-pypi-{self.config.version}"

            try:
                passed = self._test_cli(method)
                results[test_name] = passed
                self.results.append(TestResult(test_name, passed))
            except Exception as e:
                log_error(f"Exception during {test_name}: {e}")
                results[test_name] = False
                self.results.append(TestResult(test_name, passed=False, error=str(e)))

        return results

    def run_server_tests(self, methods: list[str] | None = None) -> dict[str, bool]:
        """Run server installer tests.

        Args:
            methods: List of installation methods to test

        Returns:
            Dict mapping test name to pass/fail
        """
        methods = methods or [self.config.method]
        results = {}

        for method in methods:
            # Server not on PyPI yet
            if method == "pypi":
                log_info("Skipping server pypi test (not yet on PyPI)")
                continue

            test_name = f"server-{method}"

            try:
                passed = self._test_server(method)
                results[test_name] = passed
                self.results.append(TestResult(test_name, passed))
            except Exception as e:
                log_error(f"Exception during {test_name}: {e}")
                results[test_name] = False
                self.results.append(TestResult(test_name, passed=False, error=str(e)))

        return results

    def _test_cli(self, method: str) -> bool:
        """Test CLI installation with a specific method."""
        version_str = self.config.version or "latest"
        if method == "pypi":
            log_subheader(f"Testing CLI: PyPI ({version_str})")
        elif method == "git":
            log_subheader(f"Testing CLI: Git ({self.config.branch} branch)")
        else:
            log_subheader("Testing CLI: Local path")

        # Cleanup first
        self.backend.cleanup_cli()

        # Upload installer
        installer_path = self.config.installer_dir / "install-cli.py"
        if not self._upload_installer(installer_path, "cli"):
            return False

        # For local method, upload package
        if method == "local":
            if not self._upload_local_package("cli"):
                log_warning("Skipping local path test (could not upload package)")
                return True  # Don't fail the suite

        # Build command
        cmd = self._build_cli_install_command(method)

        # Run installer
        log_info(f"Running installer ({method})...")
        result = self.backend.run(cmd)

        if not result.success:
            log_error("Installation failed")
            # Always show output on failure, more details in verbose mode
            if result.stdout.strip():
                print(result.stdout)
            if result.stderr.strip():
                print(result.stderr)
            return False

        log_success("CLI installer completed")
        if common.VERBOSE and result.stdout.strip():
            print(result.stdout)

        # Validate
        return validate_cli_installation(self.backend)

    def _test_server(self, method: str) -> bool:
        """Test server installation with a specific method."""
        if method == "git":
            log_subheader(f"Testing Server: Git ({self.config.branch} branch)")
        else:
            log_subheader("Testing Server: Local path")

        # Cleanup first
        self.backend.cleanup_server()

        # Upload installer
        installer_path = self.config.installer_dir / "install-server.py"
        if not self._upload_installer(installer_path, "server"):
            return False

        # For local method, upload package
        if method == "local":
            if not self._upload_local_package("server"):
                log_warning("Skipping local path test (could not upload package)")
                return True  # Don't fail the suite

        # Build command
        cmd = self._build_server_install_command(method)

        # Run installer
        skip_info = "skip-acme" if self.config.skip_acme else ""
        log_info(
            f"Running installer ({method}{', ' + skip_info if skip_info else ''})..."
        )
        result = self.backend.run(cmd, sudo=True)

        if not result.success:
            log_error("Installation failed")
            # Always show output on failure, more details in verbose mode
            if result.stdout.strip():
                print(result.stdout)
            if result.stderr.strip():
                print(result.stderr)
            return False

        log_success("Server installer completed")
        if common.VERBOSE and result.stdout.strip():
            print(result.stdout)

        # Validate
        return validate_server_installation(self.backend)

    def _upload_installer(self, installer_path: Path, installer_type: str) -> bool:
        """Upload installer script to the test environment."""
        if not installer_path.exists():
            log_error(f"Installer not found: {installer_path}")
            return False

        remote_path = self.backend.get_installer_path(installer_type)

        # For backends with mounted volumes (Docker, Vagrant), skip upload
        if hasattr(self.backend, "installer_dir") or hasattr(
            self.backend, "vagrant_dir"
        ):
            return True

        return self.backend.upload(installer_path, remote_path)

    def _upload_local_package(self, package_type: str) -> bool:
        """Upload local package for --local-path testing."""
        if self.config.local_packages_dir is None:
            # Try to find packages directory
            project_root = self.config.installer_dir.parent
            packages_dir = project_root / "packages"
        else:
            packages_dir = self.config.local_packages_dir

        if package_type == "cli":
            local_package = packages_dir / "hop3-cli"
        else:
            local_package = packages_dir / "hop3-server"

        if not local_package.exists():
            log_error(f"Local package not found: {local_package}")
            return False

        remote_path = f"/tmp/hop3-{package_type}"

        log_info(f"Uploading {local_package} to {remote_path}...")

        # Remove existing
        self.backend.run(f"rm -rf {remote_path}")

        if self.backend.upload_dir(local_package, remote_path):
            # Fix permissions
            self.backend.run(f"chmod -R a+rX {remote_path}", sudo=True)
            log_success(f"Package uploaded to {remote_path}")
            return True

        log_error(f"Failed to upload package to {remote_path}")
        return False

    def _build_cli_install_command(self, method: str) -> str:
        """Build the CLI installer command."""
        installer_path = self.backend.get_installer_path("cli")
        base_cmd = f"python3 {installer_path} --no-modify-path --verbose"

        match method:
            case "pypi":
                if self.config.version:
                    return f"{base_cmd} --version {self.config.version}"
                return base_cmd
            case "git":
                return f"{base_cmd} --git --branch {self.config.branch}"
            case _:  # local
                return f"{base_cmd} --local-path /tmp/hop3-cli"

    def _build_server_install_command(self, method: str) -> str:
        """Build the server installer command."""
        installer_path = self.backend.get_installer_path("server")
        base_cmd = f"python3 {installer_path} --verbose"

        if self.config.skip_acme:
            base_cmd += " --skip-acme"

        match method:
            case "git":
                return f"{base_cmd} --git --branch {self.config.branch}"
            case _:  # local
                return f"{base_cmd} --local-path /tmp/hop3-server"

    def print_summary(self) -> bool:
        """Print test summary.

        Returns:
            True if all tests passed, False otherwise
        """
        log_header("Test Summary")

        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed

        print(f"  Total:   {total}")
        print(f"  Passed:  {C.GREEN}{passed}{C.RESET}")
        print(f"  Failed:  {C.RED if failed > 0 else ''}{failed}{C.RESET}")
        print()

        for result in self.results:
            status = (
                f"{C.GREEN}PASS{C.RESET}" if result.passed else f"{C.RED}FAIL{C.RESET}"
            )
            print(f"  [{status}] {result.name}")

        if failed > 0:
            print()
            log_error("Some tests failed")
            return False

        print()
        log_success("All tests passed!")
        return True
