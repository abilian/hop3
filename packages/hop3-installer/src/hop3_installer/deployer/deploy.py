# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Main deployment logic for Hop3."""

from __future__ import annotations

import json
import pathlib
import re
import shlex
import subprocess
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from hop3_installer.common import (
    CommandResult,
    GitProvenance,
    ServiceStartError,
    collect_git_provenance,
    make_build_info,
)
from hop3_installer.constants import (
    BUILD_INFO_PATH,
    DEFAULT_ADMIN_EMAIL,
    HOP3_SERVER_BIN,
    HOP3_SERVER_BIND,
    VENV_DIR,
)
from hop3_installer.nginx_templates import (
    generate_full_ssl_config,
    generate_http_only_config,
)

if TYPE_CHECKING:
    from .backends.base import DeployBackend
    from .config import DeployConfig


# Post-restart health check. Migrations run BEFORE the restart (see
# _run_migrations), so a healthy server only has to boot here — not migrate —
# and 15 x 2s = 30s is ample. A slow-but-healthy start that overruns the budget
# fails loud and never auto-reverts, so erring short is the safe direction.
_HEALTH_RETRIES = 15
_HEALTH_DELAY_S = 2.0
_HEALTH_PROBE_TIMEOUT_S = 3

#: What one release of Hop3 puts in the server venv. Every update path installs
#: all three at one version and then checks that it did: rootd and cli used to
#: be left at the old version beside a new server, and a botched upload once
#: reinstalled the old server under a green message.
_VERSIONED_PACKAGES = ("hop3-server", "hop3-rootd", "hop3-cli")
_VERSION_PROBE = (
    "import importlib.metadata as m\n"
    "for p in ('hop3_server', 'hop3_rootd', 'hop3_cli'):\n"
    "    try:\n"
    "        print(p, m.version(p))\n"
    "    except m.PackageNotFoundError:\n"
    "        print(p, '')\n"
)


# The context a `--docker` deploy writes for the container it just set up.
#
# NOT `default`, which this used to claim. `hop3 login` writes `default` only
# when it is free, and refuses to repoint an existing one at another server —
# the deployer passed `--context default` explicitly, which skips that guard
# and silently moved an operator's `default` onto the box being deployed. A
# name of its own cannot collide with one a person chose.
#
# Only Docker. An SSH deploy configures no CLI at all: the address worth
# talking to is `https://<admin-domain>`, whose certificate may not be trusted
# from here, and working that out — HTTPS or an SSH tunnel, and saying which —
# is what `hop3 login <target>` already does. Re-deciding it here with
# `--token --url` is the second implementation of one contract that this
# codebase keeps paying for.
CLI_CONTEXT_NAME = "hop3-docker"


