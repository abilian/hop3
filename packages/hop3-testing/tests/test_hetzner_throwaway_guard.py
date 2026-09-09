# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
A rebuild refuses a server that is not labelled as a throwaway.

The server id reaches the manager from a config file or the environment, and
both have named a box people were using. The label lives on the server itself,
so a wrong id cannot carry it.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from hop3_testing.system_tests.config import HetznerConfig
from hop3_testing.system_tests.hetzner import (
    THROWAWAY_LABEL,
    HetznerManager,
    ServerResetError,
)


def _manager(labels: dict[str, str]) -> HetznerManager:
    manager = HetznerManager(
        HetznerConfig(
            api_token="t", server_id=7, image="ubuntu-24.04", ssh_key_name="k"
        )
    )
    server = MagicMock(id=7, labels=labels)
    server.name = "hop3-dev"
    manager._client = MagicMock()
    manager._client.servers.get_by_id.return_value = server
    manager._find_image = lambda _name: MagicMock()  # type: ignore[method-assign]
    manager.resolve_ssh_key = MagicMock  # type: ignore[method-assign]
    return manager


def test_an_unlabelled_server_is_not_rebuilt():
    manager = _manager({})
    with pytest.raises(ServerResetError, match="not labelled hop3-throwaway=true"):
        manager.rebuild_server()
    manager._client.servers.rebuild.assert_not_called()


def test_a_label_with_the_wrong_value_is_not_enough():
    manager = _manager({THROWAWAY_LABEL: "yes"})
    with pytest.raises(ServerResetError):
        manager.rebuild_server()
    manager._client.servers.rebuild.assert_not_called()


def test_a_labelled_server_reaches_the_rebuild_call():
    manager = _manager({THROWAWAY_LABEL: "true"})
    # Everything after the API call is out of scope here; make it stop there.
    manager._client.servers.rebuild.side_effect = RuntimeError("stop at the call")
    with pytest.raises(RuntimeError, match="stop at the call"):
        manager.rebuild_server()
    manager._client.servers.rebuild.assert_called_once()
