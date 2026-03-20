# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Main orchestrator for daily system tests."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

import paramiko
from rich.console import Console
from rich.panel import Panel

from hop3_testing.util import find_project_root, find_project_root_optional

from .deployment import DeploymentManager, DeploymentResult, DeploymentVerifier
from .diagnostics import DiagnosticCollector, DiagnosticResult
from .hetzner import HetznerError, HetznerManager, ServerInfo
from .runner import AllSuitesResult, TestRunnerManager
from .ssh import SSHConnection, SSHConnectionInfo, is_port_open, verify_ssh_connectivity

if TYPE_CHECKING:
    from .config import Config


class Phase(Enum):
    """Test run phases."""

    INIT = "init"
    RESET = "reset"
    DEPLOY = "deploy"
    TEST = "test"
    REPORT = "report"


@dataclass
class PhaseResult:
    """Result of a single phase."""

    phase: Phase
    success: bool
    duration: float
    message: str
    details: dict = field(default_factory=dict)


@dataclass
class DailyTestResult:
    """Complete result of a daily test run."""

    timestamp: datetime
    branch: str
    server_info: ServerInfo | None
    phase_results: list[PhaseResult] = field(default_factory=list)
    deployment_result: DeploymentResult | None = None
    test_results: AllSuitesResult | None = None
    diagnostics: DiagnosticResult | None = None

    @property
    def success(self) -> bool:
        """Check if all phases succeeded."""
        return all(p.success for p in self.phase_results)

    @property
    def total_duration(self) -> float:
        """Total duration of all phases."""
        return sum(p.duration for p in self.phase_results)

    @property
    def failed_phase(self) -> Phase | None:
        """Get the first failed phase, if any."""
        for p in self.phase_results:
            if not p.success:
                return p.phase
        return None


