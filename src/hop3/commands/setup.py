# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

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

from click import argument

from hop3.oses.ubuntu2204 import setup_system
from hop3.system.constants import (
    HOP3_SCRIPT,
    ROOT_DIRS,
    UWSGI_ENABLED,
    UWSGI_LOG_MAXSIZE,
    UWSGI_ROOT,
)
from hop3.util.console import echo

from . import make_executable
from .cli import hop3


@hop3.command("setup:system")
def cmd_setup_system() -> None:
    """Set up the server (must be run as root)."""
    # Set up the server
    setup_system()


@hop3.command("setup")
def cmd_setup() -> None:
    """Initialize environment."""
    echo(f"Running in Python {'.'.join(map(str, sys.version_info))}")

    # Create required paths
    for p in ROOT_DIRS:
        path = Path(p)
        if not path.exists():
            echo(f"Creating '{p}'.", fg="green")
            path.mkdir(parents=True)

    # Set up the uWSGI emperor config
    cpu_count = os.cpu_count() or 1
    pw_name = pwd.getpwuid(os.getuid()).pw_name
    gr_name = grp.getgrgid(os.getgid()).gr_name
    settings = [
        ("chdir", UWSGI_ROOT),
        ("emperor", UWSGI_ENABLED),
        ("log-maxsize", UWSGI_LOG_MAXSIZE),
        ("logto", os.path.join(UWSGI_ROOT, "uwsgi.log")),
        ("log-backupname", os.path.join(UWSGI_ROOT, "uwsgi.old.log")),
        ("socket", os.path.join(UWSGI_ROOT, "uwsgi.sock")),
        ("uid", pw_name),
        ("gid", gr_name),
        ("enable-threads", "true"),
        ("threads", f"{cpu_count * 2}"),
    ]
    with Path(UWSGI_ROOT, "uwsgi.ini").open("w") as h:
        h.write("[uwsgi]\n")
        for k, v in settings:
            h.write(f"{k:s} = {v}\n")

    # mark this script as executable (in case we were invoked via interpreter)
    make_executable(HOP3_SCRIPT)


@hop3.command("setup:ssh")
@argument("public_key_file")
def cmd_setup_ssh(public_key_file) -> None:
    """Set up a new SSH key (use - for stdin)."""

    def add_helper(key_file):
        if Path(key_file).exists():
            try:
                fingerprint = str(
                    subprocess.check_output("ssh-keygen -lf " + key_file, shell=True),
                ).split(" ", 4)[1]
                key = Path(key_file).read_text().strip()
                echo(f"Adding key '{fingerprint}'.", fg="white")
                setup_authorized_keys(fingerprint, key)
            except Exception:
                echo(
                    f"Error: invalid public key file '{key_file}':"
                    f" {traceback.format_exc()}",
                    fg="red",
                )
        elif public_key_file == "-":
            buffer = "".join(sys.stdin.readlines())
            with NamedTemporaryFile(mode="w", encoding="utf8") as f:
                f.write(buffer)
                f.flush()
                add_helper(f.name)
        else:
            echo(f"Error: public key file '{key_file}' not found.", fg="red")

    add_helper(public_key_file)


def setup_authorized_keys(ssh_fingerprint, pubkey) -> None:
    """Sets up an authorized_keys file to redirect SSH commands."""
    authorized_keys = Path(os.environ["HOME"], ".ssh", "authorized_keys")
    authorized_keys.parent.mkdir(parents=True, exist_ok=True)

    # Restrict features and force all SSH commands to go through our script
    authorized_keys.write_text(
        f'command="FINGERPRINT={ssh_fingerprint:s} NAME=default'
        f' {HOP3_SCRIPT:s} $SSH_ORIGINAL_COMMAND",no-agent-forwarding,no-user-rc,no-X11-forwarding,no-port-forwarding'
        f" {pubkey:s}\n",
    )

    authorized_keys.parent.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    authorized_keys.chmod(stat.S_IRUSR | stat.S_IWUSR)
