# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the proxy helper (unit-file writer + systemctl driver).

systemctl is mocked; UNIT_DIR and the proxyd path point at the tmp dir so no
real systemd is needed.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from hop3_rootd import proxy


@pytest.fixture
def proxy_env(tmp_path):
    """Point UNIT_DIR + proxyd at a tmp dir and stub systemctl. Yields calls."""
    calls: list[tuple[str, ...]] = []
    with (
        patch.object(proxy, "UNIT_DIR", tmp_path),
        patch.object(
            proxy, "SOCKET_PROXYD_PATH", "/usr/lib/systemd/systemd-socket-proxyd"
        ),
        patch.object(proxy, "_systemctl", side_effect=lambda *a, **k: calls.append(a)),
    ):
        yield tmp_path, calls


def test_add_proxy_writes_unit_pair_and_enables(proxy_env):
    unit_dir, calls = proxy_env
    result = proxy.add_proxy("postgres", "mydb", 54312, 5432)

    assert result == {
        "unit": "hop3-expose-postgres-mydb",
        "public_port": 54312,
        "target_port": 5432,
    }

    socket_text = (unit_dir / "hop3-expose-postgres-mydb.socket").read_text()
    service_text = (unit_dir / "hop3-expose-postgres-mydb.service").read_text()

    # Public listener + loopback-only destination.
    assert "ListenStream=0.0.0.0:54312" in socket_text
    assert "WantedBy=sockets.target" in socket_text
    assert "127.0.0.1:5432" in service_text
    assert "systemd-socket-proxyd" in service_text
    assert "Requires=hop3-expose-postgres-mydb.socket" in service_text

    # No secret ever lands in a unit file.
    assert "password" not in (socket_text + service_text).lower()

    # daemon-reload then enable --now the socket.
    assert ("daemon-reload",) in calls
    assert ("enable", "--now", "hop3-expose-postgres-mydb.socket") in calls


def test_add_proxy_fails_loud_when_proxyd_missing(tmp_path):
    with (
        patch.object(proxy, "UNIT_DIR", tmp_path),
        patch.object(proxy, "SOCKET_PROXYD_PATH", None),
        patch.object(proxy, "_SOCKET_PROXYD_CANDIDATES", ("/nonexistent/proxyd",)),
        pytest.raises(proxy.ProxyUnavailableError),
    ):
        proxy.add_proxy("redis", "cache", 54000, 6379)

    # Nothing written when the binary is absent (rendered before any write).
    assert list(tmp_path.iterdir()) == []


def test_remove_proxy_deletes_units_idempotently(proxy_env):
    unit_dir, calls = proxy_env
    proxy.add_proxy("mysql", "shop", 54001, 3306)
    calls.clear()

    first = proxy.remove_proxy("hop3-expose-mysql-shop")
    assert first == {"removed": True, "unit": "hop3-expose-mysql-shop"}
    assert not (unit_dir / "hop3-expose-mysql-shop.socket").exists()
    assert not (unit_dir / "hop3-expose-mysql-shop.service").exists()
    assert ("disable", "--now", "hop3-expose-mysql-shop.socket") in calls

    # Idempotent: removing again reports nothing present.
    second = proxy.remove_proxy("hop3-expose-mysql-shop")
    assert second["removed"] is False


def test_list_units_returns_base_names(proxy_env):
    unit_dir, _ = proxy_env
    proxy.add_proxy("postgres", "a", 54010, 5432)
    proxy.add_proxy("redis", "b", 54011, 6379)
    # An unrelated unit must be ignored.
    (unit_dir / "other.socket").write_text("")

    assert sorted(proxy.list_units()) == [
        "hop3-expose-postgres-a",
        "hop3-expose-redis-b",
    ]


def test_unit_base_name():
    assert proxy.unit_base_name("postgres", "my-db") == "hop3-expose-postgres-my-db"
