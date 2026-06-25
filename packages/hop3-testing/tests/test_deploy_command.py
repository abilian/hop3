# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""hop3-deploy command assembly: the credential key is threaded as --ssh-key.

Without it the deploy's ssh falls back to a default identity the server-resident
runtime user doesn't have -> 'Permission denied (publickey)' at target setup.
"""

from __future__ import annotations

from hop3_testing.targets.helpers import _build_deploy_command


def _cmd(**over):
    base = {
        "docker": False,
        "host": "203.0.113.7",
        "user": "root",
        "container_name": "c",
        "image": "i",
        "use_local": False,
        "clean": False,
        "branch": "main",
        "verbose": False,
        "features": ["all"],
    }
    base.update(over)
    return _build_deploy_command(**base)


def test_ssh_key_threaded_to_hop3_deploy():
    cmd = _cmd(ssh_key="/data/keys/k.key")
    assert cmd[cmd.index("--ssh-key") + 1] == "/data/keys/k.key"


def test_no_ssh_key_omits_the_flag():
    assert "--ssh-key" not in _cmd()


def test_docker_target_gets_no_ssh_key():
    assert "--ssh-key" not in _cmd(docker=True, ssh_key="/k")  # docker doesn't ssh
