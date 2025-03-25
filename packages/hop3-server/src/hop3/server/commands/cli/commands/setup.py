# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import grp
import os
import pwd
import stat
import subprocess
import sys
import traceback
from pathlib import Path
from tempfile import NamedTemporaryFile

from hop3 import config as c
from hop3.server.commands.registry import command
from hop3.oses.ubuntu2204 import setup_system
from hop3.lib import Abort, echo


@command
class SetupSystemCmd:
    name = "setup:system"
    """Set up the server (must be run as root)."""

    def run(self) -> None:
        setup_system()


@command
class SetupCmd:
    """Initialize environment."""

    name = "setup"

    def run(self) -> None:
        echo(f"Running in Python {'.'.join(map(str, sys.version_info))}")

        # Create required paths
        for p in c.ROOT_DIRS:
            path = Path(p)
            if not path.exists():
                echo(f"Creating '{p}'.", fg="green")
                path.mkdir(parents=True)

        # Set up the uWSGI emperor config
        cpu_count = os.cpu_count() or 1
        pw_name = pwd.getpwuid(os.getuid()).pw_name
        gr_name = grp.getgrgid(os.getgid()).gr_name
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
        with (c.UWSGI_ROOT / "uwsgi.ini").open("w") as h:
            h.write("[uwsgi]\n")
            for k, v in settings:
                h.write(f"{k:s} = {v}\n")


@command
class SetupSshCmd:
    """Set up a new SSH key (use - for stdin)."""

    name = "setup:ssh"

    def add_arguments(self, parser) -> None:
        parser.add_argument("public_key_file", type=str)

    def run(self, public_key_file: str) -> None:
        """Process a public key file or read from standard input to manage
        keys.

        Input:
        - public_key_file (str): The path to the public key file. If set to '-', the key is read from standard input.
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