class DailyTestOrchestrator:
    """Orchestrates the daily system test workflow."""

    def __init__(
        self,
        config: Config,
        console: Console | None = None,
        verbose: bool = False,
    ):
        """Initialize orchestrator.

        Args:
            config: Test configuration.
            console: Rich console for output. Creates one if None.
            verbose: Enable verbose output with streaming logs.
        """
        self.config = config
        self.console = console or Console()
        self.verbose = verbose
        self._result = DailyTestResult(
            timestamp=datetime.now(tz=UTC),
            branch=config.deployment.branch,
            server_info=None,
        )
        self._hetzner: HetznerManager | None = None
        self._deployment: DeploymentManager | None = None
        self._test_logs_dir: Path | None = None

    def run(
        self,
        skip_reset: bool = False,
        skip_deploy: bool = False,
        skip_tests: bool = False,
    ) -> DailyTestResult:
        """Run the complete daily test workflow.

        Args:
            skip_reset: Skip server reset phase.
            skip_deploy: Skip deployment phase.
            skip_tests: Skip test execution phase.

        Returns:
            DailyTestResult with all phase outcomes.
        """
        self._print_header()

        # Phase 1: Initialize
        phase_result = self._run_init_phase()
        self._result.phase_results.append(phase_result)
        if not phase_result.success:
            return self._finalize()

        # Phase 2: Reset server
        if not skip_reset:
            phase_result = self._run_reset_phase()
            self._result.phase_results.append(phase_result)
            if not phase_result.success:
                return self._finalize()
        else:
            self._log_skip("Server reset (--skip-reset)")

        # Phase 3: Deploy Hop3
        if not skip_deploy:
            phase_result = self._run_deploy_phase()
            self._result.phase_results.append(phase_result)
            if not phase_result.success:
                return self._finalize()
        else:
            self._log_skip("Deployment (--skip-deploy)")

        # Phase 4: Run tests (placeholder for Phase 2 implementation)
        if not skip_tests:
            phase_result = self._run_test_phase()
            self._result.phase_results.append(phase_result)

        return self._finalize()

    def _run_init_phase(self) -> PhaseResult:
        """Initialize managers and validate configuration."""
        start_time = time.time()
        self._log_phase("Initialization")

        try:
            # Validate configuration
            errors = self.config.validate()
            if errors:
                return PhaseResult(
                    phase=Phase.INIT,
                    success=False,
                    duration=time.time() - start_time,
                    message="Configuration validation failed",
                    details={"errors": errors},
                )

            # Initialize Hetzner manager
            self._hetzner = HetznerManager(
                self.config.hetzner,
                verbose=self.verbose,
                console=self.console,
            )

            # Get server info
            server_info = self._hetzner.get_server_info()
            self._result.server_info = server_info

            self.console.print(f"  Server: {server_info.name} ({server_info.ipv4})")
            self.console.print(f"  Status: {server_info.status.value}")
            self.console.print(f"  Datacenter: {server_info.datacenter}")

            return PhaseResult(
                phase=Phase.INIT,
                success=True,
                duration=time.time() - start_time,
                message="Initialization complete",
                details={"server_id": server_info.id},
            )

        except HetznerError as e:
            return PhaseResult(
                phase=Phase.INIT,
                success=False,
                duration=time.time() - start_time,
                message=f"Hetzner API error: {e}",
            )

        except Exception as e:
            return PhaseResult(
                phase=Phase.INIT,
                success=False,
                duration=time.time() - start_time,
                message=f"Unexpected error: {e}",
            )

    def _run_reset_phase(self) -> PhaseResult:
        """Reset server to clean state."""
        start_time = time.time()
        self._log_phase("Server Reset")

        if not self._hetzner:
            return PhaseResult(
                phase=Phase.RESET,
                success=False,
                duration=0,
                message="Hetzner manager not initialized",
            )

        try:
            server_ip = self._hetzner.get_server_ip()

            # Rebuild server
            if self.verbose:
                self.console.print("  Rebuilding server...")
            else:
                self.console.print("  Rebuilding server...", end="")

            server_info = self._hetzner.rebuild_server(
                image=self.config.hetzner.image,
                timeout=600,
            )

            if not self.verbose:
                self.console.print(" done")
            self.console.print(
                f"  Server rebuilt with image: {self.config.hetzner.image}"
            )

            # Wait for SSH with progress
            self.console.print(
                "  Waiting for SSH...", end="" if not self.verbose else "\n"
            )
            ssh_ready = self._wait_for_ssh_with_progress(server_ip, timeout=300)

            if not ssh_ready:
                return PhaseResult(
                    phase=Phase.RESET,
                    success=False,
                    duration=time.time() - start_time,
                    message="SSH did not become available within 5 minutes",
                )

            if not self.verbose:
                self.console.print(" ready")

            # Verify SSH connectivity
            if self.verbose:
                self.console.print("  Verifying SSH connectivity...")
            if not verify_ssh_connectivity(server_ip):
                return PhaseResult(
                    phase=Phase.RESET,
                    success=False,
                    duration=time.time() - start_time,
                    message="SSH connectivity verification failed",
                )

            self._result.server_info = server_info
            self.console.print("  [green]Server reset complete[/green]")
            self.console.print(f"  Image: {server_info.image}")

            return PhaseResult(
                phase=Phase.RESET,
                success=True,
                duration=time.time() - start_time,
                message="Server reset complete",
                details={"image": server_info.image},
            )

        except HetznerError as e:
            return PhaseResult(
                phase=Phase.RESET,
                success=False,
                duration=time.time() - start_time,
                message=f"Server reset failed: {e}",
            )

        except Exception as e:
            return PhaseResult(
                phase=Phase.RESET,
                success=False,
                duration=time.time() - start_time,
                message=f"Unexpected error: {e}",
            )

    def _run_deploy_phase(self) -> PhaseResult:
        """Deploy Hop3 to the server."""
        start_time = time.time()
        self._log_phase("Hop3 Deployment")

        if not self._result.server_info:
            return PhaseResult(
                phase=Phase.DEPLOY,
                success=False,
                duration=0,
                message="Server info not available",
            )

        try:
            server_ip = self._result.server_info.ipv4

            self._deployment = DeploymentManager(
                host=server_ip,
                config=self.config.deployment,
                verbose=self.verbose,
                console=self.console,
            )

            # Clone repository or use local
            if self.config.deployment.use_local_repo:
                repo_path = (
                    self.config.deployment.local_repo_path or find_project_root()
                )
                self._deployment.repo_path = repo_path
                self.console.print(f"  Using local repository: {repo_path}")
            else:
                self.console.print("  Cloning repository...")
                repo_path = self._deployment.clone_repo()
                self.console.print(f"  Cloned to {repo_path}")

            # Run deployment
            self.console.print("  Deploying Hop3...")
            if self.verbose:
                self.console.print("  [dim]--- hop3-deploy output ---[/dim]")
            result = self._deployment.deploy()
            self._result.deployment_result = result
            if self.verbose:
                self.console.print("  [dim]--- end hop3-deploy output ---[/dim]")

            if not result.success:
                self.console.print(f"  [red]Deployment failed: {result.error}[/red]")
                self._print_deployment_diagnostics(server_ip, result)
                return PhaseResult(
                    phase=Phase.DEPLOY,
                    success=False,
                    duration=time.time() - start_time,
                    message=f"Deployment failed: {result.error}",
                    details={"log": result.log_output},
                )

            # Verify deployment
            verifier = DeploymentVerifier(server_ip)
            checks = verifier.run_all_checks()

            if not all(checks.values()):
                failed = [k for k, v in checks.items() if not v]
                return PhaseResult(
                    phase=Phase.DEPLOY,
                    success=False,
                    duration=time.time() - start_time,
                    message=f"Verification failed: {', '.join(failed)}",
                    details={"checks": checks},
                )

            # Verify Docker is installed (required for Docker-based apps)
            docker_installed = self._verify_docker_installed(server_ip)
            if not docker_installed:
                self.console.print("  [red]Docker is NOT installed on the server[/red]")
                self.console.print(
                    "  [yellow]Hint: Ensure deployment config has features=['docker'][/yellow]"
                )
                return PhaseResult(
                    phase=Phase.DEPLOY,
                    success=False,
                    duration=time.time() - start_time,
                    message="Docker not installed - required for Docker-based apps",
                    details={"checks": checks, "docker": False},
                )
            self.console.print("  [green]Docker is installed[/green]")

            self.console.print("  [green]Deployment complete[/green]")
            self.console.print(f"  Server URL: {result.server_url}")
            self.console.print(f"  Duration: {result.duration:.1f}s")

            return PhaseResult(
                phase=Phase.DEPLOY,
                success=True,
                duration=time.time() - start_time,
                message="Deployment complete",
                details={
                    "server_url": result.server_url,
                    "deploy_duration": result.duration,
                },
            )

        except Exception as e:
            return PhaseResult(
                phase=Phase.DEPLOY,
                success=False,
                duration=time.time() - start_time,
                message=f"Deployment error: {e}",
            )

        finally:
            # Cleanup temp directory
            if self._deployment:
                self._deployment.cleanup()

    def _run_test_phase(self) -> PhaseResult:
        """Run test suites using hop3-testing framework.

        The hop3 CLI runs locally, connects to the server via SSH tunnel,
        and deploys apps. The server handles builds (including Docker).
        """
        start_time = time.time()
        self._log_phase("Test Execution")

        if not self._result.server_info:
            return PhaseResult(
                phase=Phase.TEST,
                success=False,
                duration=0,
                message="Server info not available",
            )

        try:
            server_ip = self._result.server_info.ipv4

            # Verify hop3-server is running before attempting tests
            self.console.print("Checking hop3-server is ready...")
            verifier = DeploymentVerifier(server_ip)
            checks = verifier.run_all_checks()

            if not checks.get("rpc", False):
                self.console.print("  [red]hop3-server is not responding[/red]")
                self.console.print(
                    "  [yellow]Hint: Did you skip deployment? "
                    "Run without --skip-deploy to install hop3-server first.[/yellow]"
                )
                return PhaseResult(
                    phase=Phase.TEST,
                    success=False,
                    duration=time.time() - start_time,
                    message="hop3-server is not running - cannot run tests",
                    details={"checks": checks},
                )

            self.console.print("  [green]hop3-server is ready[/green]")

            # Find project root for test apps
            project_root = self._find_hop3_project_root()
            if not project_root:
                return PhaseResult(
                    phase=Phase.TEST,
                    success=False,
                    duration=time.time() - start_time,
                    message="Could not find hop3 project root",
                )
            self.console.print(f"  Project root: {project_root}")

            # Create logs directory for diagnostics
            # Must be created BEFORE running tests so immediate diagnostics work
            logs_dir = Path("./logs")
            timestamp = datetime.now(tz=UTC).strftime("%Y-%m-%d_%H-%M-%S")
            test_logs_dir = logs_dir / f"daily-test-{timestamp}"
            test_logs_dir.mkdir(parents=True, exist_ok=True)
            self._test_logs_dir = test_logs_dir  # Store for _collect_diagnostics

            # Create test runner using hop3-testing framework
            # The hop3 CLI runs locally and connects via SSH tunnel
            runner = TestRunnerManager(
                host=server_ip,
                config=self.config.tests,
                project_root=project_root,
                console=self.console,
                verbose=self.verbose,
                logs_dir=test_logs_dir,
            )

            # Run all test suites
            test_results = runner.run_all_suites()
            self._result.test_results = test_results

            # Print summary
            self.console.print()
            self.console.print("[bold]Test Results:[/bold]")
            self.console.print(
                f"  Total: {test_results.total_tests} tests, "
                f"{test_results.total_passed} passed, "
                f"{test_results.total_failed} failed"
            )

            if test_results.success:
                return PhaseResult(
                    phase=Phase.TEST,
                    success=True,
                    duration=time.time() - start_time,
                    message=f"All tests passed ({test_results.total_passed}/{test_results.total_tests})",
                    details={
                        "total": test_results.total_tests,
                        "passed": test_results.total_passed,
                        "failed": test_results.total_failed,
                    },
                )
            failed_tests = [r.test.name for r in test_results.get_failed_tests()]
            return PhaseResult(
                phase=Phase.TEST,
                success=False,
                duration=time.time() - start_time,
                message=f"{test_results.total_failed} test(s) failed",
                details={
                    "total": test_results.total_tests,
                    "passed": test_results.total_passed,
                    "failed": test_results.total_failed,
                    "failed_tests": failed_tests[:10],  # First 10 failures
                },
            )

        except Exception as e:
            return PhaseResult(
                phase=Phase.TEST,
                success=False,
                duration=time.time() - start_time,
                message=f"Test execution error: {e}",
            )

    def _finalize(self) -> DailyTestResult:
        """Finalize the test run and print summary."""
        # Collect diagnostics if there were failures
        if not self._result.success and self._result.server_info:
            self._collect_diagnostics()

        self._print_summary()
        return self._result

    def _collect_diagnostics(self) -> None:
        """Collect diagnostic information from the server after failures.

        Note: Per-test diagnostics are already collected by TestRunnerManager
        immediately when tests fail (before cleanup). This method collects
        general server diagnostics and any remaining app logs.
        """
        if not self._result.server_info:
            return

        server_ip = self._result.server_info.ipv4
        self._log_phase("Diagnostic Collection")

        # Get list of failed tests
        failed_tests: list[str] = []
        if self._result.test_results:
            failed_tests = [
                r.test.name for r in self._result.test_results.get_failed_tests()
            ]

        # Use existing logs directory if available (from test phase)
        # This ensures diagnostics go to the same place as per-test logs
        logs_dir = self._test_logs_dir.parent if self._test_logs_dir else Path("./logs")

        self.console.print(f"  Collecting diagnostics from {server_ip}...")
        self.console.print(f"  Failed tests: {len(failed_tests)}")

        info = SSHConnectionInfo(host=server_ip, user="root")
        conn = SSHConnection(info)

        try:
            if not conn.connect(timeout=30):
                self.console.print("  [red]Failed to connect for diagnostics[/red]")
                return

            collector = DiagnosticCollector(conn, logs_dir, self.console)
            # Use existing test logs directory if available (per-test diagnostics
            # were already collected there by TestRunnerManager)
            diagnostics = collector.collect(
                failed_tests, existing_output_dir=self._test_logs_dir
            )
            self._result.diagnostics = diagnostics

            if diagnostics.success:
                self.console.print(
                    f"  [green]Diagnostics saved to: {diagnostics.output_dir}[/green]"
                )
            else:
                self.console.print(
                    f"  [yellow]Diagnostics collected with {len(diagnostics.errors)} errors[/yellow]"
                )
                self.console.print(f"  Output: {diagnostics.output_dir}")

        except Exception as e:
            self.console.print(f"  [red]Error collecting diagnostics: {e}[/red]")

        finally:
            conn.close()

    def _print_header(self) -> None:
        """Print test run header."""
        self.console.print()
        self.console.print(
            Panel.fit(
                f"[bold]Hop3 Daily System Test[/bold]\n"
                f"Branch: {self.config.deployment.branch}\n"
                f"Started: {self._result.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
                title="Daily Test",
            )
        )
        self.console.print()

    def _print_summary(self) -> None:
        """Print test run summary."""
        self.console.print()

        if self._result.success:
            status = "[bold green]PASSED[/bold green]"
        elif self._result.failed_phase:
            status = f"[bold red]FAILED[/bold red] at {self._result.failed_phase.value}"
        else:
            status = "[bold red]FAILED[/bold red]"

        # Build summary text
        summary_lines = [
            f"Status: {status}",
            f"Total Duration: {self._result.total_duration:.1f}s",
            f"Phases: {len(self._result.phase_results)}",
        ]

        # Add test results summary if available
        if self._result.test_results:
            tr = self._result.test_results
            summary_lines.extend([
                "",
                f"Tests: {tr.total_passed}/{tr.total_tests} passed",
                f"Failed: {tr.total_failed}, Skipped: {tr.total_skipped}",
            ])

        self.console.print(
            Panel.fit(
                "\n".join(summary_lines),
                title="Summary",
            )
        )

        # Print phase details
        self.console.print()
        for pr in self._result.phase_results:
            icon = "[green]✓[/green]" if pr.success else "[red]✗[/red]"
            self.console.print(
                f"  {icon} {pr.phase.value}: {pr.message} ({pr.duration:.1f}s)"
            )

        # Print failed tests if any
        if self._result.test_results and self._result.test_results.total_failed > 0:
            self.console.print()
            self.console.print("[bold red]Failed Tests:[/bold red]")
            for result in self._result.test_results.get_failed_tests():
                error = result.error or "unknown error"
                self.console.print(f"  [red]✗[/red] {result.test.name}: {error}")

        # Print diagnostics location if available
        if self._result.diagnostics:
            self.console.print()
            self.console.print(
                f"[bold cyan]Diagnostics:[/bold cyan] {self._result.diagnostics.output_dir}"
            )
            self.console.print(
                f"  Files collected: {len(self._result.diagnostics.collected_files)}"
            )
            if self._result.diagnostics.errors:
                self.console.print(
                    f"  [yellow]Collection errors: {len(self._result.diagnostics.errors)}[/yellow]"
                )

    def _log_phase(self, name: str) -> None:
        """Log start of a phase."""
        self.console.print()
        self.console.rule(f"[bold]{name}[/bold]")

    def _log_skip(self, what: str) -> None:
        """Log a skipped phase."""
        self.console.print()
        self.console.print(f"[dim]Skipping: {what}[/dim]")

    def _wait_for_ssh_with_progress(self, host: str, timeout: int = 300) -> bool:
        """Wait for SSH with progress feedback.

        Args:
            host: Server hostname or IP.
            timeout: Maximum wait time in seconds.

        Returns:
            True if SSH became available.
        """
        start_time = time.time()
        interval = 10
        last_status = ""

        while time.time() - start_time < timeout:
            elapsed = int(time.time() - start_time)
            remaining = timeout - elapsed

            # Check port first
            if is_port_open(host, 22, timeout=5):
                new_status = "port open, verifying connection"
                if self.verbose and new_status != last_status:
                    self.console.print(f"    [{elapsed}s] SSH {new_status}...")
                    last_status = new_status

                # Try SSH handshake
                try:
                    transport = paramiko.Transport((host, 22))
                    transport.connect()
                    transport.close()
                    if self.verbose:
                        self.console.print(
                            f"    [{elapsed}s] SSH connection successful"
                        )
                    return True
                except Exception as e:
                    if self.verbose:
                        self.console.print(
                            f"    [{elapsed}s] SSH handshake failed: {e}"
                        )
            else:
                new_status = "port closed"
                if self.verbose and new_status != last_status:
                    self.console.print(f"    [{elapsed}s] SSH {new_status}, waiting...")
                    last_status = new_status
                elif not self.verbose and elapsed % 30 == 0 and elapsed > 0:
                    # Show brief progress every 30s in non-verbose mode
                    self.console.print(f" ({elapsed}s)", end="")

            time.sleep(interval)

        return False

    def _verify_docker_installed(self, server_ip: str) -> bool:
        """Verify Docker is installed on the server.

        Args:
            server_ip: Server IP address.

        Returns:
            True if Docker is installed and working.
        """
        self.console.print("  Checking Docker installation...")

        info = SSHConnectionInfo(host=server_ip, user="root")
        conn = SSHConnection(info)

        try:
            if not conn.connect(timeout=30):
                self.console.print("    [red]SSH connection failed[/red]")
                return False

            # Check if docker command exists (use common paths since SSH may have limited PATH)
            exit_code, stdout, stderr = conn.run(
                "command -v docker || test -x /usr/bin/docker || test -x /usr/local/bin/docker",
                timeout=10,
            )
            if exit_code != 0:
                self.console.print("    [red]docker command not found[/red]")
                return False

            # Check if docker daemon is running
            exit_code, stdout, stderr = conn.run(
                "/usr/bin/docker info 2>&1 | head -5", timeout=30
            )
            if exit_code != 0:
                self.console.print("    [red]Docker daemon not running[/red]")
                self.console.print(f"    {stderr.strip()[:100]}")
                return False

            # Get Docker version
            exit_code, stdout, stderr = conn.run(
                "/usr/bin/docker --version", timeout=10
            )
            if exit_code == 0:
                version = stdout.strip()
                self.console.print(f"    Docker: {version}")

            return True

        except Exception as e:
            self.console.print(f"    [red]Error checking Docker: {e}[/red]")
            return False

        finally:
            conn.close()

    def _find_hop3_project_root(self) -> Path | None:
        """Find the Hop3 monorepo root directory.

        Returns:
            Path to project root, or None if not found.
        """
        # Check explicit config first
        if self.config.deployment.use_local_repo:
            if self.config.deployment.local_repo_path:
                return self.config.deployment.local_repo_path

        return find_project_root_optional()

    def _print_deployment_diagnostics(
        self,
        server_ip: str,
        result: DeploymentResult,
    ) -> None:
        """Print detailed diagnostics when deployment fails."""
        self.console.print()
        self.console.print("[bold red]Deployment Diagnostics[/bold red]")
        self.console.print("=" * 60)

        # Show last part of deployment log
        if result.log_output:
            log_lines = result.log_output.strip().split("\n")
            # Show last 30 lines
            recent_lines = log_lines[-30:] if len(log_lines) > 30 else log_lines
            self.console.print()
            self.console.print("[bold]Recent deployment log:[/bold]")
            for line in recent_lines:
                self.console.print(f"  {line}")

        # Try to get remote diagnostics via SSH
        self.console.print()
        self.console.print("[bold]Remote server diagnostics:[/bold]")

        info = SSHConnectionInfo(host=server_ip, user="root")
        conn = SSHConnection(info)

        try:
            if conn.connect(timeout=10):
                # Check if hop3-server service exists and its status
                exit_code, stdout, stderr = conn.run(
                    "systemctl status hop3-server 2>&1 | head -20",
                    timeout=10,
                )
                self.console.print()
                self.console.print("  [bold]hop3-server service status:[/bold]")
                for line in stdout.strip().split("\n")[:15]:
                    self.console.print(f"    {line}")

                # Check recent journal logs
                exit_code, stdout, stderr = conn.run(
                    "journalctl -u hop3-server -n 20 --no-pager 2>&1",
                    timeout=10,
                )
                if stdout.strip():
                    self.console.print()
                    self.console.print("  [bold]Recent hop3-server logs:[/bold]")
                    for line in stdout.strip().split("\n")[-15:]:
                        self.console.print(f"    {line}")

                # Check if port 8000 is listening
                exit_code, stdout, stderr = conn.run(
                    "ss -tlnp | grep :8000 || echo 'Port 8000 not listening'",
                    timeout=10,
                )
                self.console.print()
                self.console.print(f"  [bold]Port 8000 status:[/bold] {stdout.strip()}")

                # Check if nginx is running
                exit_code, stdout, stderr = conn.run(
                    "systemctl is-active nginx 2>&1",
                    timeout=10,
                )
                self.console.print(f"  [bold]Nginx status:[/bold] {stdout.strip()}")

                # Check hop3 installation
                exit_code, stdout, stderr = conn.run(
                    "ls -la /home/hop3/venv/bin/hop3-server 2>&1 || echo 'hop3-server not found'",
                    timeout=10,
                )
                self.console.print(
                    f"  [bold]hop3-server binary:[/bold] {stdout.strip()}"
                )

                # Try to import hop3-server to see full error
                exit_code, stdout, stderr = conn.run(
                    "/home/hop3/venv/bin/python3 -c 'from hop3.server.cli import main; print(\"Import OK\")' 2>&1",
                    timeout=30,
                )
                if exit_code != 0 or "Import OK" not in stdout:
                    self.console.print()
                    self.console.print(
                        "  [bold red]hop3-server import error:[/bold red]"
                    )
                    for line in (stdout + stderr).strip().split("\n")[-25:]:
                        self.console.print(f"    {line}")

            else:
                self.console.print(
                    "  [yellow]Could not connect via SSH for diagnostics[/yellow]"
                )

        except Exception as e:
            self.console.print(
                f"  [yellow]Error getting remote diagnostics: {e}[/yellow]"
            )

        finally:
            conn.close()

        self.console.print()
        self.console.print("=" * 60)


def run_daily_test(
    config: Config,
    skip_reset: bool = False,
    skip_deploy: bool = False,
    skip_tests: bool = False,
) -> DailyTestResult:
    """Run the daily system test.

    Convenience function that creates an orchestrator and runs the test.

    Args:
        config: Test configuration.
        skip_reset: Skip server reset.
        skip_deploy: Skip deployment.
        skip_tests: Skip test execution.

    Returns:
        DailyTestResult with outcomes.
    """
    orchestrator = DailyTestOrchestrator(config)
    return orchestrator.run(
        skip_reset=skip_reset,
        skip_deploy=skip_deploy,
        skip_tests=skip_tests,
    )
