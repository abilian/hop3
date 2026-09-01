# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
What an SSH tunnel to a hop3-managed user actually does.

The happy path — tunnelling as root to a real server — cannot be exercised here.
The e2e container only hands out the `hop3` user's key, and hop3-server installs
that key with `no-port-forwarding` (`hop3/server/cli/setup.py`): it is the
git-push key, deliberately locked down. hop3-cli tunnels as root, whose key the
platform does not manage.

So this covers the case the container *can* prove, and the one an operator is
likely to hit by writing `ssh://hop3@host` instead of `ssh://root@host`: the
forward is refused, and the failure has to say so rather than surfacing as a bare
`httpx.ReadError` with a localhost URL that looks fine.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import anyio
import pytest
from hop3_tui.api.client import Hop3ClientError
from hop3_tui.app import Hop3TUI
from hop3_tui.config import TUIConfig

if TYPE_CHECKING:
    from hop3_testing.targets.base import TargetInfo


def test_a_tunnel_as_the_hop3_user_fails_with_an_actionable_message(
    hop3_server: TargetInfo, monkeypatch, tmp_path
):
    if not hop3_server.ssh_key or not hop3_server.ssh_port:
        pytest.skip("container exposed no SSH key/port to tunnel through")

    monkeypatch.setenv("HOP3_CONFIG_DIR", str(tmp_path))
    (tmp_path / "config.toml").write_text(
        f'ssh_user = "hop3"\nserver_port = 8000\nssh_key = "{hop3_server.ssh_key}"\n'
    )
    host = hop3_server.ssh_host.split("@")[-1]

    hop3 = Hop3TUI(TUIConfig(server_url=f"ssh://hop3@{host}:{hop3_server.ssh_port}"))
    try:
        # The tunnel process starts: ssh connects fine, it is the *channel* that
        # is refused, which is why this is not caught at `start()`.
        assert hop3.tunnel is not None
        assert hop3.api_client.base_url.startswith("http://localhost:")

        with pytest.raises(Hop3ClientError) as caught:
            anyio.run(hop3.api_client.list_apps)

        message = str(caught.value)
        assert "no-port-forwarding" in message, message
        assert "root" in message, "the message must name the way out"
    finally:
        hop3.close()

    assert hop3.tunnel is None
