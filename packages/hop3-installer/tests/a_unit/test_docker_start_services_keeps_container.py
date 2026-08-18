# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Starting the services must not kill the process holding the container open.

`start_services` ran `pkill -f 'sleep infinity'` before launching supervisord,
to "kill the sleep process that's keeping the container alive". It never did:
`sleep infinity` was pid 1, and the kernel discards a signal sent to pid 1 when
pid 1 installed no handler for it. The line was inert, and read as working.

Running the container under `--init` (so package postinsts can reap their
children) made tini pid 1 and the sleep an ordinary child — at which point the
pkill landed, tini exited along with its only child, and the container died in
the middle of its own deploy. What that looked like from outside was a deploy
failing at "Restarting server" with an empty `/etc/supervisor/conf.d`.

supervisord daemonizes, so nothing needs to be freed up for it.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from hop3_installer.deployer.backends.docker import DockerDeployBackend
from hop3_installer.deployer.config import DeployConfig


class _Result:
    def __init__(self, stdout: str = "", success: bool = True) -> None:
        self.stdout = stdout
        self.stderr = ""
        self.success = success
        self.returncode = 0 if success else 1


@pytest.fixture
def commands():
    """Run `start_services` with no supervisord present, recording commands."""
    recorded: list[str] = []
    backend = DockerDeployBackend(DeployConfig(use_docker=True))

    def fake_run(cmd, *args, **kwargs):
        recorded.append(cmd)
        # `pgrep -x supervisord` fails: nothing is running yet, which is the
        # branch that used to carry the pkill.
        return _Result(success="pgrep -x supervisord" not in cmd)

    with patch.object(backend, "run", side_effect=fake_run), patch("time.sleep"):
        backend.start_services()
    return recorded


def test_nothing_pkills_the_container_placeholder(commands):
    assert not any("pkill" in cmd for cmd in commands)
    assert not any("sleep infinity" in cmd for cmd in commands)


def test_supervisord_is_started(commands):
    assert any(cmd.startswith("supervisord -c") for cmd in commands)


def test_the_supervisor_config_is_written_first(commands):
    """A config written after the daemon starts is a config it never read."""
    config = next(i for i, c in enumerate(commands) if "conf.d/hop3.conf" in c)
    started = next(i for i, c in enumerate(commands) if c.startswith("supervisord -c"))

    assert config < started
