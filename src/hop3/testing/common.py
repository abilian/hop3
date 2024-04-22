# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import os
import sys
import time
from io import StringIO
from pathlib import Path
from subprocess import PIPE, Popen

import paramiko
from cleez.colors import blue, dim, green, red
from dotenv import load_dotenv

load_dotenv()

USER = "hop3"
DOMAIN = os.environ["HOP3_TEST_DOMAIN"]
SERVER = f"ssh.{DOMAIN}"

ssh_client = paramiko.SSHClient()
ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh_client.connect(SERVER, username="root")


def print_lines(s: str | list[str], prefix) -> None:
    match s:
        case list():
            lines = s
        case str():
            lines = s.splitlines()
        case _:
            raise TypeError(type(s))

    for line in lines:
        print(prefix, " ", dim(line.rstrip("\n")))


class ClientError(Exception):
    pass


def run(cmd) -> str:
    print(dim("$"), cmd)

    stdout = StringIO()

    with Popen(cmd, stdout=PIPE, stderr=PIPE, shell=True, text=True, bufsize=1) as p:
        assert p.stdout
        assert p.stderr

        os.set_blocking(p.stdout.fileno(), False)
        os.set_blocking(p.stderr.fileno(), False)
        while True:
            lines = p.stdout.readlines()
            print_lines(lines, blue("Stdout: "))
            stdout.write("\n".join(lines))

            lines = p.stderr.readlines()
            print_lines(lines, red("Stderr: "))

            time.sleep(0.1)

            if p.poll() is not None:
                break

        lines = p.stdout.readlines()
        print_lines(lines, blue("Stdout: "))
        stdout.write("\n".join(lines))

        lines = p.stderr.readlines()
        print_lines(lines, red("Stderr: "))

        status = p.wait()

    if status != 0:
        raise ClientError(status)

    return stdout.getvalue()


def ssh(cmd) -> None:
    print(dim(f"root@{SERVER}:"), cmd)

    transport = ssh_client.get_transport()
    assert transport

    chan = transport.open_session()
    chan.exec_command(cmd)

    while True:
        if chan.recv_ready():
            stdout = chan.recv(sys.maxsize).decode()
            print_lines(stdout, blue("Stdout: "))
        if chan.recv_stderr_ready():
            stderr = chan.recv_stderr(sys.maxsize).decode()
            print_lines(stderr, red("Stderr: "))
        if chan.exit_status_ready():
            break
        time.sleep(0.1)

    chan.close()
    assert chan.exit_status_ready()


# Don't use. Use the installer instead.
def update_agent() -> None:
    """Build and deploy the agent from this repo."""
    print(green("Updating agent"))
    run("rm -rf dist/*")
    run("poetry build")
    sftp_client = ssh_client.open_sftp()
    wheel_path = next(Path("dist").glob("hop3-*.whl"))
    wheel_name = wheel_path.name
    sftp_client.put(str(wheel_path), f"/tmp/{wheel_name}")
    ssh(f"su - hop3 -c '~/venv/bin/pip install -q --force-reinstall /tmp/{wheel_name}'")
    print(green("...done\n"))
