#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Abilian SAS
"""Run all tutorials and collect results.

Usage: python scripts/run-all-tutorials.py [--verbose]
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


# ANSI color codes
class Colors:
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    BLUE = "\033[0;34m"
    NC = "\033[0m"  # No Color


@dataclass
class TutorialResult:
    name: str
    status: str  # "passed", "failed", "skipped"
    duration: float = 0.0
    test_count: int = 0
    fail_info: str = ""


@dataclass
class TestRunner:
    project_root: Path
    tutorials_dir: Path
    log_dir: Path
    verbose: bool = False
    test_domain: str = "hop3.local"

    # Results tracking
    results: list[TutorialResult] = field(default_factory=list)

    @property
    def passed(self) -> list[TutorialResult]:
        return [r for r in self.results if r.status == "passed"]

    @property
    def failed(self) -> list[TutorialResult]:
        return [r for r in self.results if r.status == "failed"]

    @property
    def skipped(self) -> list[TutorialResult]:
        return [r for r in self.results if r.status == "skipped"]

    def extract_app_name(self, file_path: Path) -> str | None:
        """Extract app name from tutorial file."""
        try:
            content = file_path.read_text()
            match = re.search(r"hop3-tuto-[a-zA-Z0-9_-]*", content)
            return match.group(0) if match else None
        except OSError:
            return None

    def extract_pass_count(self, log_content: str) -> int:
        """Extract pass count from log content."""
        match = re.search(r"(\d+) passed", log_content)
        return int(match.group(1)) if match else 0

    def extract_fail_info(self, log_content: str) -> str:
        """Extract failure info from log content."""
        match = re.search(r"\d+ passed, \d+ failed", log_content)
        if match:
            return match.group(0)
        match = re.search(r"\d+ failed", log_content)
        return match.group(0) if match else "error"

    def has_executable_blocks(self, file_path: Path) -> bool:
        """Check if tutorial has any executable blocks."""
        try:
            content = file_path.read_text()
            return "```bash exec" in content
        except OSError:
            return False

    def cleanup_app(self, app_name: str) -> None:
        """Clean up any existing app before running tutorial."""
        try:
            subprocess.run(
                ["hop3", "app:destroy", app_name, "-y"],
                capture_output=True,
                check=False,
            )
        except OSError:
            pass

    def run_tutorial(self, tutorial_path: Path) -> TutorialResult:
        """Run a single tutorial and return the result."""
        tutorial_name = tutorial_path.stem
        language = tutorial_path.parent.name
        full_name = f"{language}/{tutorial_name}"
        log_file = self.log_dir / f"{language}_{tutorial_name}.log"

        # Check if tutorial has any exec blocks
        if not self.has_executable_blocks(tutorial_path):
            print(f"  {Colors.YELLOW}[SKIP]{Colors.NC} {full_name} (no executable blocks)")
            log_file.write_text("SKIPPED: No executable blocks")
            return TutorialResult(name=full_name, status="skipped")

        # Clean up any existing app before running
        app_name = self.extract_app_name(tutorial_path)
        if app_name:
            self.cleanup_app(app_name)

        # Run the tutorial
        print(f"  {full_name:<40} ", end="", flush=True)

        start_time = time.time()
        try:
            result = subprocess.run(
                ["tutotest", "run", str(tutorial_path)],
                capture_output=True,
                text=True,
                check=True,
            )
            log_content = result.stdout + result.stderr
            log_file.write_text(log_content)

            duration = time.time() - start_time
            pass_count = self.extract_pass_count(log_content)

            print(f"{Colors.GREEN}[PASS]{Colors.NC} ({pass_count} tests, {duration:.0f}s)")
            return TutorialResult(
                name=full_name,
                status="passed",
                duration=duration,
                test_count=pass_count,
            )

        except subprocess.CalledProcessError as e:
            log_content = (e.stdout or "") + (e.stderr or "")
            log_file.write_text(log_content)

            duration = time.time() - start_time
            fail_info = self.extract_fail_info(log_content)

            print(f"{Colors.RED}[FAIL]{Colors.NC} ({fail_info}, {duration:.0f}s)")

            # Show failure details if verbose
            if self.verbose and log_content:
                print("    Last error:")
                lines = log_content.split("\n")
                fail_lines = []
                for i, line in enumerate(lines):
                    if "FAIL]" in line:
                        fail_lines = lines[i : i + 3]
                        break
                for line in fail_lines[-5:]:
                    print(f"    {line}")

            return TutorialResult(
                name=full_name,
                status="failed",
                duration=duration,
                fail_info=fail_info,
            )

        except OSError as e:
            log_file.write_text(f"ERROR: {e}")
            duration = time.time() - start_time
            print(f"{Colors.RED}[FAIL]{Colors.NC} (error running tutotest, {duration:.0f}s)")
            return TutorialResult(
                name=full_name,
                status="failed",
                duration=duration,
                fail_info=str(e),
            )

    def run_all(self) -> None:
        """Find and run all tutorials."""
        print(f"{Colors.BLUE}Running tutorials...{Colors.NC}")
        print()

        # Process tutorials by language
        for lang_dir in sorted(self.tutorials_dir.iterdir()):
            if not lang_dir.is_dir():
                continue

            language = lang_dir.name
            tutorials = sorted(lang_dir.glob("*.md"))

            if not tutorials:
                continue

            print(f"{Colors.YELLOW}{language}:{Colors.NC}")

            for tutorial in tutorials:
                result = self.run_tutorial(tutorial)
                self.results.append(result)

            print()

    def write_summary(self) -> None:
        """Write summary to file."""
        summary_file = self.log_dir / "summary.txt"
        lines = [
            "Tutorial Test Results",
            "=====================",
            "",
            f"Run Date: {datetime.now()}",
            f"Test Domain: {self.test_domain}",
            "",
            f"Total tutorials: {len(self.results)}",
            f"Passed: {len(self.passed)}",
            f"Failed: {len(self.failed)}",
            f"Skipped: {len(self.skipped)}",
            "",
        ]

        if self.passed:
            lines.append("Passed tutorials:")
            for r in self.passed:
                lines.append(f"  \u2713 {r.name}")
            lines.append("")

        if self.failed:
            lines.append("Failed tutorials:")
            for r in self.failed:
                lines.append(f"  \u2717 {r.name}")
            lines.append("")

        if self.skipped:
            lines.append("Skipped tutorials:")
            for r in self.skipped:
                lines.append(f"  - {r.name}")
            lines.append("")

        summary_file.write_text("\n".join(lines))

    def print_summary(self) -> None:
        """Print summary to terminal."""
        print()
        print(f"{Colors.BLUE}========================================{Colors.NC}")
        print(f"{Colors.BLUE}Summary{Colors.NC}")
        print(f"{Colors.BLUE}========================================{Colors.NC}")
        print()
        print(f"Total tutorials: {len(self.results)}")
        print(f"{Colors.GREEN}Passed: {len(self.passed)}{Colors.NC}")
        print(f"{Colors.RED}Failed: {len(self.failed)}{Colors.NC}")
        print(f"{Colors.YELLOW}Skipped: {len(self.skipped)}{Colors.NC}")
        print()

        if self.passed:
            print("Passed tutorials:")
            for r in self.passed:
                print(f"  {Colors.GREEN}\u2713{Colors.NC} {r.name}")
            print()

        if self.failed:
            print("Failed tutorials:")
            for r in self.failed:
                print(f"  {Colors.RED}\u2717{Colors.NC} {r.name}")
            print()

        if self.skipped:
            print("Skipped tutorials:")
            for r in self.skipped:
                print(f"  {Colors.YELLOW}-{Colors.NC} {r.name}")
            print()


def check_dns_resolution(test_domain: str) -> tuple[bool, str]:
    """Check if DNS wildcard resolution is working for the test domain.

    Args:
        test_domain: The test domain (e.g., hop3.local)

    Returns:
        Tuple of (success, resolved_ip or error message)
    """
    import socket

    # Test wildcard resolution by resolving a random subdomain
    test_subdomain = f"dns-test.{test_domain}"

    try:
        resolved_ip = socket.gethostbyname(test_subdomain)
        return True, resolved_ip
    except socket.gaierror as e:
        return False, str(e)


def check_server_connectivity(test_domain: str, timeout: int = 10) -> bool:
    """Check if the Hop3 server is accessible.

    Args:
        test_domain: The test domain (e.g., hop3.local)
        timeout: Connection timeout in seconds

    Returns:
        True if server is accessible, False otherwise
    """
    import socket

    # Resolve domain to IP
    try:
        server_ip = socket.gethostbyname(test_domain)
    except socket.gaierror:
        print(f"{Colors.RED}Error: Cannot resolve {test_domain}{Colors.NC}")
        return False

    server_url = f"http://{server_ip}:8000/rpc"

    # Try to connect using curl
    try:
        result = subprocess.run(
            [
                "curl",
                "-s",
                "-o", "/dev/null",
                "-w", "%{http_code}",
                "--connect-timeout", str(timeout),
                "--max-time", str(timeout),
                server_url,
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        http_code = result.stdout.strip()

        # Any response means server is up
        if http_code and http_code != "000":
            return True

    except OSError:
        pass

    return False


def main() -> int:
    """Main entry point."""
    # Parse arguments
    verbose = "--verbose" in sys.argv or "-v" in sys.argv

    # Configuration
    script_dir = Path(__file__).parent.resolve()
    project_root = script_dir.parent
    tutorials_dir = project_root / "docs" / "src" / "tutorials"
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_dir = project_root / "logs" / "tutorial-logs" / timestamp

    # Ensure HOP3_TEST_DOMAIN is set
    test_domain = os.environ.get("HOP3_TEST_DOMAIN", "hop3.local")
    os.environ["HOP3_TEST_DOMAIN"] = test_domain

    # Create log directory
    log_dir.mkdir(parents=True, exist_ok=True)

    # Print header
    print(f"{Colors.BLUE}========================================{Colors.NC}")
    print(f"{Colors.BLUE}Tutorial Test Runner{Colors.NC}")
    print(f"{Colors.BLUE}========================================{Colors.NC}")
    print()
    print(f"Log directory: {log_dir}")
    print(f"Test domain: {test_domain}")
    print(f"Started at: {datetime.now()}")
    print()

    # Check DNS wildcard resolution before running tutorials
    print(f"Checking DNS wildcard resolution for *.{test_domain}...")
    dns_ok, dns_result = check_dns_resolution(test_domain)
    if not dns_ok:
        print(f"{Colors.RED}Error: DNS wildcard resolution not working for *.{test_domain}{Colors.NC}")
        print(f"  Resolution error: {dns_result}")
        print()
        print("Please configure DNS wildcard resolution:")
        print(f"  python scripts/setup-dnsmasq.py <server-ip>")
        print()
        print("For macOS, this script sets up dnsmasq to resolve:")
        print(f"  *.{test_domain} -> <server-ip>")
        print()
        print("See docs/src/dev/dns-configuration.md for details.")
        print()
        return 1
    print(f"{Colors.GREEN}DNS resolves *.{test_domain} -> {dns_result}{Colors.NC}")
    print()

    # Check server connectivity before running tutorials
    print(f"Checking server connectivity to {test_domain}:8000...")
    if not check_server_connectivity(test_domain):
        print(f"{Colors.RED}Error: Cannot connect to Hop3 server at {test_domain}:8000{Colors.NC}")
        print()
        print("Please ensure:")
        print("  1. The Hop3 server is running")
        print("  2. The server is accessible from this machine")
        print(f"  3. Run: python scripts/deploy-server.py --host {test_domain} -l")
        print()
        return 1
    print(f"{Colors.GREEN}Server is accessible{Colors.NC}")
    print()

    # Check tutorials directory exists
    if not tutorials_dir.exists():
        print(f"{Colors.RED}Error: Tutorials directory not found: {tutorials_dir}{Colors.NC}")
        return 1

    # Create runner and run all tutorials
    runner = TestRunner(
        project_root=project_root,
        tutorials_dir=tutorials_dir,
        log_dir=log_dir,
        verbose=verbose,
        test_domain=test_domain,
    )

    runner.run_all()
    runner.write_summary()
    runner.print_summary()

    print(f"Finished at: {datetime.now()}")
    print(f"Logs saved to: {log_dir}")

    # Exit with failure if any tutorials failed
    return 1 if runner.failed else 0


if __name__ == "__main__":
    sys.exit(main())
