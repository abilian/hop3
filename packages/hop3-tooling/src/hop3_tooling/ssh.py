# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""The one ssh command line the maintainer tools spawn."""

from __future__ import annotations

from hop3_cli.core.ssh_target import SshSettings, split_ssh_target, ssh_base_argv


def ssh_argv(target: str, remote_cmd: str) -> list[str]:
    """
    ``ssh`` to ``target`` running ``remote_cmd``.

    Built on hop3-cli's ssh command line (host keys trusted on first use,
    never ``StrictHostKeyChecking=no``), with ``BatchMode`` so a missing key
    fails instead of prompting. Not with hop3-cli's *configured* settings:
    the boxes these tools reach (a freshly rebuilt bench server, a verify
    target) are not the operator's hop3 server, so an ``ssh_port = 2222`` set
    for that server sent every bench connection to the wrong port. A target
    that needs a port says so itself (``root@host:2222``).
    """
    user_host, port = split_ssh_target(target)
    return [
        *ssh_base_argv(SshSettings(), port=port),
        "-o",
        "BatchMode=yes",
        user_host,
        remote_cmd,
    ]
