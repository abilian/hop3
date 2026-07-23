# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
ServerInfo must stay in step with the hcloud Server model.

Hetzner deprecated datacenters on 2026-06-02 (removal after 2026-10-01) and
hcloud dropped ``Server.datacenter`` in 2.23.0 — a *minor* release, so no
version bound would have held it back. Nothing here noticed until a
provisioning run aborted mid-rebuild on ``AttributeError: 'Server' object has
no attribute 'datacenter'``, losing a full-suite run to a field we only display.

These pin the mapping against the *real* hcloud domain class, so the next
upstream field removal fails a unit test instead of a cloud run.
"""

from __future__ import annotations

import pytest
from hcloud.locations.domain import Location
from hcloud.servers.domain import Server
from hop3_testing.system_tests import hetzner
from hop3_testing.system_tests.hetzner import HetznerError, ServerInfo

# Every attribute ServerInfo.from_server reads off an hcloud Server.
MAPPED_ATTRIBUTES = (
    "id",
    "name",
    "status",
    "public_net",
    "location",
    "server_type",
    "image",
)


class FakeServer:
    """
    A server exposing only what the IP lookup may touch.

    Deliberately not a real ``Server``: the point is to fail if
    ``get_server_ip`` starts reaching for anything beyond the address.
    """

    def __init__(self, public_net) -> None:
        self.public_net = public_net


def _server(**kwargs) -> Server:
    defaults = {
        "id": 1,
        "name": "hop3-dev",
        "status": "running",
        "location": Location(id=1, name="hel1"),
    }
    return Server(**{**defaults, **kwargs})


def _manager(server) -> hetzner.HetznerManager:
    manager = hetzner.HetznerManager.__new__(hetzner.HetznerManager)
    manager.config = type("_Config", (), {"server_id": 7})()
    manager.get_server = lambda: server  # type: ignore[method-assign]
    return manager


@pytest.mark.parametrize("name", MAPPED_ATTRIBUTES)
def test_every_mapped_attribute_exists_on_the_hcloud_model(name):
    """The mapping may only read fields hcloud actually declares."""
    assert name in Server.__slots__, f"hcloud Server no longer has {name!r}"


def test_from_server_reads_location_not_datacenter():
    info = ServerInfo.from_server(_server())
    assert info.location == "hel1"
    assert not hasattr(info, "datacenter")


def test_from_server_tolerates_a_server_without_a_location():
    """A rebuilding server can come back with fields unpopulated."""
    assert ServerInfo.from_server(_server(location=None)).location == ""


def test_get_server_ip_does_not_depend_on_unrelated_fields():
    """
    The rebuild path needs the address alone. Mapping every other field
    first is what let an unrelated model change abort provisioning.
    """
    ipv4 = type("_Ip", (), {"ip": "1.2.3.4"})()
    public_net = type("_Net", (), {"ipv4": ipv4, "ipv6": None})()
    assert _manager(FakeServer(public_net)).get_server_ip() == "1.2.3.4"


def test_get_server_ip_fails_loudly_without_an_address():
    with pytest.raises(HetznerError, match="no public IPv4"):
        _manager(FakeServer(None)).get_server_ip()
