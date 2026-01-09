# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import grp
import os
import pwd
import secrets
import stat
import subprocess
import sys
import traceback
from pathlib import Path
from tempfile import NamedTemporaryFile

import toml

from hop3 import config as c
from hop3.core.plugins import get_os_strategy
from hop3.lib import Abort, echo
from hop3.lib.registry import register
from hop3.server.cli import Command


@register
class SetupSystemCmd(Command):
    """Set up the server (must be run as root)."""

    name = "setup:system"

    def run(self) -> None:
        """Run OS-specific system setup using the plugin system."""
        strategy = get_os_strategy()
        echo(f"Detected OS: {strategy.display_name}", fg="green")
        strategy.setup_server()


@register
class SetupCmd(Command):
    """Initialize environment."""

    name = "setup"

    def add_arguments(self, parser) -> None:
        """Add command-specific arguments."""
        parser.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            dest="verbose_setup",
            help="Show detailed information during setup",
        )

    def run(self, *, verbose_setup: bool = False) -> None:
        echo(f"Running in Python {'.'.join(map(str, sys.version_info))}")

        if verbose_setup:
            echo(f"HOP3_ROOT: {c.HOP3_ROOT}", fg="blue")
            echo("")

        # Create required paths
        if verbose_setup:
            echo("Creating required directories:", fg="yellow")

        created_count = 0
        existing_count = 0
        for p in c.ROOT_DIRS:
            path = Path(p)
            if not path.exists():
                echo(f"  Creating '{p}'.", fg="green")
                path.mkdir(parents=True)
                created_count += 1
            else:
                if verbose_setup:
                    echo(f"  Directory '{p}' already exists.", fg="blue")
                existing_count += 1

        if verbose_setup:
            echo("")
            echo(
                f"Directories: {created_count} created, {existing_count} already existed",
                fg="blue",
            )
            echo("")

        # Set up the uWSGI emperor config
        cpu_count = os.cpu_count() or 1
        pw_name = pwd.getpwuid(os.getuid()).pw_name
        gr_name = grp.getgrgid(os.getgid()).gr_name

        if verbose_setup:
            echo("Configuring uWSGI emperor:", fg="yellow")
            echo(f"  CPU count: {cpu_count}", fg="blue")
            echo(f"  User: {pw_name} (UID: {os.getuid()})", fg="blue")
            echo(f"  Group: {gr_name} (GID: {os.getgid()})", fg="blue")
            echo(f"  Worker threads: {cpu_count * 2}", fg="blue")
            echo("")

        settings = [
            ("chdir", c.UWSGI_ROOT),
            ("emperor", c.UWSGI_ENABLED),
            ("log-maxsize", c.UWSGI_LOG_MAXSIZE),
            ("logto", c.UWSGI_ROOT / "uwsgi.log"),
            ("log-backupname", c.UWSGI_ROOT / "uwsgi.old.log"),
            ("socket", c.UWSGI_ROOT / "uwsgi.sock"),
            ("uid", pw_name),
            ("gid", gr_name),
            ("enable-threads", "true"),
            ("threads", f"{cpu_count * 2}"),
        ]

        uwsgi_config_path = c.UWSGI_ROOT / "uwsgi.ini"
        with uwsgi_config_path.open("w") as h:
            h.write("[uwsgi]\n")
            for k, v in settings:
                h.write(f"{k:s} = {v}\n")

        if verbose_setup:
            echo(f"Created uWSGI config: {uwsgi_config_path}", fg="green")
            echo("")
            echo("Configuration settings:", fg="yellow")
            for k, v in settings:
                echo(f"  {k}: {v}", fg="blue")
            echo("")

        # Set up HOP3_SECRET_KEY
        self.setup_secret_key(verbose=verbose_setup)

        if verbose_setup:
            echo("")
            echo("Setup completed successfully!", fg="green")

    def setup_secret_key(self, *, verbose: bool = False) -> None:
        """Generate and configure HOP3_SECRET_KEY if not already set.

        Args:
            verbose: Whether to show detailed output
        """
        # Check if already set in environment
        if os.environ.get("HOP3_SECRET_KEY"):
            if verbose:
                echo("Secret key configuration:", fg="yellow")
                echo("  HOP3_SECRET_KEY already set in environment", fg="blue")
            return

        # Path to server config file
        config_file = c.HOP3_ROOT / "hop3-server.toml"

        # Check if already set in config file
        if config_file.exists():
            try:
                config_data = toml.load(config_file)
                if config_data.get("HOP3_SECRET_KEY"):
                    if verbose:
                        echo("Secret key configuration:", fg="yellow")
                        echo(
                            f"  HOP3_SECRET_KEY already configured in {config_file}",
                            fg="blue",
                        )
                    return
            except Exception:
                # If we can't parse the file, continue to generate a new key
                pass

        # Generate new secret key
        echo("Secret key configuration:", fg="yellow")
        secret_key = secrets.token_urlsafe(32)

        # Save to config file
        try:
            # Load existing config or start fresh
            if config_file.exists():
                config_data = toml.load(config_file)
            else:
                config_data = {}

            # Add secret key
            config_data["HOP3_SECRET_KEY"] = secret_key

            # Write config file
            with config_file.open("w") as f:
                f.write("# Hop3 Server Configuration\n")
                f.write("# Generated by hop3-server setup\n\n")
                toml.dump(config_data, f)

            # Set restrictive permissions (owner read/write only)
            config_file.chmod(0o600)

            echo(f"  Generated and saved HOP3_SECRET_KEY to {config_file}", fg="green")
            echo("")
            echo(
                "  IMPORTANT: Restart the hop3 service to load the key:",
                fg="yellow",
            )
            echo("    sudo systemctl restart hop3", fg="white")
            echo("")
            echo(
                "  IMPORTANT: Keep this key secret! It's used to sign authentication tokens",
                fg="yellow",
            )

            if verbose:
                echo("")
                echo(f"  Secret key: {secret_key}", fg="blue")
                echo("  File permissions: 0600 (owner read/write only)", fg="blue")

        except Exception as e:
            echo(
                f"  Warning: Could not save HOP3_SECRET_KEY to {config_file}: {e}",
                fg="red",
            )
            echo("")
            echo(
                "  Please manually add HOP3_SECRET_KEY to your config file:",
                fg="yellow",
            )
            echo(f"  Edit {config_file} and add:", fg="white")
            echo(f'  HOP3_SECRET_KEY = "{secret_key}"', fg="white")
            echo(f"  chmod 600 {config_file}", fg="white")


