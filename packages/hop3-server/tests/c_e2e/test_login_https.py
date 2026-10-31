# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
E2E: `hop3 login` against a server with an admin domain sends every later
command over HTTPS, not through an SSH tunnel.

`hop3 login root@host` mints a token over SSH, asks the server for its public
address, checks that address over TLS, and records it as where commands go,
with SSH kept only to renew the token. Tested on a server whose admin domain
has a self-signed certificate, the one an operator would pin with `hop3 settings
set ssl_cert`: the login must trust what every later call trusts.

The CLI runs on the server, as an install puts it there: the admin domain
resolves to the server's own nginx, and the certificate file is at hand. Each
check reads nginx's access log, where a command that went over HTTPS leaves a
line and one through a tunnel leaves none.
"""

from __future__ import annotations

import shlex
from typing import TYPE_CHECKING, Any

import pytest

from .conftest import _start_hop3_container, _stop_hop3_container

if TYPE_CHECKING:
    from collections.abc import Iterator

    import docker

ADMIN = "admin.test.local"
CERT = "/home/hop3/admin-tls/admin.crt"
ACCESS_LOG = "/var/log/nginx/access.log"
HOP3 = "/home/hop3/venv/bin/hop3"


@pytest.fixture(scope="module")
def server(
    docker_client: docker.DockerClient, hop3_image: str
) -> Iterator[dict[str, Any]]:
    """A server with an admin domain that resolves, on the server, to itself."""
    info = _start_hop3_container(
        docker_client, hop3_image, label="login-https", admin_domain=ADMIN
    )
    try:
        # The CLI's ssh is root's: give root the key its authorized_keys trusts.
        _sh(
            info,
            f"echo '127.0.0.1 {ADMIN}' >> /etc/hosts && "
            "install -m 0600 /home/hop3/.ssh/id_rsa /root/.ssh/id_rsa",
        )
        yield info
    finally:
        _stop_hop3_container(info)


def _sh(info: dict[str, Any], command: str) -> str:
    """Run ``command`` as root on the server; its output, or fail with it."""
    result = info["container"].exec_run(["sh", "-c", command])
    output = result.output.decode(errors="replace")
    assert result.exit_code == 0, f"{command}\n{output}"
    return output


def _hop3(info: dict[str, Any], home: str, *args: str) -> str:
    """`hop3 …` on the server, from the config home ``home``."""
    argv = shlex.join([HOP3, *args])
    return _sh(info, f"cd /tmp && HOP3_CONFIG_DIR={home} {argv} 2>&1")


def _rpc_requests(info: dict[str, Any]) -> int:
    """How many RPC requests nginx has logged: each came in over HTTPS."""
    return int(_sh(info, f"grep -c '\"POST /rpc' {ACCESS_LOG} || true").strip())


@pytest.mark.e2e
class TestLoginOverHttps:
    def test_a_pinned_certificate_makes_the_https_address_the_everyday_one(
        self, server
    ):
        home = "/tmp/cli-pinned"
        _hop3(server, home, "settings", "set", "ssl_cert", CERT)

        login = _hop3(server, home, "login", "root@localhost")

        assert f"Signed in to https://{ADMIN}" in login, login
        recorded = _sh(server, f"cat {home}/config.toml")
        assert f'"https://{ADMIN}"' in recorded, recorded
        assert '"ssh://root@localhost"' in recorded, recorded  # renewal only

        before = _rpc_requests(server)
        listed = _hop3(server, home, "app", "list")

        assert _rpc_requests(server) > before, f"no RPC reached nginx:\n{listed}"

    def test_without_the_pin_the_login_keeps_the_tunnel_and_says_why(self, server):
        home = "/tmp/cli-unpinned"

        login = _hop3(server, home, "login", "root@localhost")

        assert "does not trust" in login, login
        assert "tunnel over SSH" in login, login
        before = _rpc_requests(server)
        _hop3(server, home, "app", "list")
        assert _rpc_requests(server) == before
