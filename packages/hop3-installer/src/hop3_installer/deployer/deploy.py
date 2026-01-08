# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Main deployment logic for Hop3."""

from __future__ import annotations

import pathlib
import shlex
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .backends.base import DeployBackend
    from .config import DeployConfig


class Deployer:
    """Handles Hop3 deployment to various targets."""

    def __init__(self, config: DeployConfig, backend: DeployBackend):
        self.config = config
        self.backend = backend
        self.verbose = config.verbose
        self.quiet = config.quiet
        self.log_file = config.log_file

        # Generate default log file for quiet mode
        if self.quiet and not self.log_file:
            from datetime import datetime
            from pathlib import Path

            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            self.log_file = Path(f"deploy-{timestamp}.log")

        # Initialize log file
        if self.log_file:
            from datetime import datetime

            with Path(self.log_file).open("w") as f:
                f.write(f"Hop3 Deployment Log - {datetime.now().isoformat()}\n")
                f.write("=" * 60 + "\n\n")

    def log(self, message: str, level: str = "info") -> None:
        """Print log message."""
        prefix = {
            "info": "→",
            "success": "✓",
            "warning": "⚠",
            "error": "✗",
        }.get(level, "→")

        formatted = f"  {prefix} {message}"

        # Always log to file if available
        if self.log_file:
            with pathlib.Path(self.log_file).open("a") as f:
                f.write(formatted + "\n")

        # Print to terminal unless quiet (but always show errors)
        if not self.quiet or level == "error":
            print(formatted)

    def log_step(self, step: int, message: str) -> None:
        """Print step message."""
        formatted = f"\n[{step}] {message}"

        if self.log_file:
            with pathlib.Path(self.log_file).open("a") as f:
                f.write(formatted + "\n")

        if not self.quiet:
            print(formatted)
        else:
            # In quiet mode, show minimal progress
            print(f"  [{step}] {message}...", end=" ", flush=True)

    def log_output(self, result, *, always: bool = False) -> None:
        """Print command output.

        Args:
            result: CommandResult from backend.run()
            always: If True, show output even on success (for verbose mode)
        """
        # Always show output on failure, or when verbose and always=True
        show_stdout = result.stdout.strip() and (
            not result.success or (self.verbose and always)
        )
        show_stderr = result.stderr.strip() and (
            not result.success or (self.verbose and always)
        )

        if show_stdout:
            print("\n  --- stdout ---")
            for line in result.stdout.strip().splitlines():
                print(f"  {line}")
        if show_stderr:
            print("\n  --- stderr ---")
            for line in result.stderr.strip().splitlines():
                print(f"  {line}")
        if show_stdout or show_stderr:
            print()

    def _handle_install_or_update(
        self, step: int, local_path_on_server: str | None
    ) -> tuple[bool, int]:
        """Handle installation or update logic.

        Returns:
            Tuple of (success, updated_step_count).
        """
        if self.config.skip_install:
            step += 1
            self.log_step(step, "Skipping installation (--skip-install)")
            # Even with skip_install, update local code if requested
            if self.config.use_local_code:
                step += 1
                self.log_step(step, "Updating with local code")
                if not self._update_local_code():
                    return False, step
        elif self.backend.is_hop3_installed():
            step += 1
            self.log_step(step, "Updating existing installation")
            if not self._update():
                return False, step
        else:
            step += 1
            self.log_step(step, "Installing Hop3")
            if not self._install(local_path=local_path_on_server):
                return False, step

        return True, step

    def _print_completion_message(self) -> None:
        """Print deployment completion message."""
        if self.quiet:
            print(f"\n✓ Deployment complete. Server: {self.backend.get_server_url()}")
            if self.log_file:
                print(f"  Log file: {self.log_file}")
            return

        print("\n" + "=" * 60)
        print("Deployment complete!")
        print(f"Server URL: {self.backend.get_server_url()}")

        if self.config.admin_domain:
            print(f"Admin URL: https://{self.config.admin_domain}")
            print(f"Admin user: {self.config.admin_user}")
            # Only show full password in verbose mode to avoid CI log exposure
            if self.verbose:
                print(f"Admin password: {self.config.admin_password}")
            else:
                # Show masked password with hint
                masked = (
                    self.config.admin_password[:4]
                    + "..."
                    + self.config.admin_password[-4:]
                )
                print(f"Admin password: {masked} (use --verbose to show full)")

        print("=" * 60)

    def _setup_and_prepare(self) -> tuple[bool, int, str | None]:
        """Setup backend and prepare for deployment.

        Returns:
            Tuple of (success, step_count, local_path_on_server).
        """
        step = 0

        # Setup backend
        step += 1
        self.log_step(step, "Setting up deployment target")
        if not self.backend.setup():
            self.log("Failed to setup deployment target", "error")
            return False, step, None
        self.log("Target ready", "success")

        # Clean if requested
        if self.config.clean_before:
            step += 1
            self.log_step(step, "Cleaning previous installation")
            self.backend.clean()
            self.log("Clean complete", "success")

        # Upload local code FIRST if using local code for fresh install
        local_path_on_server = None
        if self.config.use_local_code and not self.backend.is_hop3_installed():
            step += 1
            self.log_step(step, "Uploading local code for installation")
            local_path_on_server = self._upload_local_code_for_install()
            if not local_path_on_server:
                return False, step, None

        return True, step, local_path_on_server

    def deploy(self) -> bool:
        """Run full deployment.

        Returns:
            True if deployment succeeded
        """
        try:
            # Setup and prepare
            success, step, local_path_on_server = self._setup_and_prepare()
            if not success:
                return False

            # Install or update
            success, step = self._handle_install_or_update(step, local_path_on_server)
            if not success:
                return False

            # Setup admin user
            if self.config.admin_domain:
                step += 1
                self.log_step(step, "Setting up admin user")
                if not self._setup_admin():
                    return False

            # Setup CLI
            if not self.config.no_cli_setup:
                step += 1
                self.log_step(step, "Configuring local CLI")
                self._setup_cli()

            self._print_completion_message()
            return True

        except Exception as e:
            self.log(f"Deployment failed: {e}", "error")
            if self.verbose:
                import traceback

                traceback.print_exc()
            return False

    def _install(self, *, local_path: str | None = None) -> bool:
        """Install Hop3 on the target.

        Args:
            local_path: Path on the server where local code was uploaded (if any)
        """
        # Upload installer script
        installer_path = self.config.installer_path
        if not installer_path.exists():
            self.log(f"Installer not found: {installer_path}", "error")
            return False

        self.log("Uploading installer script")
        if not self.backend.upload_file(installer_path, "/tmp/install-server.py"):
            self.log("Failed to upload installer", "error")
            return False

        # Build install command
        # Use -u for unbuffered output so we can stream progress
        install_cmd = "python3 -u /tmp/install-server.py"

        # Use local path if provided (for --local flag)
        if local_path:
            install_cmd += f" --local-path {shlex.quote(local_path)}"
        elif self.config.branch != "devel":
            # Quote branch name to prevent command injection
            install_cmd += f" --git --branch {shlex.quote(self.config.branch)}"

        if self.config.with_features:
            install_cmd += f" --with {','.join(self.config.with_features)}"

        # Always use verbose for better error output
        install_cmd += " --verbose"

        self.log(f"Running: {install_cmd}")
        if not self.quiet:
            print()  # Blank line before streaming output

        # Use streaming to show real-time progress
        exit_code = self.backend.run_streaming(
            install_cmd, quiet=self.quiet, log_file=self.log_file
        )

        if not self.quiet:
            print()  # Blank line after streaming output
        else:
            # In quiet mode, log_step left cursor waiting - print result
            print("done" if exit_code == 0 else "FAILED")

        if exit_code != 0:
            self.log(f"Installation failed (exit code {exit_code})", "error")
            return False

        self.log("Installation complete", "success")
        return True

    def _update(self) -> bool:
        """Update existing Hop3 installation."""
        # If using local code, use that instead of git
        if self.config.use_local_code:
            return self._update_local_code()

        self.log("Pulling latest code from git")

        # Quote branch name to prevent command injection
        safe_branch = shlex.quote(self.config.branch)

        # Update from git
        update_commands = [
            "cd /home/hop3/hop3 && git fetch origin",
            f"cd /home/hop3/hop3 && git checkout {safe_branch}",
            f"cd /home/hop3/hop3 && git reset --hard origin/{safe_branch}",
            "cd /home/hop3/hop3 && /home/hop3/venv/bin/pip install -e packages/hop3-server",
            "systemctl restart hop3-server",
        ]

        for cmd in update_commands:
            if self.verbose:
                self.log(f"Running: {cmd}")
            result = self.backend.run(cmd, check=False)
            if not result.success:
                self.log(f"Update command failed: {cmd}", "error")
                self.log_output(result)
                return False

        self.log("Update complete", "success")
        return True

    def _upload_local_code_for_install(self) -> str | None:
        """Upload local code to a temp location for fresh install.

        Returns:
            Path on server where code was uploaded, or None on failure
        """
        server_pkg = self.config.server_package_path

        if not server_pkg.exists():
            self.log(f"Server package not found: {server_pkg}", "error")
            return None

        remote_path = "/tmp/hop3-server"

        self.log(f"Uploading {server_pkg} to {remote_path}")
        if not self.backend.upload_dir(server_pkg, remote_path):
            self.log("Failed to upload code", "error")
            return None

        self.log("Local code uploaded", "success")
        return remote_path

    def _update_local_code(self) -> bool:
        """Update an existing installation with local code."""
        server_pkg = self.config.server_package_path

        if not server_pkg.exists():
            self.log(f"Server package not found: {server_pkg}", "error")
            return False

        # Upload to temp location first
        remote_path = "/tmp/hop3-server"
        self.log(f"Uploading {server_pkg}")
        if not self.backend.upload_dir(server_pkg, remote_path):
            self.log("Failed to upload code", "error")
            return False

        # Install from uploaded code
        self.log("Installing from uploaded code")
        result = self.backend.run(
            f"/home/hop3/venv/bin/pip install --upgrade {remote_path}",
            check=False,
        )
        if not result.success:
            self.log("Failed to install package", "error")
            self.log_output(result)
            return False

        # Restart server
        self.log("Restarting server")
        self.backend.run("systemctl restart hop3-server", check=False)

        self.log("Local code deployed", "success")
        return True

    def _setup_admin(self) -> bool:
        """Setup admin user and domain."""
        domain = self.config.admin_domain
        if not domain:
            self.log("No admin domain configured, skipping admin setup")
            return True

        user = self.config.admin_user
        email = self.config.admin_email
        password = self.config.admin_password

        self.log(f"Creating admin domain: {domain}")

        # Quote all user-controlled values to prevent command injection
        safe_domain = shlex.quote(domain)
        safe_user = shlex.quote(user)
        safe_email = shlex.quote(email)
        safe_password = shlex.quote(password)

        # Create admin app
        commands = [
            f"sudo -u hop3 /home/hop3/venv/bin/hop3-server apps:create {safe_domain}",
            (
                f"sudo -u hop3 /home/hop3/venv/bin/hop3-server users:create "
                f"--admin {safe_user} {safe_email} {safe_password}"
            ),
        ]

        for cmd in commands:
            result = self.backend.run(cmd, check=False)
            if not result.success:
                # Non-fatal - admin might already exist
                self.log(f"Command returned non-zero (may be OK): {cmd}", "warning")
                if result.stderr.strip():
                    self.log_output(result)

        self.log("Admin setup complete", "success")
        return True

    def _setup_cli(self) -> None:
        """Configure local CLI to connect to the deployed server."""
        try:
            import subprocess

            # Try to configure hop3 CLI
            host = self.config.host or "localhost"
            # Build the full API URL
            api_url = f"http://{host}:8000" if "://" not in host else host
            subprocess.run(
                ["hop3", "settings", "set", "server", api_url],
                capture_output=True,
                check=False,
            )

            # Create admin user and get token for CLI authentication
            user = self.config.admin_user
            password = self.config.admin_password

            # Quote user-controlled values to prevent command injection
            safe_user = shlex.quote(user)
            safe_password = shlex.quote(password)
            safe_email = shlex.quote(f"{user}@hop3.dev")

            # Create admin user on server using --password-stdin (ignore if already exists)
            self.backend.run(
                f"echo {safe_password} | sudo -u hop3 /home/hop3/venv/bin/hop3-server "
                f"admin:create {safe_user} {safe_email} --password-stdin",
                check=False,
            )

            # Get token from server (admin:token only needs username)
            result = self.backend.run(
                f"sudo -u hop3 /home/hop3/venv/bin/hop3-server admin:token {safe_user}",
                check=False,
            )

            if result.success and result.stdout.strip():
                # Parse token from output - JWT tokens start with "eyJ"
                token = None
                for line in result.stdout.strip().splitlines():
                    line = line.strip()
                    if line.startswith("eyJ"):
                        token = line
                        break

                if token:
                    # Set token in local CLI config
                    subprocess.run(
                        ["hop3", "settings", "set", "token", token],
                        capture_output=True,
                        check=False,
                    )
                    self.log("CLI configured with authentication token", "success")
                else:
                    self.log(
                        "Could not parse auth token from output (no JWT found)",
                        "warning",
                    )
            else:
                self.log("Could not get auth token (check server logs)", "warning")

            self.log(f"CLI configured to connect to {api_url}", "success")
        except FileNotFoundError:
            self.log("hop3 CLI not found, skipping CLI setup", "warning")


def create_backend(config: DeployConfig) -> DeployBackend:
    """Create appropriate backend based on config."""
    if config.use_docker:
        from .backends.docker import DockerDeployBackend

        return DockerDeployBackend(config)

    from .backends.ssh import SSHDeployBackend

    return SSHDeployBackend(config)


def deploy(config: DeployConfig) -> bool:
    """Run deployment with the given config.

    This is the main entry point for programmatic use.
    """
    backend = create_backend(config)
    deployer = Deployer(config, backend)
    return deployer.deploy()
