# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The TUI must reach the same server `hop3` reaches, by the same route.

It used to reimplement hop3-cli's configuration: guessing the config path per
platform (wrong on macOS, so it found nothing and fell back to `localhost:5000`,
where an unrelated dev server answered with the 404 that started this), and then
reading only the flat `api_url` — ignoring the context chain, so `hop3` would talk
to prod while the TUI talked to localhost.

Both are now delegated to hop3-cli, and an `ssh://` answer is reached the way the
CLI reaches it: an `ssh -N -L` forward, with the client pointed at the local end.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from hop3_cli.config import get_config as cli_config
from hop3_tui.app import Hop3TUI
from hop3_tui.config import TUIConfig

if TYPE_CHECKING:
    from pathlib import Path

PROD = "ssh://root@prod.test"


@pytest.fixture
def cli_home(monkeypatch, tmp_path: Path):
    """A throwaway hop3-cli config directory, isolated from the developer's own."""
    monkeypatch.setenv("HOP3_CONFIG_DIR", str(tmp_path))
    for var in (
        "HOP3_API_URL",
        "HOP3_API_TOKEN",
        "HOP3_SERVER_URL",
        "HOP3_TOKEN",
        "HOP3_DEV_MODE",
    ):
        monkeypatch.delenv(var, raising=False)

    def write(text: str) -> Path:
        (tmp_path / "config.toml").write_text(text)
        return tmp_path

    return write


CONTEXT_CONFIG = (
    'api_url = "http://ignored.test:8000"\n'
    "[cli]\n"
    'default_context = "prod"\n'
    "[contexts.prod]\n"
    f'server = "{PROD}"\n'
)


def test_there_is_no_default_server_to_fall_back_to():
    """hop3-cli has no default api_url either: unconfigured must be detectable.

    A default was not harmless. It pointed at localhost:5000, where whatever else
    the developer was running answered, and the TUI reported that stranger's 404
    as its own.
    """
    assert TUIConfig().server_url == ""


def test_the_tui_resolves_the_same_server_as_hop3_cli(cli_home):
    """The whole point of delegating: one resolution, so they cannot disagree."""
    cli_home(CONTEXT_CONFIG)

    cli = cli_config()
    name = cli.get_context_override() or cli.get_default_context()
    if name and (server := cli.get_context_server(name)):
        cli.set_active_server(server)

    assert TUIConfig._load_from_cli_config(TUIConfig()).server_url == cli.get_api_url()


def test_the_active_context_beats_the_flat_api_url(cli_home):
    """`hop3` resolves the context first; reading `api_url` sent the TUI elsewhere."""
    cli_home(CONTEXT_CONFIG)

    assert TUIConfig._load_from_cli_config(TUIConfig()).server_url == PROD


def test_a_bare_api_url_is_ignored_the_way_hop3_cli_ignores_it(cli_home):
    """`hop3` uses a flat `api_url` only under HOP3_DEV_MODE.

    The TUI used to read it unconditionally, which is one of the ways it ended up
    pointed somewhere `hop3` was not. Delegating means inheriting this rule too,
    including the part where unconfigured stays detectable.
    """
    cli_home('api_url = "http://plain.test:8000"\n')

    assert TUIConfig._load_from_cli_config(TUIConfig()).server_url == ""


def test_dev_mode_brings_the_flat_api_url_back(cli_home, monkeypatch):
    cli_home('api_url = "http://plain.test:8000"\n')
    monkeypatch.setenv("HOP3_DEV_MODE", "true")

    assert (
        TUIConfig._load_from_cli_config(TUIConfig()).server_url
        == "http://plain.test:8000"
    )


# -- reaching an ssh:// server ---------------------------------------------------------


#: Forwards the stub was asked for, newest last. Module-level rather than a class
#: attribute so the fixture can reset it without a mutable class default.
STARTED: list[tuple[Any, ...]] = []


class StubTunnel:
    """Records the forward it was asked for, without running ssh."""

    def __init__(self, host, remote_port, *, user, ssh_port=22, key=None) -> None:
        self.args = (host, remote_port, user, ssh_port, key)
        self.stopped = False

    def start(self) -> None:
        STARTED.append(self.args)

    def stop(self) -> None:
        self.stopped = True

    @property
    def local_bind_port(self) -> int:
        return 54321


@pytest.fixture
def stub_tunnel(monkeypatch):
    STARTED.clear()
    monkeypatch.setattr("hop3_tui.app.SshTunnel", StubTunnel)
    return STARTED


def test_an_ssh_server_is_reached_through_a_tunnel(stub_tunnel):
    """`hop3` forwards a local port to the remote hop3-server; so does the TUI."""
    hop3 = Hop3TUI(TUIConfig(server_url=PROD))

    host, remote_port, user, ssh_port, _key = stub_tunnel[0]
    assert (host, user, ssh_port) == ("prod.test", "root", 22)
    assert remote_port == 8000, "the port hop3-server listens on remotely"
    assert hop3.api_client.base_url == "http://localhost:54321"
    hop3.close()


def test_an_http_server_opens_no_tunnel(stub_tunnel):
    hop3 = Hop3TUI(TUIConfig(server_url="http://plain.test:8000"))

    assert stub_tunnel == []
    assert hop3.tunnel is None
    assert hop3.api_client.base_url == "http://plain.test:8000"


def test_closing_drops_the_tunnel_and_is_safe_twice(stub_tunnel):
    """An `ssh -N -L` child outliving the TUI would hold the port."""
    hop3 = Hop3TUI(TUIConfig(server_url=PROD))
    tunnel = hop3.tunnel

    hop3.close()
    hop3.close()

    assert tunnel is not None
    assert tunnel.stopped
    assert hop3.tunnel is None


def test_an_ssh_url_without_a_host_fails_loudly():
    with pytest.raises(ValueError, match="no hostname"):
        Hop3TUI(TUIConfig(server_url="ssh://"))
