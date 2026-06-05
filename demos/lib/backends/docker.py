# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Docker backend for demo execution in local containers."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from .base import CommandResult, DemoBackend


class DockerDemoBackend(DemoBackend):
    """Backend for executing demos in local Docker containers.

    This backend creates a Docker container with systemd support
    for realistic testing of Hop3 server installation.

    When systemd isn't available (basic mode), it provides fallback
    service management using direct process execution.
    """

    name = "docker"

    def __init__(
        self,
        container_name: str = "hop3-demo",
        image: str = "ubuntu:24.04",
        project_root: Path | None = None,
        port_offset: int = 10000,
    ):
        """Initialize Docker backend.

        Args:
            container_name: Name for the Docker container
            image: Docker image to use
            project_root: Path to hop3 project root (for mounting)
            port_offset: Offset for port mappings to avoid conflicts (default: 10000)
        """
        self.container_name = container_name
        self.image = image
        self.project_root = project_root or Path(__file__).parent.parent.parent.parent
        self._container_ip: str | None = None
        self.port_offset = port_offset
        # Port mappings: host_port:container_port
        self.port_server = 8000 + port_offset  # Hop3 server (18000:8000)
        self.port_http = 80 + port_offset  # HTTP (10080:80)
        self.port_https = 443 + port_offset  # HTTPS (10443:443)
        # Track if systemd is available
        self._has_systemd = False

    def _docker_available(self) -> bool:
        """Check if Docker is available."""
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                text=True,
                check=False,
            )
            return result.returncode == 0
        except FileNotFoundError:
            return False

    def _container_exists(self) -> bool:
        """Check if the container exists."""
        result = subprocess.run(
            ["docker", "ps", "-a", "--filter", f"name=^{self.container_name}$", "-q"],
            capture_output=True,
            text=True,
            check=False,
        )
        return bool(result.stdout.strip())

    def _container_running(self) -> bool:
        """Check if the container is running."""
        result = subprocess.run(
            ["docker", "ps", "--filter", f"name=^{self.container_name}$", "-q"],
            capture_output=True,
            text=True,
            check=False,
        )
        return bool(result.stdout.strip())

    def _remove_container(self) -> None:
        """Remove the container if it exists."""
        subprocess.run(
            ["docker", "rm", "-f", self.container_name],
            capture_output=True,
            check=False,
        )

    def _get_container_ip(self) -> str | None:
        """Get the container's internal IP address."""
        result = subprocess.run(
            [
                "docker",
                "inspect",
                "-f",
                "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
                self.container_name,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return None

    def _check_systemd(self) -> bool:
        """Check if systemd is running as PID 1 and responding."""
        # First check if PID 1 is systemd
        result = self.run("cat /proc/1/comm 2>/dev/null", check=False)
        if not result.success or "systemd" not in result.stdout:
            return False
        # Then check if systemctl works
        result = self.run(
            "systemctl is-system-running 2>/dev/null || true", check=False
        )
        # Accept "running", "degraded", or "starting" as valid states
        return any(
            state in result.stdout
            for state in ["running", "degraded", "starting", "initializing"]
        )

    @property
    def has_systemd(self) -> bool:
        """Return whether systemd is available in this container."""
        return self._has_systemd

    def setup(self) -> bool:
        """Start Docker container for demo execution."""
        if not self._docker_available():
            print("  ✗ Docker is not available")
            return False

        # Always remove existing container first
        self._remove_container()

        # Try systemd mode with proper flags for macOS Docker Desktop
        # The key additions are --tmpfs mounts needed for systemd
        print("  → Starting container with systemd...")
        systemd_result = subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                self.container_name,
                "--privileged",
                "--cgroupns=host",
                "-v",
                "/sys/fs/cgroup:/sys/fs/cgroup:rw",
                "--tmpfs",
                "/run",
                "--tmpfs",
                "/run/lock",
                "-v",
                f"{self.project_root}:/hop3:ro",
                "-p",
                f"{self.port_server}:8000",
                "-p",
                f"{self.port_http}:80",
                "-p",
                f"{self.port_https}:443",
                self.image,
                "/lib/systemd/systemd",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        if systemd_result.returncode == 0:
            # Wait for systemd to initialize
            time.sleep(2)
            # Verify systemd is running
            if self._check_systemd():
                self._has_systemd = True
                print("  ✓ Systemd mode enabled")
            else:
                print("  → Systemd not responding, falling back...")
                self._remove_container()
                systemd_result.returncode = 1  # Force fallback

        if systemd_result.returncode != 0:
            # Remove failed container before retry
            self._remove_container()

            # Try basic mode with supervisor for service management
            print("  → Using basic mode with supervisor...")
            basic_result = subprocess.run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    self.container_name,
                    "-v",
                    f"{self.project_root}:/hop3:ro",
                    "-p",
                    f"{self.port_server}:8000",
                    "-p",
                    f"{self.port_http}:80",
                    "-p",
                    f"{self.port_https}:443",
                    self.image,
                    "sleep",
                    "infinity",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            if basic_result.returncode != 0:
                print("  ✗ Failed to start container")
                if basic_result.stderr:
                    print(f"  Error: {basic_result.stderr.strip()}")
                return False

            self._has_systemd = False

        # Wait for container to be ready
        for _ in range(30):
            if self._container_running():
                break
            time.sleep(0.5)
        else:
            print("  ✗ Container failed to start within timeout")
            return False

        # Get container IP
        self._container_ip = self._get_container_ip()

        # Install base packages (with retry for fresh containers)
        print("  → Installing base packages in container...")

        # Base packages needed for Hop3
        base_packages = "python3 python3-venv python3-pip git curl sudo ca-certificates"

        # In basic mode (no systemd), we also need supervisor for service management
        if not self._has_systemd:
            base_packages += " supervisor"

        install_cmd = (
            "export DEBIAN_FRONTEND=noninteractive && "
            "apt-get update -qq && "
            f"apt-get install -y -qq --no-install-recommends {base_packages} 2>&1"
        )
        result = self.run(install_cmd, check=False)
        if not result.success:
            # Try fixing broken packages first
            print("  → Fixing package dependencies...")
            self.run("apt --fix-broken install -y 2>&1 || true", check=False)
            result = self.run(install_cmd, check=False)
            if not result.success:
                print("  ✗ Failed to install base packages")
                print(f"  Error: {result.stderr}")
                return False

        # If using supervisor, start it
        if not self._has_systemd:
            print("  → Starting supervisor...")
            # Create supervisor directory and start it
            self.run("mkdir -p /var/log/supervisor", check=False)
            self.run("mkdir -p /etc/supervisor/conf.d", check=False)
            # Start supervisord in background
            self.run(
                "supervisord -c /etc/supervisor/supervisord.conf 2>&1 || true",
                check=False,
            )

        # Install database services for demos that need them
        self._install_database_services()

        print("  ✓ Container ready")
        return True

    def _install_database_services(self) -> None:
        """Install PostgreSQL, Redis, and MySQL packages for demos that need them.

        Note: This only installs packages. Supervisor config is set up later
        by configure_database_supervisor() after the Hop3 installer runs.
        """
        # Install PostgreSQL
        print("  → Installing PostgreSQL...")
        self.run(
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq postgresql postgresql-contrib 2>&1",
            check=False,
        )

        # Install Redis
        print("  → Installing Redis...")
        self.run(
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq redis-server 2>&1",
            check=False,
        )

        # Install MySQL/MariaDB
        print("  → Installing MariaDB...")
        self.run(
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq mariadb-server 2>&1",
            check=False,
        )

    def configure_database_supervisor(self) -> None:
        """Configure database services under supervisor after Hop3 installer runs.

        This should be called AFTER install_hop3() because the installer may start
        database services itself. We stop them and transfer control to supervisor.
        """
        if self._has_systemd:
            # With systemd, services are already managed properly
            return

        # Stop any services that might be running (started by installer or init scripts)
        self.run(
            "service postgresql stop 2>&1 || true; "
            "service redis-server stop 2>&1 || true; "
            "service mariadb stop 2>&1 || true; "
            # Force kill any remaining processes
            "pkill -9 -x postgres 2>&1 || true; "
            "pkill -9 -x redis-server 2>&1 || true; "
            "pkill -9 -x mariadbd 2>&1 || true; "
            "pkill -9 -x mysqld 2>&1 || true; "
            # Clean up stale PID files
            "rm -f /var/lib/postgresql/*/main/postmaster.pid 2>&1 || true; "
            "rm -f /var/run/redis/redis-server.pid 2>&1 || true; "
            "rm -f /var/run/mysqld/mysqld.pid 2>&1 || true; "
            "sleep 2",
            check=False,
        )

        # Configure supervisor for database services
        self._ensure_supervisor_config("postgresql")
        self._ensure_supervisor_config("redis-server")
        self._ensure_supervisor_config("mysql")

        # Reload supervisor to pick up new configs
        self.run(
            "supervisorctl reread && supervisorctl update 2>&1 || true", check=False
        )

        # Explicitly start the services
        self.run(
            "supervisorctl start postgresql redis-server mysql 2>&1 || true",
            check=False,
        )

        # Wait for services to be ready and verify
        self.run("sleep 3", check=False)

        # Create PostgreSQL user (service must be running)
        self.run(
            'su - postgres -c "psql -c \\"CREATE USER hop3 WITH PASSWORD \'hop3\' CREATEDB SUPERUSER;\\"" 2>&1 || true',
            check=False,
        )
        # Configure pg_hba.conf for trust auth (for addons to work)
        # Allow local socket connections and localhost (both IPv4 and IPv6) without password
        self.run(
            # First, backup and modify pg_hba.conf to use trust for local connections
            "PG_HBA=$(ls /etc/postgresql/*/main/pg_hba.conf 2>/dev/null | head -1) && "
            'if [ -f "$PG_HBA" ]; then '
            '  cp "$PG_HBA" "$PG_HBA.bak" && '
            # Replace default authentication with trust for local connections
            "  sed -i 's/^local\\s*all\\s*all\\s*peer/local all all trust/' \"$PG_HBA\" && "
            "  sed -i 's/^host\\s*all\\s*all\\s*127.0.0.1\\/32\\s*scram-sha-256/host all all 127.0.0.1\\/32 trust/' \"$PG_HBA\" && "
            "  sed -i 's/^host\\s*all\\s*all\\s*::1\\/128\\s*scram-sha-256/host all all ::1\\/128 trust/' \"$PG_HBA\" && "
            "  supervisorctl restart postgresql 2>&1; "
            "fi || true",
            check=False,
        )
        # Wait for PostgreSQL to restart
        self.run("sleep 2", check=False)

        # Create MariaDB users (service must be running)
        # First, create the hop3 superuser with full privileges
        self.run(
            "mysql -e \"CREATE USER IF NOT EXISTS 'hop3'@'localhost' IDENTIFIED BY 'hop3'; "
            "GRANT ALL PRIVILEGES ON *.* TO 'hop3'@'localhost' WITH GRANT OPTION; "
            'FLUSH PRIVILEGES;" 2>&1 || true',
            check=False,
        )
        # Also set root password for mysql_native_password auth (some tools expect root)
        self.run(
            "mysql -e \"ALTER USER 'root'@'localhost' IDENTIFIED BY 'root'; "
            'FLUSH PRIVILEGES;" 2>&1 || true',
            check=False,
        )

        # Configure MySQL credentials in hop3-server.toml (required for addon system)
        # Note: Variables are MYSQL_SUPERUSER (default root) and MYSQL_SUPERUSER_PASSWORD
        self.run(
            "grep -q MYSQL_SUPERUSER_PASSWORD /home/hop3/hop3-server.toml || ( "
            "echo 'MYSQL_SUPERUSER = \"hop3\"' >> /home/hop3/hop3-server.toml && "
            "echo 'MYSQL_SUPERUSER_PASSWORD = \"hop3\"' >> /home/hop3/hop3-server.toml "
            ")",
            check=False,
        )

    def configure_rootd_supervisor(self) -> None:
        """Start hop3-rootd under supervisor after the installer runs.

        Call AFTER install_hop3() and BEFORE any deploy. On non-systemd
        containers the installer does host prep but can't activate the daemon
        (it ships as systemd units), so we run it under supervisor here. The
        deploy path requires rootd for nginx reloads (ADR 041). Mirrors
        configure_database_supervisor.
        """
        if self._has_systemd:
            # With systemd, the installer already started the unit.
            return

        self._ensure_supervisor_config("hop3-rootd")
        self.run(
            "supervisorctl reread && supervisorctl update 2>&1 || true", check=False
        )
        self.run("supervisorctl start hop3-rootd 2>&1 || true", check=False)
        self.run("sleep 1", check=False)

    def teardown(self) -> None:
        """Stop and remove the container."""
        subprocess.run(
            ["docker", "rm", "-f", self.container_name],
            capture_output=True,
            check=False,
        )

    def run(self, command: str, *, check: bool = True) -> CommandResult:
        """Run a command in the container."""
        docker_cmd = [
            "docker",
            "exec",
            self.container_name,
            "bash",
            "-c",
            command,
        ]

        result = subprocess.run(
            docker_cmd,
            capture_output=True,
            text=True,
            check=False,
        )

        cmd_result = CommandResult(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )

        if check and not cmd_result.success:
            msg = (
                f"Docker exec failed: {command}\n"
                f"Exit code: {result.returncode}\n"
                f"stderr: {result.stderr}"
            )
            raise RuntimeError(msg)

        return cmd_result

    def run_streaming(self, command: str) -> int:
        """Run a command with output streamed to terminal."""
        docker_cmd = [
            "docker",
            "exec",
            "-e",
            "PYTHONUNBUFFERED=1",
            "-e",
            "DEBIAN_FRONTEND=noninteractive",
            self.container_name,
            "bash",
            "-c",
            command,
        ]

        result = subprocess.run(docker_cmd, check=False)
        return result.returncode

    def upload_file(self, local_path: Path, remote_path: str) -> bool:
        """Copy a file into the container."""
        result = subprocess.run(
            ["docker", "cp", str(local_path), f"{self.container_name}:{remote_path}"],
            capture_output=True,
            check=False,
        )
        return result.returncode == 0

    def upload_dir(self, local_path: Path, remote_path: str) -> bool:
        """Copy a directory into the container."""
        result = subprocess.run(
            ["docker", "cp", str(local_path), f"{self.container_name}:{remote_path}"],
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            # Fix permissions
            self.run(f"chmod -R a+rX {remote_path}", check=False)
        return result.returncode == 0

    def is_hop3_installed(self) -> bool:
        """Check if Hop3 is installed."""
        result = self.run("test -f /home/hop3/venv/bin/hop3-server", check=False)
        return result.success

    def get_server_ip(self) -> str:
        """Get the container IP or localhost."""
        return self._container_ip or "localhost"

    def get_server_url(self) -> str:
        """Get the URL to access the server."""
        # Use localhost with mapped port
        return f"http://localhost:{self.port_server}"

    def start_service(self, service_name: str) -> bool:
        """Start a service using systemd or supervisor.

        Args:
            service_name: Name of the service (e.g., 'hop3-server', 'nginx')

        Returns:
            True if service started successfully
        """
        if self._has_systemd:
            result = self.run(f"systemctl start {service_name}", check=False)
            return result.success
        # Use supervisor in basic mode
        # First, create supervisor config if it doesn't exist
        self._ensure_supervisor_config(service_name)
        result = self.run(f"supervisorctl start {service_name}", check=False)
        return result.success or "ALREADY_STARTED" in result.stdout

    def stop_service(self, service_name: str) -> bool:
        """Stop a service using systemd or supervisor."""
        if self._has_systemd:
            result = self.run(f"systemctl stop {service_name}", check=False)
            return result.success
        result = self.run(f"supervisorctl stop {service_name}", check=False)
        return result.success or "NOT_RUNNING" in result.stdout

    def restart_service(self, service_name: str) -> bool:
        """Restart a service using systemd or supervisor."""
        if self._has_systemd:
            result = self.run(f"systemctl restart {service_name}", check=False)
            return result.success
        # For supervisor, stop then start
        self.stop_service(service_name)
        return self.start_service(service_name)

    def reload_service(self, service_name: str) -> bool:
        """Reload a service configuration."""
        if self._has_systemd:
            result = self.run(f"systemctl reload {service_name}", check=False)
            return result.success
        # For supervisor, just restart
        return self.restart_service(service_name)

    def service_status(self, service_name: str) -> str:
        """Get service status."""
        if self._has_systemd:
            result = self.run(
                f"systemctl is-active {service_name} 2>/dev/null || echo 'unknown'",
                check=False,
            )
            return result.stdout.strip()
        result = self.run(
            f"supervisorctl status {service_name} 2>/dev/null | awk '{{print $2}}' || echo 'unknown'",
            check=False,
        )
        status = result.stdout.strip().lower()
        if "running" in status:
            return "active"
        if "stopped" in status:
            return "inactive"
        return status or "unknown"

    def _ensure_supervisor_config(self, service_name: str) -> None:
        """Create supervisor config for a service if it doesn't exist."""
        config_path = f"/etc/supervisor/conf.d/{service_name}.conf"

        # Check if config already exists
        result = self.run(f"test -f {config_path}", check=False)
        if result.success:
            return

        # Create config based on service type
        if service_name == "hop3-server":
            # Note: hop3-server serve doesn't take --host/--port args
            # It uses configuration from hop3-server.toml
            config = """[program:hop3-server]
command=/home/hop3/venv/bin/hop3-server serve
user=hop3
directory=/home/hop3
autostart=true
autorestart=true
stderr_logfile=/var/log/supervisor/hop3-server.err.log
stdout_logfile=/var/log/supervisor/hop3-server.out.log
environment=HOME="/home/hop3",PATH="/home/hop3/venv/bin:%(ENV_PATH)s"
"""
        elif service_name == "nginx":
            config = """[program:nginx]
command=/usr/sbin/nginx -g 'daemon off;'
autostart=true
autorestart=true
stderr_logfile=/var/log/supervisor/nginx.err.log
stdout_logfile=/var/log/supervisor/nginx.out.log
"""
        elif service_name == "hop3-rootd":
            # Privileged-operations daemon (ADR 041). Runs as root (no user=)
            # so it can reload nginx; hop3-server connects to its socket as the
            # hop3 user (SO_PEERCRED admits hop3 + root). The container has no
            # systemd, so the installer only did host prep — we activate here.
            config = """[program:hop3-rootd]
command=/home/hop3/venv/bin/hop3-rootd --socket-path /run/hop3-rootd/socket
autostart=true
autorestart=true
stderr_logfile=/var/log/supervisor/hop3-rootd.err.log
stdout_logfile=/var/log/supervisor/hop3-rootd.out.log
"""
        elif service_name == "uwsgi-hop3":
            # uWSGI Emperor to manage app workers
            config = """[program:uwsgi-hop3]
command=/home/hop3/venv/bin/uwsgi --emperor /home/hop3/uwsgi-enabled --stats /tmp/hop3-uwsgi-stats.sock
user=hop3
directory=/home/hop3
autostart=true
autorestart=true
stderr_logfile=/var/log/supervisor/uwsgi-hop3.err.log
stdout_logfile=/var/log/supervisor/uwsgi-hop3.out.log
environment=HOME="/home/hop3",PATH="/home/hop3/venv/bin:%(ENV_PATH)s"
"""
        elif service_name == "postgresql":
            # PostgreSQL database server
            config = """[program:postgresql]
command=/usr/lib/postgresql/16/bin/postgres -D /var/lib/postgresql/16/main -c config_file=/etc/postgresql/16/main/postgresql.conf
user=postgres
autostart=true
autorestart=true
stderr_logfile=/var/log/supervisor/postgresql.err.log
stdout_logfile=/var/log/supervisor/postgresql.out.log
"""
        elif service_name == "redis-server":
            # Redis in-memory data store
            config = """[program:redis-server]
command=/usr/bin/redis-server --daemonize no
autostart=true
autorestart=true
stderr_logfile=/var/log/supervisor/redis.err.log
stdout_logfile=/var/log/supervisor/redis.out.log
"""
        elif service_name == "mysql":
            # MariaDB/MySQL database server (named 'mysql' for compatibility)
            config = """[program:mysql]
command=/usr/bin/mariadbd-safe
autostart=true
autorestart=true
stderr_logfile=/var/log/supervisor/mysql.err.log
stdout_logfile=/var/log/supervisor/mysql.out.log
"""
        else:
            # Generic config - won't work for all services
            return

        # Write config and reload supervisor
        escaped_config = config.replace("'", "'\\''")
        self.run(f"echo '{escaped_config}' > {config_path}", check=False)
        self.run("supervisorctl reread && supervisorctl update", check=False)

    def clean(self) -> None:
        """Clean the container for fresh installation."""
        commands = [
            "systemctl stop hop3-server 2>/dev/null || true",
            "systemctl stop uwsgi-hop3 2>/dev/null || true",
            "rm -rf /home/hop3",
            "userdel -r hop3 2>/dev/null || true",
            "groupdel hop3 2>/dev/null || true",
        ]

        for cmd in commands:
            self.run(cmd, check=False)