class Deployer:
    """Handles Hop3 deployment to various targets."""

    def __init__(self, config: DeployConfig, backend: DeployBackend) -> None:
        self.config = config
        self.backend = backend
        self.verbose = config.verbose
        self.quiet = config.quiet
        self.log_file = config.log_file
        self.admin_user_created = False  # Track if admin was newly created
        # Set by `_login_local_cli` when it signs this machine's CLI in. The
        # closing banner reads it: having written the `default` context itself,
        # the deployer must not then tell the operator to run a plain
        # `hop3 login <target>`, which that very context makes the CLI refuse.
        self.cli_context_server: str | None = None

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

    def log_output(self, result: CommandResult, *, always: bool = False) -> None:
        """
        Print command output.

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
        """
        Handle installation or update logic.

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

            # Ensure the process manager exists BEFORE restarting through it.
            #
            # `_start_docker_services` runs after this block, which is fine for a
            # fresh install but leaves the update path restarting hop3-server via
            # a supervisor that may never have been set up. A deploy that died
            # between installing and starting services — an installer that exited
            # non-zero, say — left a box that answers `is_hop3_installed()` with
            # yes and has no supervisor at all. Every later run then took this
            # branch and failed identically on
            # "unix:///var/run/supervisor.sock no such file", with no way out but
            # `--clean`. Idempotent (reread+update when supervisord is already
            # running) and a no-op on systemd targets, so it costs nothing in the
            # normal case and un-sticks the broken one.
            try:
                self.backend.start_services()
            except ServiceStartError as e:
                self.log(f"Could not start services before updating: {e}", "error")
                return False, step

            if not self._update():
                return False, step
            # Install any requested features not yet present
            if self.config.install_features:
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

        # The server's own URL, not the API port it listens on. `hop3-server`
        # binds 0.0.0.0:8000 in clear, and printing that as "Server URL" both
        # advertises an address that should not be reached from off the box
        # and invites pasting it somewhere a bearer token will follow. nginx
        # in front of it is the address an operator has any business using.
        admin_domain = self.config.effective_admin_domain
        if admin_domain:
            print(f"Server URL: https://{admin_domain}")
        else:
            print(f"Server URL: {self.backend.get_server_url()}")

        self._print_how_to_log_in()
        print("=" * 60)

    def _print_how_to_log_in(self) -> None:
        """
        Give the operator one command to run, and say why it needs no password.

        One command, not two. The CLI login and the dashboard link look like a
        pair and are not: both travel over SSH, and only the first is a login —
        the second prints a URL. Offering them as two bullets taught a symmetry
        that does not exist, so the dashboard link is mentioned in prose, after
        the one command that actually has to be run.

        The generated admin password comes last because it opens neither.
        Leading with it sent operators hunting for a way to recover a secret
        they never had to hold.

        A Docker target has no SSH target to name and its CLI was configured in
        place by `_setup_cli`, so it gets no login block.

        One command shape throughout. An earlier version gave a bare login on
        one line and `--context <name>` on the next without saying they were
        the same command, then a third spelling for the browser — three shapes
        for one operation, and the reader has to work out which parts compose.
        Here the login is stated once and each variation is an added flag.

        What `--context` does is spelled out. "sign in under a name of its
        own" does not tell a reader that the name is theirs to invent and that
        the flag creates the context.
        """
        if self.config.use_docker or not self.config.host:
            return

        target = self.config.ssh_target
        print()
        print("Sign in from this machine — your SSH access to the server is")
        print("the credential, so there is no password to type:")
        print()
        print(f"  hop3 login {target}")
        print()
        print("`hop3 apps` and the rest then work from here. That files the")
        print("server under the CLI context named 'default'. If you already")
        print("have a 'default' pointing somewhere else, Hop3 says so rather")
        print("than moving it, and you give this one a name of your choosing:")
        print()
        print(f"  hop3 login {target} --context hop3-dev")
        print()
        print("For the dashboard in a browser, add --browser to either command:")
        print("it prints a one-time sign-in link instead.")
        print()
        print(f"Admin user: {self.config.admin_user}")

        if not self.admin_user_created:
            return
        # SECURITY: never a partially-masked form (e.g. first-4 + last-4).
        # Even small fractions of a secret narrow a brute-force search; show
        # all of it under --verbose so the operator can capture it, or none.
        if self.verbose:
            print(f"Admin password: {self.config.admin_password}")
            return
        # "re-run with --verbose" did not say re-run *what*, and "to set one
        # you know" read as an instruction rather than an option nobody has to
        # take. Neither sign-in above needs this password: both authenticate
        # over SSH. It exists for the dashboard's own form, later.
        print("Admin password: not shown (re-run this deploy with --verbose to")
        print("  print it). You do not need it to sign in — both commands above")
        print("  authenticate over SSH. To replace it with one you choose, sign")
        print("  in first, then:")
        print(f"    hop3 user set-password {self.config.admin_user} --stdin")

    def _setup_and_prepare(self) -> tuple[bool, int, str | None]:
        """
        Setup backend and prepare for deployment.

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
        """
        Start services in Docker via supervisor.

        Returns:
            Tuple of (success, updated_step_count).
        """
        if not self.config.use_docker:
            return True, step

        step += 1
        self.log_step(step, "Starting services (supervisor)")
        try:
            self.backend.start_services()
        except ServiceStartError as e:
            self.log(f"Failed to start services: {e}", "error")
            return False, step
        # supervisord reports RUNNING once it has forked the process, seconds
        # before the server answers; the CLI login that follows ran in that
        # window and failed with "Could not connect".
        if not self._wait_until_server_healthy():
            self.log(
                f"hop3-server did not answer on {HOP3_SERVER_BIND} after start; "
                "see `supervisorctl tail hop3-server stderr` in the container",
                "error",
            )
            return False, step
        self.log("Services started", "success")
        return True, step

    def _configure_admin_domain(self, step: int) -> tuple[bool, int]:
        """
        Configure admin domain with nginx, SSL, and user.

        Returns:
            Tuple of (success, updated_step_count).
        """
        admin_domain = self.config.effective_admin_domain
        if not admin_domain:
            return True, step

        # Configure nginx
        step += 1
        self.log_step(step, "Configuring nginx for domain")
        if not self._setup_admin_nginx(admin_domain):
            return False, step

        # Setup SSL certificate
        step += 1
        self.log_step(step, "Setting up SSL certificate")
        if not self._setup_admin_ssl(admin_domain):
            return False, step

        # Create admin user
        step += 1
        self.log_step(step, "Creating admin user")
        if not self._create_admin_user():
            return False, step

        # Tell the server its own public domain, so it emits https://<domain>
        # magic links and `hop3 addon expose` URLs instead of http://host:8000.
        step += 1
        self.log_step(step, "Recording admin domain in server config")
        if not self._persist_admin_domain(admin_domain):
            return False, step

        return True, step

    def _persist_admin_domain(self, domain: str) -> bool:
        """
        Record ``ADMIN_DOMAIN`` in the server config (``hop3-server.toml``).

        The deployer fronts the domain in nginx, but the server reads its own
        canonical domain from ``ADMIN_DOMAIN`` in ``/home/hop3/hop3-server.toml``.
        Without it the server doesn't know its public URL, so ``auth:magic-link``
        returns a bare token and the CLI falls back to ``http://<host>:8000`` —
        even though TLS fronts the dashboard at the domain. Idempotent
        (update-or-append); preserves file ownership.
        """
        cfg = "/home/hop3/hop3-server.toml"
        # ``domain`` already passed RFC-1035 validation in _setup_admin_nginx, so
        # it is only [A-Za-z0-9.-] — safe to embed in the sed/printf below.
        line = f'ADMIN_DOMAIN = "{domain}"'
        script = (
            f'set -e; f={shlex.quote(cfg)}; touch "$f"; '
            f"if grep -q '^ADMIN_DOMAIN' \"$f\"; then "
            f"sed -i 's|^ADMIN_DOMAIN.*|{line}|' \"$f\"; "
            f"else printf '\\n# Admin UI domain (set by hop3-deploy)\\n%s\\n' "
            f"'{line}' >> \"$f\"; fi; "
            f'chown hop3:hop3 "$f"'
        )
        result = self.backend.run(script, check=False)
        if not result.success:
            self.log("Failed to record ADMIN_DOMAIN in server config", "error")
            self.log_output(result, always=True)
            return False
        # Restart so the running server (addon-expose URLs, etc.) sees the new
        # value, and verify it comes back up: this is the LAST restart before the
        # deploy reports success, so an unverified one would let a dead server be
        # reported as "Deployment complete".
        restart = self.backend.service_restart_command("hop3-server")
        recovery = f"remove or fix ADMIN_DOMAIN in {cfg} and run {restart}"
        if not self._restart_and_verify("setting the admin domain", recovery):
            return False
        self.log(f"Server ADMIN_DOMAIN set to {domain}", "success")
        return True

    def deploy(self) -> bool:
        """
        Run full deployment.

        Returns:
            True if deployment succeeded
        """
        try:
            # Announce what's being deployed (commit/branch) up front so the
            # deploy log is self-documenting.
            self._log_deploy_provenance()

            # Setup and prepare
            success, step, local_path_on_server = self._setup_and_prepare()
            if not success:
                return False

            # Install or update
            success, step = self._handle_install_or_update(step, local_path_on_server)
            if not success:
                return False

            # Services (supervisor in Docker, no-op for SSH/systemd), the admin
            # domain (nginx, SSL, user), then the local CLI.
            for run_step in (
                self._start_docker_services,
                self._configure_admin_domain,
                self._configure_local_cli,
            ):
                success, step = run_step(step)
                if not success:
                    return False

            # Record deploy provenance (commit/branch/method) on the server so
            # `hop3 system info` can report exactly what's running.
            self._write_build_info()

            self._print_completion_message()
            return True

        except Exception as e:
            self.log(f"Deployment failed: {e}", "error")
            if self.verbose:
                traceback.print_exc()
            return False

    def _build_source_args(self, local_path: str | None) -> str:
        """
        Build installer arguments for the installation source.

        Args:
            local_path: Path on the server where local code was uploaded (if any)

        Returns:
            String of command-line arguments for the installer
        """
        # Canonical installer spellings (ADR 052): --path / --from git. The
        # deployer must NOT pass the deprecated --local-path/--git or the server
        # installer prints a deprecation warning into every deploy log for the
        # platform's own internal call (self-inflicted; R2 lockstep).
        if local_path:
            return f" --path {shlex.quote(local_path)}"

        if self.config.use_git:
            return f" --from git --branch {shlex.quote(self.config.branch)}"

        # Default: install from PyPI
        args = ""
        if self.config.pypi_version:
            args += f" --version {shlex.quote(self.config.pypi_version)}"
        if self.config.pypi_pre:
            args += " --pre"
        return args

    def _ensure_python310_plus(self) -> str:
        """
        Ensure Python 3.10+ is available on the remote system.

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
        """
        Install Hop3 on the target.

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

        if self.config.install_features:
            install_cmd += f" --with {','.join(self.config.install_features)}"

        if self.config.acme_email:
            install_cmd += f" --acme-email {shlex.quote(self.config.acme_email)}"

        # OPERATOR_EMAIL resolves recipes' `[admin].email = "operator"` (ADR 056);
        # forward the admin email so admin-bootstrap apps can deploy.
        if self.config.admin_email:
            install_cmd += f" --operator-email {shlex.quote(self.config.admin_email)}"

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

    def _feature_install_command(self, python_cmd: str) -> str:
        """
        Build the installer command for the feature/redeploy path.

        Forwards ``--acme-email`` so the cert *engine* is configured in
        ``/etc/default/hop3`` (the default is self-signed — it is NOT
        necessarily "already configured", which the old code wrongly assumed,
        silently dropping the flag). ``--skip-acme`` is kept: cert *issuance*
        stays on the explicit ``hop3 cert renew`` path rather than running
        certbot on every redeploy (which would hammer Let's Encrypt limits).
        """
        cmd = f"{python_cmd} -u /tmp/install-server.py"
        if self.config.install_features:
            cmd += f" --with {','.join(self.config.install_features)}"
        cmd += " --skip-nginx --skip-acme --skip-package-install"
        if self.config.acme_email:
            cmd += f" --acme-email {shlex.quote(self.config.acme_email)}"
        if self.config.admin_email:
            cmd += f" --operator-email {shlex.quote(self.config.admin_email)}"
        cmd += " --verbose"
        return cmd

    def _install_features(self) -> bool:
        """
        Install additional features on an existing Hop3 installation.

        Re-runs the installer with --with flags, skipping steps unrelated to
        feature installation (nginx, package install). ``--acme-email`` is
        forwarded so the cert engine is configured; the installer is idempotent
        so already-installed features are skipped.
        """
        if not self.config.install_features:
            return True

        self.log(f"Installing features: {', '.join(self.config.install_features)}")

        python_cmd = self._ensure_python310_plus()

        # Upload installer script
        installer_path = self.config.installer_path
        if not installer_path.exists():
            self.log(f"Installer not found: {installer_path}", "error")
            return False

        if not self.backend.upload_file(installer_path, "/tmp/install-server.py"):
            self.log("Failed to upload installer", "error")
            return False

        # Run installer with feature flags, skipping unrelated steps.
        # --skip-package-install is critical: without it, this step
        # reinstalls hop3-server from PyPI, clobbering whatever the
        # preceding _update() just installed (local code, specific git
        # branch, or specific PyPI version).
        install_cmd = self._feature_install_command(python_cmd)

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

    def _run_migrations(self) -> bool:
        """
        Run database migrations via ``hop3-server db:upgrade``.

        Called after the new package is installed but before the server is
        restarted, so a failed migration leaves the old server still
        running on the old schema.

        Returns:
            True if migrations succeeded (or were skipped).
        """
        if self.config.skip_migrations:
            self.log("Skipping migrations (--skip-migrations)", "info")
            return True

        self.log("Running database migrations")
        hop3_server = str(HOP3_SERVER_BIN)
        result = self.backend.run(
            f"sudo -u hop3 {hop3_server} db:upgrade",
            check=False,
        )
        if not result.success:
            self.log("Database migration failed — server NOT restarted", "error")
            self.log_output(result)
            return False

        self.log("Migrations applied", "success")
        return True

    def _restart_and_verify(self, what: str, recovery: str) -> bool:
        """
        Restart hop3-server and confirm it answers HTTP.

        Returns True when the server comes back up. On failure logs loudly (with
        the recovery path) and returns False — a restart that starts the systemd
        unit but leaves the server crashing must never be reported as success,
        wherever in the deploy it happens. The caller logs its own success
        message only once this returns True.
        """
        self.log("Restarting server")
        result = self.backend.restart_service("hop3-server")

        if self._wait_until_server_healthy():
            return True

        self.log(f"Server did NOT come back up after {what}.", "error")

        # The restart command's own output, which used to be dropped. When the
        # restart itself was refused — supervisord not running, so supervisorctl
        # answered "unix:///var/run/supervisor.sock no such file" — that one line
        # is the whole diagnosis, and none of it reached the operator.
        if not result.success:
            self.log(
                f"  The restart command failed: "
                f"{self.backend.service_restart_command('hop3-server')}",
                "error",
            )
            self.log_output(result, always=True)

        self.log(f"  Recover: {recovery}", "error")
        self.log(
            f"  Diagnose: {self.backend.service_logs_command('hop3-server')}", "error"
        )
        return False

    @staticmethod
    def _upgrade_recovery(revert: str) -> str:
        """
        Recovery guidance for a failed upgrade: how to revert, plus the
        forward-only-migration caveat (reverting code may not be enough).
        """
        # Intentional: kept as a named one-caller helper — names the concept for
        # _finish_upgrade rather than inlining the two-line string.
        return (
            f"{revert}. A forward-migrated schema may also require restoring a "
            "pre-upgrade database backup."
        )

    def _finish_upgrade(self, revert: str, success_msg: str) -> bool:
        """
        Shared tail of every upgrade path: restart rootd, restart the server,
        verify it answers, report. Returns False (fail loud) if either does not
        come back.
        """
        recovery = self._upgrade_recovery(revert)
        if not self._restart_rootd(recovery):
            return False
        if not self._restart_and_verify("the upgrade", recovery):
            return False
        self.log(success_msg, "success")
        return True

    def _restart_rootd(self, recovery: str) -> bool:
        """
        Restart the privileged daemon so it runs the code just installed.

        The server calls rootd for every nginx reload and, since 0.7.3, for
        service reloads. A daemon left at the old version answers the new
        server's ops with "no such op", at the next deploy, far from here.
        """
        self.log("Restarting hop3-rootd")
        result = self.backend.restart_service("hop3-rootd")
        if result.success:
            return True
        self.log(
            "hop3-rootd did not restart: "
            f"{self.backend.service_restart_command('hop3-rootd')}",
            "error",
        )
        self.log_output(result, always=True)
        self.log(f"  Recover: {recovery}", "error")
        self.log(
            f"  Diagnose: {self.backend.service_logs_command('hop3-rootd')}", "error"
        )
        return False

    def _installed_versions(self) -> dict[str, str]:
        """The version of each Hop3 package in the server venv, "" when absent."""
        probe = f"{VENV_DIR}/bin/python -c {shlex.quote(_VERSION_PROBE)}"
        result = self.backend.run(probe, check=False)
        versions = dict.fromkeys(_VERSIONED_PACKAGES, "")
        for line in (result.stdout or "").splitlines():
            name, _, version = line.strip().partition(" ")
            name = name.replace("_", "-")
            if name in versions:
                versions[name] = version.strip()
        return versions

    def _check_one_version(self, expected: str | None) -> bool:
        """
        Fail loud unless the venv holds hop3-server, hop3-rootd and hop3-cli at
        one version, and at ``expected`` when the caller knows what it installed.

        Runs after the install and before the migrations, so a wrong install
        aborts with the old server still running on the old schema.
        """
        versions = self._installed_versions()
        found = set(versions.values())
        consistent = len(found) == 1 and "" not in found
        if consistent and (expected is None or found == {expected}):
            self.log(
                f"hop3-server, hop3-rootd and hop3-cli at {found.pop()}", "success"
            )
            return True
        self.log("The server venv does not hold one version of Hop3:", "error")
        for name, version in versions.items():
            self.log(f"  {name}: {version or 'not installed'}", "error")
        if expected:
            self.log(f"  expected: {expected}", "error")
        return False

    @staticmethod
    def _package_version(pyproject: Path) -> str:
        """The ``version`` a package's pyproject declares (fail loud if none)."""
        match = re.search(
            r'^version\s*=\s*"([^"]+)"', pyproject.read_text(), re.MULTILINE
        )
        if not match:
            msg = f'{pyproject}: no version = "..." line'
            raise ValueError(msg)
        return match.group(1)

    def _wait_until_server_healthy(
        self, retries: int = _HEALTH_RETRIES, delay: float = _HEALTH_DELAY_S
    ) -> bool:
        """
        Poll until hop3-server answers HTTP on its bind address, or give up.

        Any HTTP response (even a 404/redirect) means the process is up and
        serving; connection-refused / timeout means it never came back. Never a
        false *positive* — curl only exits 0 when the server actually answered.
        """
        url = f"http://{HOP3_SERVER_BIND}/"
        probe = f"curl -s -o /dev/null -m {_HEALTH_PROBE_TIMEOUT_S} {url}"
        for _ in range(retries):
            if self.backend.run(probe, check=False).success:
                return True
            time.sleep(delay)
        return False

    def _update_from_git(self) -> bool:
        """Update existing installation from git."""
        self.log("Pulling latest code from git")

        # Quote branch name to prevent command injection
        safe_branch = shlex.quote(self.config.branch)

        # Capture the current commit BEFORE `reset --hard`, so a broken upgrade
        # can point the operator at the exact release to revert to.
        head = self.backend.run("cd /home/hop3/hop3 && git rev-parse HEAD", check=False)
        # Intentional double .strip(): degrade the hint to "" when HEAD is empty
        # or whitespace, not only when the command itself fails.
        old_ref = head.stdout.strip() if head.success and head.stdout.strip() else ""

        # Install the new code before running migrations and restarting.
        # Migrations run between install and restart so a schema mismatch
        # aborts the deploy with the OLD server still running.
        update_commands = [
            "cd /home/hop3/hop3 && git fetch origin",
            f"cd /home/hop3/hop3 && git checkout {safe_branch}",
            f"cd /home/hop3/hop3 && git reset --hard origin/{safe_branch}",
            # [waf] extra: install the LeWAF engine by default (ADR 050). No-op on
            # <3.12 (marker-gated); without it, WAF-enabled apps abort the deploy.
            "cd /home/hop3/hop3 && /home/hop3/venv/bin/pip install -e 'packages/hop3-server[waf]'",
            # The daemon and the client ride along at the same commit.
            "cd /home/hop3/hop3 && /home/hop3/venv/bin/pip install -e packages/hop3-rootd -e packages/hop3-cli",
        ]

        for cmd in update_commands:
            if self.verbose:
                self.log(f"Running: {cmd}")
            result = self.backend.run(cmd, check=False)
            if not result.success:
                self.log(f"Update command failed: {cmd}", "error")
                self.log_output(result)
                return False

        declared = self.backend.run(
            "grep -m1 '^version' /home/hop3/hop3/packages/hop3-server/pyproject.toml",
            check=False,
        )
        found = re.search(r'"([^"]+)"', declared.stdout or "")
        if not self._check_one_version(found.group(1) if found else None):
            return False

        if not self._run_migrations():
            return False

        ref = old_ref or "<previous commit>"
        restart = self.backend.service_restart_command("hop3-server")
        revert = (
            f"cd /home/hop3/hop3 && git reset --hard {ref} && "
            "/home/hop3/venv/bin/pip install -e 'packages/hop3-server[waf]' "
            f"-e packages/hop3-rootd -e packages/hop3-cli && {restart}"
        )
        return self._finish_upgrade(revert, "Update complete")

    def _update_from_pypi(self) -> bool:
        """Update existing installation from PyPI."""
        pip = "/home/hop3/venv/bin/pip"

        # Capture the installed version BEFORE upgrading, for the revert hint.
        show = self.backend.run(f"{pip} show hop3-server", check=False)
        old_version = ""
        if show.success:
            for line in show.stdout.splitlines():
                if line.lower().startswith("version:"):
                    old_version = line.split(":", 1)[1].strip()
                    break

        # Build package spec
        if self.config.pypi_version:
            pinned = shlex.quote(self.config.pypi_version)
            package_spec = " ".join(f"{p}=={pinned}" for p in _VERSIONED_PACKAGES)
            self.log(f"Upgrading to version {self.config.pypi_version} from PyPI")
        else:
            package_spec = " ".join(_VERSIONED_PACKAGES)
            if self.config.pypi_pre:
                self.log("Upgrading to latest (including pre-releases) from PyPI")
            else:
                self.log("Upgrading to latest stable from PyPI")

        # Build pip command
        pre_flag = (
            "--pre " if self.config.pypi_pre and not self.config.pypi_version else ""
        )
        pip_cmd = (
            f"{pip} install --upgrade --upgrade-strategy=eager {pre_flag}{package_spec}"
        )

        result = self.backend.run(pip_cmd, check=False)
        if not result.success:
            self.log("Failed to upgrade package", "error")
            self.log_output(result)
            return False

        if not self._check_one_version(self.config.pypi_version):
            return False

        if not self._run_migrations():
            return False

        version = old_version or "<previous-version>"
        restart = self.backend.service_restart_command("hop3-server")
        revert = (
            f"{pip} install "
            + " ".join(f"{p}=={version}" for p in _VERSIONED_PACKAGES)
            + f" && {restart} "
            "(the upgrade bumped dependencies eagerly; if the old server still "
            "fails, reinstall into a fresh venv)"
        )
        return self._finish_upgrade(revert, "Update from PyPI complete")

    def _upload_local_code_for_install(self) -> str | None:
        """
        Upload local code to a temp location for fresh install.

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

        # Sibling packages the installer needs: hop3-rootd (the deploy path uses
        # it for nginx reloads) and hop3-cli (so the server has the `hop3` client
        # for on-server tutorial deploys). Without rootd the install aborts at
        # the rootd step.
        if not (self._upload_rootd_package() and self._upload_cli_package()):
            return None

        self.log("Local code uploaded", "success")
        return remote_path

    def _upload_rootd_package(self) -> bool:
        """
        Upload the hop3-rootd package to /tmp/hop3-rootd (sibling of server).

        Returns True on success (or success-with-warning if the package dir is
        absent — older checkouts), False only on a transfer failure.
        """
        rootd_pkg = self.config.rootd_package_path
        if not rootd_pkg.exists():
            # The installer would abort at its rootd step, after changing the box.
            self.log(
                f"hop3-rootd package not found at {rootd_pkg}: the daemon is "
                "required for deploys (nginx reloads)",
                "error",
            )
            return False
        self.log(f"Uploading {rootd_pkg} to /tmp/hop3-rootd")
        if not self.backend.upload_dir(rootd_pkg, "/tmp/hop3-rootd"):
            self.log("Failed to upload hop3-rootd", "error")
            return False
        return True

    def _upload_cli_package(self) -> bool:
        """
        Upload the hop3-cli package to /tmp/hop3-cli (sibling of server).

        Returns True on success (or success-with-warning if the package dir is
        absent — older checkouts), False only on a transfer failure.
        """
        cli_pkg = self.config.cli_package_path
        if not cli_pkg.exists():
            self.log(
                f"hop3-cli package not found at {cli_pkg}; the server won't have "
                "the `hop3` client, so on-server tutorial tests can't deploy.",
                "warning",
            )
            return True
        self.log(f"Uploading {cli_pkg} to /tmp/hop3-cli")
        if not self.backend.upload_dir(cli_pkg, "/tmp/hop3-cli"):
            self.log("Failed to upload hop3-cli", "error")
            return False
        return True

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

        # Upload the sibling packages the installer needs: hop3-rootd (nginx
        # reloads) and hop3-cli (on-server tutorial deploys).
        if not (self._upload_rootd_package() and self._upload_cli_package()):
            return False

        if not self._install_uploaded_code(server_pkg, remote_path):
            return False

        if not self._run_migrations():
            return False

        revert = "re-deploy the previous local checkout: hop3-deploy-server --local"
        return self._finish_upgrade(revert, "Local code deployed")

    def _install_uploaded_code(self, server_pkg: Path, remote_path: str) -> bool:
        """Install the uploaded server, daemon and client, and check the venv holds one version."""
        # Uninstall the existing hop3-server *first*, so the install step
        # writes a fresh .dist-info directory. Without this, repeated
        # --local deploys can leave stale metadata: the new code lands in
        # site-packages/hop3/ but the dist-info dir keeps the old version,
        # so importlib.metadata.version("hop3_server") (used by
        # `hop3 system info` and elsewhere) reports a stale value.
        # `pip uninstall` only removes the named package, never its deps,
        # so this is fast.
        self.log("Removing stale metadata")
        self.backend.run(
            "/home/hop3/venv/bin/pip uninstall -y hop3-server",
            check=False,
        )

        # Install from uploaded code. --upgrade-strategy=eager bumps
        # transitive deps (e.g. litestar) when the new package uses APIs
        # from a newer version. Without it, a >=X.Y.Z pin that the server
        # already satisfies at the old floor leaves stale deps in place
        # and the import fails at runtime.
        self.log("Installing from uploaded code")
        result = self.backend.run(
            "/home/hop3/venv/bin/pip install "
            # [waf] extra: LeWAF engine (ADR 050), marker-gated to py3.12+.
            f"--upgrade --upgrade-strategy=eager '{remote_path}[waf]'",
            check=False,
        )
        if not result.success:
            self.log("Failed to install package", "error")
            self.log_output(result)
            return False

        self.log("Installing hop3-rootd and hop3-cli from uploaded code")
        result = self.backend.run(
            "/home/hop3/venv/bin/pip install --upgrade --upgrade-strategy=eager "
            "/tmp/hop3-rootd /tmp/hop3-cli",
            check=False,
        )
        if not result.success:
            self.log("Failed to install hop3-rootd and hop3-cli", "error")
            self.log_output(result)
            return False

        expected = self._package_version(server_pkg / "pyproject.toml")
        return self._check_one_version(expected)

    def _platform_nginx_target(self) -> tuple[str, bool]:
        """
        Where the platform vhost lives, and whether it may own default_server.

        Debian/Ubuntu (``sites-available`` present): the platform vhost goes to
        ``/etc/nginx/sites-available/hop3`` and we remove the distro ``default``
        site so the platform vhost can be the sole ``default_server`` — making
        the Hop3 control plane the deterministic owner of the bare host / any
        unmatched Host. RHEL/Fedora (``conf.d``): no ``default_server`` (the
        stock ``nginx.conf`` already ships one, and a duplicate fails
        ``nginx -t``); an explicit ``server_name`` match carries the routing.
        """
        on_debian = self.backend.run(
            "test -d /etc/nginx/sites-available", check=False
        ).success
        if on_debian:
            # Idempotent: drop the distro welcome site so our default_server is
            # unique (it otherwise wins :80 and shows the default nginx page).
            self.backend.run("rm -f /etc/nginx/sites-enabled/default", check=False)
            return "/etc/nginx/sites-available/hop3", True
        return "/etc/nginx/conf.d/hop3.conf", False

    def _setup_admin_nginx(self, domain: str) -> bool:
        """
        Configure nginx for the admin domain.

        Updates the main hop3 nginx config (in /etc/nginx/) to use the
        specified server_name. This takes precedence over app-specific
        configs in /home/hop3/nginx/.
        """
        self.log(f"Configuring nginx for {domain}")

        # First, check if there's a conflicting app config for this domain
        app_config = f"/home/hop3/nginx/{domain}.conf"
        result = self.backend.run(f"test -f {shlex.quote(app_config)}", check=False)
        if result.success:
            self.log(f"Replacing the app config that claims {domain}: {app_config}")
            removed = self.backend.run(f"rm -f {shlex.quote(app_config)}", check=False)
            if not removed.success:
                self.log(f"Could not remove {app_config}", "error")
                self.log_output(removed, always=True)
                return False

        config_path, use_default_server = self._platform_nginx_target()

        # Generate nginx config for the admin domain
        # This proxies to the hop3-server running on port 8000
        nginx_config = generate_http_only_config(
            domain, default_server=use_default_server
        )
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

        # Reload nginx (systemctl on systemd hosts; `nginx -s reload` where
        # there is no systemd — the Docker target runs nginx under supervisor).
        # A reload that fails after a validated config means the admin domain
        # won't serve — fail loud rather than report a deploy that half-worked.
        if not self._reload_nginx():
            self.log("Nginx reload failed for the admin domain", "error")
            return False

        self.log(f"Nginx configured for {domain}", "success")
        return True

    def _setup_admin_ssl(self, domain: str) -> bool:
        """
        Setup SSL certificate for the admin domain.

        Uses Let's Encrypt if a valid ACME email is provided, otherwise falls
        back to a self-signed certificate. Returns False (loud) when the cert
        can't be created or activated in nginx, so the deploy fails rather than
        reporting an admin domain that has no working HTTPS.
        """
        cert_dir = f"/home/hop3/ssl/{domain}"
        cert_file = f"{cert_dir}/fullchain.pem"

        # A certificate is already on disk. Keep it — UNLESS it's a self-signed
        # placeholder AND the operator has now supplied a usable --acme-email, in
        # which case upgrade to Let's Encrypt rather than caching the placeholder
        # forever. A real (CA-issued) cert is never re-issued here (Let's Encrypt
        # rate limits); renewal is a separate concern.
        cert_exists = self.backend.run(
            f"test -f {shlex.quote(cert_file)}", check=False
        ).success
        if cert_exists:
            upgrade = (
                self._letsencrypt_skip_reason() is None
                and self._is_self_signed_cert(cert_file)
            )
            if not upgrade:
                self.log(f"SSL certificate already installed for {domain}", "success")
                # Re-assert nginx points at the cert (in case it wasn't).
                return self._update_nginx_for_ssl(domain, cert_dir)
            self.log(
                f"Replacing the self-signed certificate for {domain} with a "
                "Let's Encrypt certificate",
                "info",
            )

        # Determine if we should use Let's Encrypt or self-signed
        # Without --acme-email a self-signed certificate is the default, and
        # said so. With one, a trusted certificate was asked for: a placeholder
        # address, a missing acme.sh or a failed issuance fails the deploy,
        # where it fell back to self-signed and reported success.
        skip_reason = self._letsencrypt_skip_reason()
        if skip_reason is None:
            if self._request_letsencrypt_cert(domain, cert_dir):
                return True
            self.log(
                f"Let's Encrypt issuance failed for {domain}. Check that its "
                "DNS points to this server and ports 80/443 are open, then "
                "redeploy.",
                "error",
            )
            return False
        if self.config.acme_email:
            self.log(
                f"No Let's Encrypt certificate for {domain}: {skip_reason}", "error"
            )
            return False
        self.log(
            f"Using a self-signed certificate for {domain}: {skip_reason}. "
            "For a browser-trusted cert, redeploy with --acme-email "
            f"<you@domain> (with public DNS for {domain} pointing here and "
            "ports 80/443 open).",
            "info",
        )

        # Generate self-signed certificate
        return self._generate_self_signed_cert(domain, cert_dir)

    def _is_self_signed_cert(self, cert_file: str) -> bool:
        """
        True if the installed leaf cert is self-signed (issuer == subject).

        Our placeholder cert is self-signed (issued for ``/CN=<domain>/O=Hop3``);
        a Let's Encrypt cert is issued by the LE CA, so its issuer differs from
        its subject. Only the placeholder is auto-replaced. If openssl can't read
        the cert, returns False — leave it alone rather than churn the CA.
        """
        result = self.backend.run(
            f"openssl x509 -in {shlex.quote(cert_file)} -noout -issuer -subject",
            check=False,
        )
        if not result.success:
            return False
        issuer = subject = ""
        for line in result.stdout.splitlines():
            if line.startswith("issuer="):
                issuer = line[len("issuer=") :].strip()
            elif line.startswith("subject="):
                subject = line[len("subject=") :].strip()
        return bool(issuer) and issuer == subject

    def _should_use_letsencrypt(self) -> bool:
        """Whether Let's Encrypt should be attempted (i.e. no skip reason)."""
        return self._letsencrypt_skip_reason() is None

    def _letsencrypt_skip_reason(self) -> str | None:
        """
        Why Let's Encrypt won't be used, or None when it will be.

        Returned (not just a bool) so ``_setup_admin_ssl`` can tell the operator
        *why* it chose self-signed — an unexplained fallback to a degraded path
        is the silent failure the platform must not produce.
        """
        email = self.config.acme_email
        if not email:
            return "no --acme-email was provided"
        # DEFAULT_ADMIN_EMAIL is admin@example.com; reject it and any other
        # example.com placeholder (Let's Encrypt would reject them anyway).
        if email == DEFAULT_ADMIN_EMAIL or "@example.com" in email:
            return f"--acme-email {email!r} is a placeholder address"

        acme_sh = "/home/hop3/.acme.sh/acme.sh"
        if not self.backend.run(f"test -f {acme_sh}", check=False).success:
            return (
                "acme.sh is not installed on the server (reinstall without --skip-acme)"
            )
        return None

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
            return self._install_ssl_cert(domain, cert_dir)

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
            self.log("acme.sh --issue failed", "error")
            self.log_output(result, always=True)
            return False

        # Install the certificate (and activate it in nginx)
        return self._install_ssl_cert(domain, cert_dir)

    def _generate_self_signed_cert(self, domain: str, cert_dir: str) -> bool:
        """Generate a self-signed SSL certificate. Returns False on failure."""
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
            return False

        # Set proper permissions
        self.backend.run(f"chmod 600 {safe_cert_dir}/key.pem", check=False)
        self.backend.run(f"chmod 644 {safe_cert_dir}/fullchain.pem", check=False)
        self.backend.run(f"chown -R hop3:hop3 {safe_cert_dir}", check=False)

        # Update nginx config to use SSL
        if not self._update_nginx_for_ssl(domain, cert_dir):
            return False

        self.log(f"Self-signed certificate installed for {domain}", "success")
        return True

    def _install_ssl_cert(self, domain: str, cert_dir: str) -> bool:
        """
        Install an acme.sh certificate and activate it in nginx.

        Returns False (loud) when the cert never landed on disk or nginx could
        not be reconfigured/reloaded for it.
        """
        safe_domain = shlex.quote(domain)
        acme_sh = "/home/hop3/.acme.sh/acme.sh"

        # Ensure cert directory exists and is owned by hop3
        self.backend.run(f"mkdir -p {shlex.quote(cert_dir)}", check=False)
        self.backend.run("chown -R hop3:hop3 /home/hop3/ssl", check=False)

        # acme.sh runs as the hop3 user, so its --reloadcmd must NOT shell out to
        # `sudo systemctl reload nginx`: the rootd security model (ADR 041 §12)
        # removes hop3's nginx sudo rights, so that prompts for a password with
        # no tty and fails. Use a no-op reload here — the deploy reloads nginx
        # itself, as root, in _update_nginx_for_ssl below.
        key_file = f"{cert_dir}/key.pem"
        full_file = f"{cert_dir}/fullchain.pem"
        install_cmd = (
            f"sudo -u hop3 {acme_sh} --install-cert "
            f"-d {safe_domain} "
            f"--key-file {shlex.quote(key_file)} "
            f"--fullchain-file {shlex.quote(full_file)} "
            "--reloadcmd true"
        )
        result = self.backend.run(install_cmd, check=False)

        # Success is the cert being on disk, not acme.sh's exit code — a failing
        # reloadcmd must not abort the deploy (the platform reloads nginx itself).
        installed = self.backend.run(
            f"test -s {shlex.quote(full_file)}", check=False
        ).success
        if not installed:
            self.log("Failed to install SSL certificate", "error")
            self.log_output(result)
            return False

        # Update nginx config to use SSL and reload nginx (as root — works
        # regardless of the rootd sudoers retirement).
        if not self._update_nginx_for_ssl(domain, cert_dir):
            return False

        self.log(f"SSL certificate installed for {domain}", "success")
        return True

    def _update_nginx_for_ssl(self, domain: str, cert_dir: str) -> bool:
        """
        Point nginx at the SSL cert and reload. Returns False (loud) on any
        failure — a written-but-not-live HTTPS vhost must not pass for success.
        """
        ssl_cert = f"{cert_dir}/fullchain.pem"
        ssl_key = f"{cert_dir}/key.pem"
        config_path, use_default_server = self._platform_nginx_target()
        nginx_config = generate_full_ssl_config(
            domain, ssl_cert, ssl_key, default_server=use_default_server
        )
        safe_config_path = shlex.quote(config_path)

        write_cmd = f"cat > {safe_config_path} << 'NGINX_EOF'\n{nginx_config}NGINX_EOF"
        result = self.backend.run(write_cmd, check=False)
        if not result.success:
            self.log("Failed to update nginx config for SSL", "error")
            self.log_output(result)
            return False

        # Validate before reload — a broken config (e.g. a duplicate
        # default_server) must surface here, not silently keep the old config
        # running while we report success.
        test_result = self.backend.run("nginx -t", check=False)
        if not test_result.success:
            self.log("nginx config test failed after SSL update", "error")
            self.log_output(test_result)
            return False

        if not self._reload_nginx():
            self.log("Failed to reload nginx after SSL update", "error")
            return False
        return True

    def _reload_nginx(self) -> bool:
        """
        Reload nginx, trying systemctl then ``nginx -s reload``.

        Mirrors hop3-rootd's reload chain (``ops/nginx.py``): ``systemctl`` on
        systemd hosts, ``nginx -s reload`` where there is no systemd — the
        Docker deploy target runs nginx under supervisor, where a plain
        ``systemctl reload`` silently no-ops. The caller validates the config
        with ``nginx -t`` first, so a bad config never reaches here.
        """
        for cmd in ("systemctl reload nginx", "nginx -s reload"):
            if self.backend.run(cmd, check=False).success:
                return True
        return False

    def _create_admin_user(self) -> bool:
        """
        Create the admin user if it doesn't already exist; False on failure.

        A failure was a warning, and the deploy went on to print login
        instructions for a user that did not exist.
        """
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
            return True

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
        if not result.success:
            self.log(f"Failed to create admin user '{user}'", "error")
            self.log_output(result, always=True)
            return False
        self.admin_user_created = True
        self.log(f"Admin user '{user}' created", "success")
        return True

    def _configure_local_cli(self, step: int) -> tuple[bool, int]:
        """
        The "Configuring local CLI" step, unless --no-cli-setup.

        Returns:
            Tuple of (success, updated_step_count).
        """
        if self.config.no_cli_setup:
            return True, step
        step += 1
        self.log_step(step, "Configuring local CLI")
        if self._setup_cli():
            return True, step
        self.log(
            "The server is deployed, but the local CLI is not pointed at it. "
            "Pass --no-cli-setup to skip this step.",
            "error",
        )
        return False, step

    def _setup_cli(self) -> bool:
        """
        Point the local CLI at the server just deployed; False if that failed.

        The server just deployed — NOT whatever ``HOP3_HOST`` / ``HOP3_DEV_HOST``
        happens to hold. In Docker mode the target is the container, reached on
        loopback, while `config.host` still carries the ambient value: a
        `--docker` run pointed the CLI at a remote dev box, printing
        "CLI configured to connect to http://hop3-dev.abilian.com:8000" two lines
        before "Server URL: http://localhost:8000". Nothing was deployed there
        this time, but the next `hop3` command would have gone to it — an
        ambient variable silently redirecting at a real server is the failure
        ADR 043 forbids for pytest, and it is no better here.

        Through `hop3 login`, not `hop3 settings set`. The latter is deprecated
        — it says so on stderr, which this call discarded with
        ``capture_output`` — and it writes `api_url` / `api_token` into
        config.toml, which ``Config.get_api_url`` consults *last*, below every
        context. An operator with any context configured was told "CLI
        configured to connect to <host>" and then had every command go
        somewhere else. `login` writes the per-server credential store and a
        named context, at the rank the rest of the resolution chain uses.

        Docker only. An SSH deploy leaves the CLI alone and the banner gives
        the one login command: the address worth recording for a real server
        is `https://<admin-domain>`, and `http://<host>:8000` — what this
        wrote — is the API port in clear, which would carry the operator's
        bearer token over plain HTTP to a socket bound on every interface.
        Loopback into a container is the one case where that address is the
        right one.
        """
        if not self.config.use_docker:
            return True
        token = self._fetch_admin_token()
        if not token:
            return False
        return self._login_local_cli(self._deployed_api_url(), token)

    def _deployed_api_url(self) -> str:
        """The address of the server this run deployed, never the ambient one."""
        host = (
            "localhost" if self.config.use_docker else (self.config.host or "localhost")
        )
        return f"http://{host}:8000" if "://" not in host else host

    def _fetch_admin_token(self) -> str | None:
        """Create the admin user if needed and return an API token for it."""
        user = self.config.admin_user
        # Quote user-controlled values to prevent command injection.
        # The password no longer flows through argv; see _create_admin_user.
        safe_user = shlex.quote(user)
        safe_email = shlex.quote(f"{user}@hop3.dev")
        hop3_server = str(HOP3_SERVER_BIN)

        # Create the admin user with --password-stdin (a no-op if it exists).
        # See _create_admin_user above for the stdin-vs-echo rationale.
        self.backend.run(
            f"sudo -u hop3 {hop3_server} "
            f"admin:create {safe_user} {safe_email} --password-stdin",
            check=False,
            stdin=self.config.admin_password,
        )

        result = self.backend.run(
            f"sudo -u hop3 {hop3_server} admin:token {safe_user}",
            check=False,
        )
        if not result.success or not result.stdout.strip():
            self.log("Could not get an auth token (check server logs)", "error")
            self.log_output(result)
            return None

        # JWT tokens start with "eyJ"; the command may print other lines.
        for line in result.stdout.strip().splitlines():
            if line.strip().startswith("eyJ"):
                return line.strip()

        self.log("Could not parse an auth token from the output", "error")
        return None

    def _login_local_cli(self, api_url: str, token: str) -> bool:
        """
        Run `hop3 login` on this machine, and report what it actually did.

        The old code logged "CLI configured to connect to <url>" unconditionally
        — after a failed token fetch, after a failed write, always. A success
        line is a promise; this one reports the outcome it got.
        """
        # The token travels on argv, where `ps` can see it for the length of the
        # call. `hop3 login` has no stdin form for --token yet; the surface work
        # in tasks/cli-auth-target-model.md Phase 3 is where that belongs.
        argv = [
            "hop3",
            "login",
            "--token",
            token,
            "--url",
            api_url,
            "--context",
            CLI_CONTEXT_NAME,
        ]
        try:
            result = subprocess.run(argv, capture_output=True, check=False, text=True)
        except FileNotFoundError:
            self.log("hop3 CLI not found on PATH", "error")
            return False

        if result.returncode != 0:
            self.log(f"Could not configure the local CLI for {api_url}", "error")
            # Through `log`, not `print`: it honours --quiet and, unlike a bare
            # print, reaches the deploy log file where a post-mortem looks.
            for stream in (result.stdout, result.stderr):
                if stream.strip():
                    self.log(stream.strip(), "error")
            return False

        self.cli_context_server = api_url
        self.log(
            f"CLI configured: context {CLI_CONTEXT_NAME!r} -> {api_url}", "success"
        )
        return True

    def _deploy_method(self) -> str:
        """Classify the deploy source: local | git | pypi."""
        if self.config.use_local_code:
            return "local"
        if self.config.use_git:
            return "git"
        return "pypi"

    def _log_deploy_provenance(self) -> None:
        """Print what's about to be deployed (commit/branch), best-effort."""
        method = self._deploy_method()
        if method == "local":
            prov = collect_git_provenance(self.config.project_root)
            commit = prov.get("git_commit")
            if commit:
                dirty = " (dirty)" if prov.get("git_dirty") else ""
                branch = prov.get("git_branch") or "?"
                self.log(f"Deploying local code @ {commit[:12]}{dirty} on '{branch}'")
            else:
                self.log("Deploying local code (not a git checkout)")
        elif method == "git":
            self.log(
                f"Deploying git branch '{self.config.branch}' "
                "(commit resolved on the server)"
            )
        else:
            self.log(f"Deploying from PyPI ({self.config.pypi_version or 'latest'})")

    def _write_build_info(self) -> None:
        """
        Write the deploy-provenance manifest to the server (best-effort).

        Authoritative per method: for ``--local`` the commit comes from the
        dev machine's checkout (the server has no ``.git``); for ``git`` it's
        read back from the server (pip's ``direct_url.json`` or the
        ``/home/hop3/hop3`` checkout).
        """
        method = self._deploy_method()
        prov: GitProvenance
        if method == "local":
            prov = collect_git_provenance(self.config.project_root)
        elif method == "git":
            prov = {
                "git_commit": self._server_git_commit(),
                "git_branch": self.config.branch,
                "git_dirty": None,
            }
        else:
            prov = {"git_commit": None, "git_branch": None, "git_dirty": None}

        info = make_build_info(
            deploy_method=method,
            version=self._server_installed_version(),
            deployed_by="hop3-deploy",
            git_commit=prov["git_commit"],
            git_branch=prov["git_branch"],
            git_dirty=prov["git_dirty"],
        )

        path = str(BUILD_INFO_PATH)
        content = json.dumps(info, indent=2)
        # Quoted heredoc: no shell expansion of the JSON payload.
        write_cmd = (
            f"cat > {shlex.quote(path)} << 'HOP3_BUILD_EOF'\n"
            f"{content}\n"
            f"HOP3_BUILD_EOF\n"
            f"chown hop3:hop3 {shlex.quote(path)}"
        )
        result = self.backend.run(write_cmd, check=False)
        if result.success:
            self.log(
                f"Recorded build info (commit {info['git_commit'] or 'unknown'})",
                "success",
            )
        else:
            self.log("Could not write build info", "warning")

    def _server_installed_version(self) -> str | None:
        """Read the hop3-server version installed in the server's venv."""
        result = self.backend.run(
            "/home/hop3/venv/bin/python -c "
            "\"import importlib.metadata as m; print(m.version('hop3_server'))\"",
            check=False,
        )
        if result.success:
            return result.stdout.strip() or None
        return None

    def _server_git_commit(self) -> str | None:
        """Resolve the deployed git commit from the server (git deploys)."""
        # pip records the commit for ``git+...`` installs (PEP 610).
        result = self.backend.run(
            "cat /home/hop3/venv/lib/python*/site-packages/"
            "hop3_server-*.dist-info/direct_url.json 2>/dev/null",
            check=False,
        )
        if result.success and result.stdout.strip():
            try:
                commit = json.loads(result.stdout).get("vcs_info", {}).get("commit_id")
                if commit:
                    return commit
            except (ValueError, AttributeError):
                pass
        # Fallback: the editable checkout used by the git-update path.
        result = self.backend.run(
            "git -C /home/hop3/hop3 rev-parse HEAD 2>/dev/null", check=False
        )
        if result.success and result.stdout.strip():
            return result.stdout.strip()
        return None


def create_backend(config: DeployConfig) -> DeployBackend:
    """Create appropriate backend based on config."""
    if config.use_docker:
        from .backends.docker import (  # ruff:ignore[import-outside-top-level]
            DockerDeployBackend,
        )

        return DockerDeployBackend(config)

    from .backends.ssh import SSHDeployBackend  # ruff:ignore[import-outside-top-level]

    return SSHDeployBackend(config)


def deploy(config: DeployConfig) -> bool:
    """
    Run deployment with the given config.

    This is the main entry point for programmatic use.
    """
    backend = create_backend(config)
    deployer = Deployer(config, backend)
    return deployer.deploy()
