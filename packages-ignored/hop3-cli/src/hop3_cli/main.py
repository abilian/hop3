# Copyright (c) 2024-2025, Abilian SAS

"""
Simple client-side script for Hop3.

All the logic is implemented on the server side, this script is just
a thin wrapper around SSH to communicate with the server.
"""

from __future__ import annotations

import os
import sys

from hop3_cli.util import err, run, run_command

# Define variables
GIT_REMOTE = run_command("git config --get remote.hop3.url")
HOP3_SERVER = os.environ.get("HOP3_SERVER")
HOP3_APP = os.environ.get("HOP3_APP")
REMOTE = GIT_REMOTE or f"{HOP3_SERVER}:{HOP3_APP}"


def main():
    err("Hop3 remote operator.")
    execute_command(sys.argv[1:])


def execute_command(args):
    if not REMOTE:
        err("\nError: no hop3 server configured.")
        err(
            "Use HOP3_SERVER=hop3@MYSERVER.NET or configure a git remote called 'hop3'.\n"
        )
        return

    server, app = REMOTE.split(":")
    sshflags = " ".join(arg for arg in args if arg.startswith("-"))
    args = [arg for arg in args if not arg.startswith("-")]

    cmd = args[0] if args else ""
    err("Server:", server)
    err("App:", app)
    err()

    if cmd in {"", "apps", "setup", "setup:ssh", "update"}:
        cmd = f"ssh -o LogLevel=QUIET {sshflags} {server} {' '.join(args)}"
        run(cmd)
        if cmd == "":
            print(
                "  shell             Local command to start an SSH session in the remote."
            )
    elif cmd == "shell":
        run(f"ssh -t {server} run {app} bash")
    else:
        args.pop(0)  # Remove cmd arg
        run(f"ssh {sshflags} {server} {cmd} {app} {' '.join(args)}")


if __name__ == "__main__":
    main()
