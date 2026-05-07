# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Main deployment logic for Hop3."""

from __future__ import annotations

import pathlib
import shlex
import subprocess
import traceback
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from hop3_installer.common import ServiceStartError
from hop3_installer.constants import (
    DEFAULT_ADMIN_EMAIL,
    HOP3_SERVER_BIN,
)
from hop3_installer.nginx_templates import (
    generate_full_ssl_config,
    generate_http_only_config,
)

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
        self.admin_user_created = False  # Track if admin was newly created

        # Generate default log file for quiet mode
        if self.quiet and not self.log_file:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            self.log_file = Path(f"deploy-{timestamp}.log")

        # Initialize log file
        if self.log_file:
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
            # Install any requested features not yet present
            if self.config.with_features:
                step += 1
                self.log_step(step, "Installing requested features")
                if not self._install_features():
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
            # Only show password if we created a new user
            if self.admin_user_created:
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

    def _start_docker_services(self, step: int) -> tuple[bool, int]:
        """Start services in Docker via supervisor.

        Returns:
            Tuple of (success, updated_step_count).
        """
        if not self.config.use_docker:
            return True, step

        step += 1
        self.log_step(step, "Starting services (supervisor)")
        try:
            self.backend.start_services()
            self.log("Services started", "success")
            return True, step
        except ServiceStartError as e:
            self.log(f"Failed to start services: {e}", "error")
            return False, step

    def _configure_admin_domain(self, step: int) -> tuple[bool, int]:
        """Configure admin domain with nginx, SSL, and user.

        Returns:
            Tuple of (success, updated_step_count).
        """
        if not self.config.admin_domain:
            return True, step

        # Configure nginx
        step += 1
        self.log_step(step, "Configuring nginx for domain")
        if not self._setup_admin_nginx(self.config.admin_domain):
            return False, step

        # Setup SSL certificate
        step += 1
        self.log_step(step, "Setting up SSL certificate")
        self._setup_admin_ssl(self.config.admin_domain)

        # Create admin user
        step += 1
        self.log_step(step, "Creating admin user")
        self._create_admin_user()

        return True, step

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

            # Start services (supervisor in Docker, no-op for SSH/systemd)
            success, step = self._start_docker_services(step)
            if not success:
                return False

            # Configure admin domain (nginx, SSL, user)
            success, step = self._configure_admin_domain(step)
            if not success:
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
                traceback.print_exc()
            return False

    def _build_source_args(self, local_path: str | None) -> str:
        """Build installer arguments for the installation source.

        Args:
            local_path: Path on the server where local code was uploaded (if any)

        Returns:
            String of command-line arguments for the installer
        """
        if local_path:
            return f" --local-path {shlex.quote(local_path)}"

        if self.config.use_git:
            return f" --git --branch {shlex.quote(self.config.branch)}"

        # Default: install from PyPI
        args = ""
        if self.config.pypi_version:
            args += f" --version {shlex.quote(self.config.pypi_version)}"
        if self.config.pypi_pre:
            args += " --pre"
        return args

    def _ensure_python310_plus(self) -> str:
        """Ensure Python 3.10+ is available on the remote system.

        RHEL 9 clones (Rocky, AlmaLinux) ship with Python 3.9 by default,
        but Python 3.11/3.12 are available in the appstream repository.

        Returns:
            The python command to use (e.g., "python3" or "python3.11")
        """
        # Check current Python version
        result = self.backend.run(
            "python3 -c \"import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')\"",
            check=False,
        )

        if result.returncode == 0:
            version = result.stdout.strip()
            major, minor = map(int, version.split(".")[:2])
            if major >= 3 and minor >= 10:
                return "python3"

        # Check if python3.12 is available
        result = self.backend.run("command -v python3.12", check=False)
        if result.returncode == 0:
            return "python3.12"

        # Check if python3.11 is available
        result = self.backend.run("command -v python3.11", check=False)
        if result.returncode == 0:
            return "python3.11"

        # Need to install Python 3.11 or 3.12
        # Check if we're on RHEL/Rocky/AlmaLinux (dnf-based)
        result = self.backend.run("command -v dnf", check=False)
        if result.returncode == 0:
            self.log("Installing Python 3.12 (RHEL/Rocky/AlmaLinux)...")
            # Try Python 3.12 first, fall back to 3.11
            result = self.backend.run(
                "dnf install -y python3.12 python3.12-pip python3.12-devel 2>&1",
                check=False,
            )
            if result.returncode == 0:
                return "python3.12"

            result = self.backend.run(
                "dnf install -y python3.11 python3.11-pip python3.11-devel 2>&1",
                check=False,
            )
            if result.returncode == 0:
                return "python3.11"

        # Default fallback
        return "python3"

    def _install(self, *, local_path: str | None = None) -> bool:
        """Install Hop3 on the target.

        Args:
            local_path: Path on the server where local code was uploaded (if any)
        """
        # Ensure Python 3.10+ is available
        python_cmd = self._ensure_python310_plus()
        if python_cmd != "python3":
            self.log(f"Using {python_cmd} for installation")

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
        install_cmd = f"{python_cmd} -u /tmp/install-server.py"
        install_cmd += self._build_source_args(local_path)

        if self.config.with_features:
            install_cmd += f" --with {','.join(self.config.with_features)}"

        if self.config.acme_email:
            install_cmd += f" --acme-email {shlex.quote(self.config.acme_email)}"

        install_cmd += " --verbose"

        self.log(f"Running: {install_cmd}")
        if not self.quiet:
            print()

        exit_code = self.backend.run_streaming(
            install_cmd, quiet=self.quiet, log_file=self.log_file
        )

        if not self.quiet:
            print()
        else:
            print("done" if exit_code == 0 else "FAILED")

        if exit_code != 0:
            self.log(f"Installation failed (exit code {exit_code})", "error")
            return False

        self.log("Installation complete", "success")
        return True

    def _update(self) -> bool:
        """Update existing Hop3 installation."""
        # If using local code, use that instead of PyPI
        if self.config.use_local_code:
            return self._update_local_code()

        # If using git, update from git
        if self.config.use_git:
            return self._update_from_git()

        # Default: update from PyPI
        return self._update_from_pypi()

    def _install_features(self) -> bool:
        """Install additional features on an existing Hop3 installation.

        Re-runs the installer with --with flags, skipping steps unrelated
        to feature installation (nginx, postgres, acme are already configured).
        The installer is idempotent so already-installed features are skipped.
        """
        if not self.config.with_features:
            return True

        self.log(f"Installing features: {', '.join(self.config.with_features)}")

        python_cmd = self._ensure_python310_plus()

        # Upload installer script
        installer_path = self.config.installer_path
        if not installer_path.exists():
            self.log(f"Installer not found: {installer_path}", "error")
            return False

        if not self.backend.upload_file(installer_path, "/tmp/install-server.py"):
            self.log("Failed to upload installer", "error")
            return False

        # Run installer with feature flags, skipping unrelated steps
        install_cmd = f"{python_cmd} -u /tmp/install-server.py"
        install_cmd += f" --with {','.join(self.config.with_features)}"
        install_cmd += " --skip-nginx --skip-acme"
        install_cmd += " --verbose"

        self.log(f"Running: {install_cmd}")
        if not self.quiet:
            print()

        exit_code = self.backend.run_streaming(
            install_cmd, quiet=self.quiet, log_file=self.log_file
        )

        if not self.quiet:
            print()
        else:
            print("done" if exit_code == 0 else "FAILED")

        if exit_code != 0:
            self.log(f"Feature installation failed (exit code {exit_code})", "error")
            return False

        self.log("Features installed", "success")
        return True

    def _update_from_git(self) -> bool:
        """Update existing installation from git."""
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

    def _update_from_pypi(self) -> bool:
        """Update existing installation from PyPI."""
        pip = "/home/hop3/venv/bin/pip"

        # Build package spec
        if self.config.pypi_version:
            package_spec = f"hop3-server=={shlex.quote(self.config.pypi_version)}"
            self.log(f"Upgrading to version {self.config.pypi_version} from PyPI")
        else:
            package_spec = "hop3-server"
            if self.config.pypi_pre:
                self.log("Upgrading to latest (including pre-releases) from PyPI")
            else:
                self.log("Upgrading to latest stable from PyPI")

        # Build pip command
        pre_flag = (
            "--pre " if self.config.pypi_pre and not self.config.pypi_version else ""
        )
        pip_cmd = f"{pip} install --upgrade {pre_flag}{package_spec}"

        result = self.backend.run(pip_cmd, check=False)
        if not result.success:
            self.log("Failed to upgrade package", "error")
            self.log_output(result)
            return False

        # Restart server
        self.log("Restarting server")
        self.backend.run("systemctl restart hop3-server", check=False)

        self.log("Update from PyPI complete", "success")
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

    def _setup_admin_nginx(self, domain: str) -> bool:
        """Configure nginx for the admin domain.

        Updates the main hop3 nginx config (in /etc/nginx/) to use the
        specified server_name. This takes precedence over app-specific
        configs in /home/hop3/nginx/.
        """
        self.log(f"Configuring nginx for {domain}")

        # First, check if there's a conflicting app config for this domain
        app_config = f"/home/hop3/nginx/{domain}.conf"
        result = self.backend.run(f"test -f {shlex.quote(app_config)}", check=False)
        if result.success:
            self.log(f"Removing conflicting app config: {app_config}", "warning")
            self.backend.run(f"rm -f {shlex.quote(app_config)}", check=False)

        # Determine which nginx config path to use
        # Debian-based: /etc/nginx/sites-available/hop3
        # RHEL-based: /etc/nginx/conf.d/hop3.conf
        result = self.backend.run("test -d /etc/nginx/sites-available", check=False)
        if result.success:
            config_path = "/etc/nginx/sites-available/hop3"
        else:
            config_path = "/etc/nginx/conf.d/hop3.conf"

        # Generate nginx config for the admin domain
        # This proxies to the hop3-server running on port 8000
        nginx_config = generate_http_only_config(domain)
        safe_config_path = shlex.quote(config_path)

        # Write the config file using a heredoc
        write_cmd = f"cat > {safe_config_path} << 'NGINX_EOF'\n{nginx_config}NGINX_EOF"
        result = self.backend.run(write_cmd, check=False)
        if not result.success:
            self.log("Failed to write nginx config", "error")
            self.log_output(result)
            return False

        # Test nginx config
        result = self.backend.run("nginx -t", check=False)
        if not result.success:
            self.log("Nginx configuration test failed", "error")
            self.log_output(result)
            return False

        # Reload nginx
        result = self.backend.run("systemctl reload nginx", check=False)
        if not result.success:
            self.log("Failed to reload nginx", "warning")
            self.log_output(result)
        else:
            self.log(f"Nginx configured for {domain}", "success")

        return True

    def _setup_admin_ssl(self, domain: str) -> None:
        """Setup SSL certificate for the admin domain.

        Uses Let's Encrypt if a valid ACME email is provided,
        otherwise falls back to a self-signed certificate.
        """
        cert_dir = f"/home/hop3/ssl/{domain}"

        # Check if certificate already exists and is installed
        result = self.backend.run(
            f"test -f {shlex.quote(cert_dir)}/fullchain.pem", check=False
        )
        if result.success:
            self.log(f"SSL certificate already installed for {domain}", "success")
            # Update nginx config to use SSL (in case it wasn't)
            self._update_nginx_for_ssl(domain, cert_dir)
            return

        # Determine if we should use Let's Encrypt or self-signed
        use_letsencrypt = self._should_use_letsencrypt()

        if use_letsencrypt:
            success = self._request_letsencrypt_cert(domain, cert_dir)
            if success:
                return
            # Fall back to self-signed if Let's Encrypt fails
            self.log("Falling back to self-signed certificate")

        # Generate self-signed certificate
        self._generate_self_signed_cert(domain, cert_dir)

    def _should_use_letsencrypt(self) -> bool:
        """Check if we should try Let's Encrypt."""
        # Don't use Let's Encrypt if email is not provided or is the default placeholder
        if not self.config.acme_email:
            return False
        if self.config.acme_email == DEFAULT_ADMIN_EMAIL:
            return False
        if self.config.acme_email == "admin@example.com":
            return False
        if "@example.com" in self.config.acme_email:
            return False

        # Check if acme.sh is installed
        acme_sh = "/home/hop3/.acme.sh/acme.sh"
        result = self.backend.run(f"test -f {acme_sh}", check=False)
        return result.success

    def _request_letsencrypt_cert(self, domain: str, cert_dir: str) -> bool:
        """Request a Let's Encrypt certificate. Returns True on success."""
        # acme_email is guaranteed non-None by _should_use_letsencrypt() check
        assert self.config.acme_email is not None
        safe_domain = shlex.quote(domain)
        safe_email = shlex.quote(self.config.acme_email)
        acme_sh = "/home/hop3/.acme.sh/acme.sh"

        # Check if certificate exists in acme.sh but not installed
        acme_cert_dir = f"/home/hop3/.acme.sh/{domain}_ecc"
        result = self.backend.run(
            f"test -f {shlex.quote(acme_cert_dir)}/fullchain.cer", check=False
        )
        if result.success:
            self.log(f"SSL certificate exists, installing for {domain}")
            self._install_ssl_cert(domain, cert_dir)
            return True

        # No certificate exists, request a new one
        self.log(f"Requesting Let's Encrypt certificate for {domain}")

        # Ensure the ACME challenge directory exists and is writable by hop3
        acme_webroot = "/var/www/html"
        acme_challenge_dir = f"{acme_webroot}/.well-known/acme-challenge"
        self.backend.run(f"mkdir -p {acme_challenge_dir}", check=False)
        self.backend.run(f"chown -R hop3:hop3 {acme_webroot}/.well-known", check=False)
        self.backend.run(f"chmod 755 {acme_webroot}/.well-known", check=False)
        self.backend.run(f"chmod 755 {acme_challenge_dir}", check=False)

        # Issue certificate using webroot mode
        issue_cmd = (
            f"sudo -u hop3 {acme_sh} --issue "
            f"-d {safe_domain} "
            f"--webroot {acme_webroot} "
            f"--accountemail {safe_email} "
        )
        result = self.backend.run(issue_cmd, check=False)
        if not result.success:
            self.log("Failed to issue Let's Encrypt certificate", "warning")
            self.log_output(result)
            return False

        # Install the certificate
        self._install_ssl_cert(domain, cert_dir)
        return True

    def _generate_self_signed_cert(self, domain: str, cert_dir: str) -> None:
        """Generate a self-signed SSL certificate."""
        safe_cert_dir = shlex.quote(cert_dir)

        self.log(f"Generating self-signed certificate for {domain}")

        # Create cert directory
        self.backend.run(f"mkdir -p {safe_cert_dir}", check=False)
        self.backend.run("chown -R hop3:hop3 /home/hop3/ssl", check=False)

        # Generate self-signed certificate valid for 365 days
        # Note: domain is used in -subj which is already quoted by the shell
        openssl_cmd = (
            f"openssl req -x509 -nodes -days 365 -newkey rsa:2048 "
            f"-keyout {safe_cert_dir}/key.pem "
            f"-out {safe_cert_dir}/fullchain.pem "
            f"-subj '/CN={domain}/O=Hop3/C=US'"
        )
        result = self.backend.run(openssl_cmd, check=False)
        if not result.success:
            self.log("Failed to generate self-signed certificate", "error")
            self.log_output(result)
            return

        # Set proper permissions
        self.backend.run(f"chmod 600 {safe_cert_dir}/key.pem", check=False)
        self.backend.run(f"chmod 644 {safe_cert_dir}/fullchain.pem", check=False)
        self.backend.run(f"chown -R hop3:hop3 {safe_cert_dir}", check=False)

        # Update nginx config to use SSL
        self._update_nginx_for_ssl(domain, cert_dir)

        self.log(f"Self-signed certificate installed for {domain}", "success")

    def _install_ssl_cert(self, domain: str, cert_dir: str) -> None:
        """Install SSL certificate from acme.sh to the target directory."""
        safe_domain = shlex.quote(domain)
        acme_sh = "/home/hop3/.acme.sh/acme.sh"

        # Ensure cert directory exists and is owned by hop3
        self.backend.run(f"mkdir -p {shlex.quote(cert_dir)}", check=False)
        self.backend.run("chown -R hop3:hop3 /home/hop3/ssl", check=False)

        install_cmd = (
            f"sudo -u hop3 {acme_sh} --install-cert "
            f"-d {safe_domain} "
            f"--key-file {shlex.quote(cert_dir)}/key.pem "
            f"--fullchain-file {shlex.quote(cert_dir)}/fullchain.pem "
            "--reloadcmd 'sudo systemctl reload nginx'"
        )
        result = self.backend.run(install_cmd, check=False)
        if not result.success:
            self.log("Failed to install SSL certificate", "warning")
            self.log_output(result)
            return

        # Update nginx config to use SSL
        self._update_nginx_for_ssl(domain, cert_dir)

        self.log(f"SSL certificate installed for {domain}", "success")

    def _update_nginx_for_ssl(self, domain: str, cert_dir: str) -> None:
        """Update nginx config to use SSL."""
        ssl_cert = f"{cert_dir}/fullchain.pem"
        ssl_key = f"{cert_dir}/key.pem"
        nginx_config = generate_full_ssl_config(domain, ssl_cert, ssl_key)
        # Use the same config path as _setup_admin_nginx
        result = self.backend.run("test -d /etc/nginx/sites-available", check=False)
        if result.success:
            config_path = "/etc/nginx/sites-available/hop3"
        else:
            config_path = "/etc/nginx/conf.d/hop3.conf"

        safe_config_path = shlex.quote(config_path)

        write_cmd = f"cat > {safe_config_path} << 'NGINX_EOF'\n{nginx_config}NGINX_EOF"
        result = self.backend.run(write_cmd, check=False)
        if not result.success:
            self.log("Failed to update nginx config for SSL", "warning")
            return

        self.backend.run("systemctl reload nginx", check=False)

    def _create_admin_user(self) -> None:
        """Create the admin user if it doesn't already exist."""
        user = self.config.admin_user
        email = self.config.admin_email
        password = self.config.admin_password

        # Quote all user-controlled values. Password is fed via stdin
        # below, so it doesn't need (and must not get) shell quoting.
        safe_user = shlex.quote(user)
        safe_email = shlex.quote(email)
        hop3_server = str(HOP3_SERVER_BIN)

        # Check if admin user already exists
        check_cmd = f"sudo -u hop3 {hop3_server} admin:list | grep -q '^{user} '"
        result = self.backend.run(check_cmd, check=False)
        user_exists = result.success

        if user_exists:
            self.log(f"Admin user '{user}' already exists", "success")
            return

        # User doesn't exist - create it
        self.log(f"Creating admin user '{user}'")
        # SECURITY: pipe the password via subprocess stdin, not via the
        # shell ``echo {pw} | sudo …`` form. The latter puts the password
        # in the spawned ``echo``'s argv (visible in /proc/<pid>/cmdline
        # for the deploy window). The remote command reads it from its
        # own stdin via --password-stdin.
        cmd = (
            f"sudo -u hop3 {hop3_server} "
            f"admin:create {safe_user} {safe_email} --password-stdin"
        )
        result = self.backend.run(cmd, check=False, stdin=password)
        if result.success:
            self.admin_user_created = True
            self.log(f"Admin user '{user}' created", "success")
        else:
            self.log("Failed to create admin user", "warning")
            self.log_output(result)

    def _setup_cli(self) -> None:
        """Configure local CLI to connect to the deployed server."""
        try:
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

            # Quote user-controlled values to prevent command injection.
            # The password no longer flows through argv; see _create_admin_user.
            safe_user = shlex.quote(user)
            safe_email = shlex.quote(f"{user}@hop3.dev")

            # Create admin user on server using --password-stdin (ignore if already exists).
            # See _create_admin_user above for the stdin-vs-echo rationale.
            hop3_server = str(HOP3_SERVER_BIN)
            self.backend.run(
                f"sudo -u hop3 {hop3_server} "
                f"admin:create {safe_user} {safe_email} --password-stdin",
                check=False,
                stdin=password,
            )

            # Get token from server (admin:token only needs username)
            result = self.backend.run(
                f"sudo -u hop3 {hop3_server} admin:token {safe_user}",
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
        from .backends.docker import DockerDeployBackend  # noqa: PLC0415

        return DockerDeployBackend(config)

    from .backends.ssh import SSHDeployBackend  # noqa: PLC0415

    return SSHDeployBackend(config)


def deploy(config: DeployConfig) -> bool:
    """Run deployment with the given config.

    This is the main entry point for programmatic use.
    """
    backend = create_backend(config)
    deployer = Deployer(config, backend)
    return deployer.deploy()