@register
class SetupSshCmd(Command):
    """Set up a new SSH key (use - for stdin)."""

    name = "setup:ssh"

    def add_arguments(self, parser) -> None:
        parser.add_argument("public_key_file", type=str)

    def run(self, public_key_file: str) -> None:
        """Process a public key file or read from standard input to manage keys.

        Args:
            public_key_file: The path to the public key file. If set to '-',
                           the key is read from standard input.
        """
        if public_key_file == "-":
            self.add_helper(Path(public_key_file))
            # Read lines from standard input if '-' is used
            buffer = "".join(sys.stdin.readlines())
            # Create a temporary file to store the public key read from stdin
            with NamedTemporaryFile(mode="w", encoding="utf8") as f:
                f.write(buffer)
                f.flush()
                self.add_helper(Path(f.name))
        else:
            self.add_helper(Path(public_key_file))

    def add_helper(self, key_file: Path) -> None:
        """Add a public key to the authorized keys list.

        Input:
        - key_file (Path): The path to the public key file to be added.
        """
        if not key_file.exists():
            msg = f"Error: public key file '{key_file}' not found."
            raise Abort(msg)

        try:
            # Run the ssh-keygen command to get the fingerprint from the key file
            cmd = ["ssh-keygen", "-lf", str(key_file)]
            cmd_output = str(subprocess.check_output(cmd))
            fingerprint = cmd_output.split(" ", 4)[1]
            key = key_file.read_text().strip()
            echo(f"Adding key '{fingerprint}'.", fg="white")
            self.setup_authorized_keys(key, fingerprint)
        except Exception:
            echo(
                f"Error: invalid public key file '{key_file}': {traceback.format_exc()}",
                fg="red",
            )

    def setup_authorized_keys(self, pubkey, fingerprint) -> None:
        """Sets up an authorized_keys file to redirect SSH commands.

        Input:
        - pubkey: The public key to be added to the authorized_keys file, provided as a string.
        - fingerprint: The fingerprint associated with the public key for identification, provided as a string.
        """
        authorized_keys = c.HOP3_ROOT / ".ssh" / "authorized_keys"
        authorized_keys.parent.mkdir(parents=True, exist_ok=True)

        # Restrict features and force all SSH commands to go through our script
        cmd = f"FINGERPRINT={fingerprint:s} NAME=default {c.HOP3_SCRIPT:s} $SSH_ORIGINAL_COMMAND"
        authorized_keys.write_text(
            f'command="{cmd}",no-agent-forwarding,no-user-rc,no-X11-forwarding,no-port-forwarding'
            f" {pubkey:s}\n",
        )
        authorized_keys.parent.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        authorized_keys.chmod(stat.S_IRUSR | stat.S_IWUSR)
