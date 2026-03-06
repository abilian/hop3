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
        self.admin_user_created = False  # Track if admin was newly created

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

            # Configure nginx for admin domain
            if self.config.admin_domain:
                step += 1
                self.log_step(step, "Configuring nginx for domain")
                if not self._setup_admin_nginx(self.config.admin_domain):
                    return False

            # Setup SSL certificate
            if self.config.admin_domain and self.config.acme_email:
                step += 1
                self.log_step(step, "Setting up SSL certificate")
                self._setup_admin_ssl(self.config.admin_domain)

            # Create admin user
            if self.config.admin_domain:
                step += 1
                self.log_step(step, "Creating admin user")
                self._create_admin_user()

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
        install_cmd = "python3 -u /tmp/install-server.py"
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
        result = self.backend.run(
            "test -d /etc/nginx/sites-available", check=False
        )
        if result.success:
            config_path = "/etc/nginx/sites-available/hop3"
        else:
            config_path = "/etc/nginx/conf.d/hop3.conf"

        # Generate nginx config for the admin domain
        # This proxies to the hop3-server running on port 8000
        nginx_config = f"""# Hop3 Server - Reverse Proxy Configuration
# Auto-generated by hop3-deploy for {domain}

# Redirect HTTP to HTTPS (except ACME challenges)
server {{
    listen 80;
    server_name {domain};

    location /.well-known/acme-challenge/ {{
        root /var/www/html;
    }}

    location / {{
        # Proxy to hop3-server (allows HTTP until SSL is configured)
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;

        # WebSocket support
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }}
}}
"""
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
        """Setup SSL certificate using acme.sh."""
        safe_domain = shlex.quote(domain)
        safe_email = shlex.quote(self.config.acme_email)
        acme_sh = "/home/hop3/.acme.sh/acme.sh"

        # Check if acme.sh is installed
        result = self.backend.run(f"test -f {acme_sh}", check=False)
        if not result.success:
            self.log("acme.sh not installed, skipping SSL setup", "warning")
            return

        # Check if certificate already exists and is installed
        cert_dir = f"/home/hop3/ssl/{domain}"
        result = self.backend.run(
            f"test -f {shlex.quote(cert_dir)}/fullchain.pem", check=False
        )
        if result.success:
            self.log(f"SSL certificate already installed for {domain}", "success")
            # Update nginx config to use SSL (in case it wasn't)
            self._update_nginx_for_ssl(domain, cert_dir)
            return

        # Check if certificate exists in acme.sh but not installed
        acme_cert_dir = f"/home/hop3/.acme.sh/{domain}_ecc"
        result = self.backend.run(
            f"test -f {shlex.quote(acme_cert_dir)}/fullchain.cer", check=False
        )
        if result.success:
            self.log(f"SSL certificate exists, installing for {domain}")
            # Just install, don't request new cert
            self._install_ssl_cert(domain, cert_dir)
            return

        # No certificate exists, request a new one
        self.log(f"Requesting new SSL certificate for {domain}")

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
            self.log("Failed to issue SSL certificate", "warning")
            self.log_output(result)
            return

        # Install the certificate
        self._install_ssl_cert(domain, cert_dir)

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
        nginx_config = f"""# Hop3 Server - Reverse Proxy Configuration
# Auto-generated by hop3-deploy for {domain} (with SSL)

# Redirect HTTP to HTTPS
server {{
    listen 80;
    server_name {domain};

    location /.well-known/acme-challenge/ {{
        root /var/www/html;
    }}

    location / {{
        return 301 https://$host$request_uri;
    }}
}}

# HTTPS server
server {{
    listen 443 ssl http2;
    server_name {domain};

    ssl_certificate {cert_dir}/fullchain.pem;
    ssl_certificate_key {cert_dir}/key.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;

    location / {{
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;

        # WebSocket support
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }}

    location /.well-known/acme-challenge/ {{
        root /var/www/html;
    }}
}}
"""
        # Use the same config path as _setup_admin_nginx
        result = self.backend.run(
            "test -d /etc/nginx/sites-available", check=False
        )
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

        # Quote all user-controlled values
        safe_user = shlex.quote(user)
        safe_email = shlex.quote(email)
        safe_password = shlex.quote(password)
        hop3_server = "/home/hop3/venv/bin/hop3-server"

        # Check if admin user already exists
        check_cmd = f"sudo -u hop3 {hop3_server} admin:list | grep -q '^{user} '"
        result = self.backend.run(check_cmd, check=False)
        user_exists = result.success

        if user_exists:
            self.log(f"Admin user '{user}' already exists", "success")
            return

        # User doesn't exist - create it
        self.log(f"Creating admin user '{user}'")
        cmd = (
            f"echo {safe_password} | sudo -u hop3 {hop3_server} "
            f"admin:create {safe_user} {safe_email} --password-stdin"
        )
        result = self.backend.run(cmd, check=False)
        if result.success:
            self.admin_user_created = True
            self.log(f"Admin user '{user}' created", "success")
        else:
            self.log("Failed to create admin user", "warning")
            self.log_output(result)

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
