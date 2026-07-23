# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Shared test stubs — plain objects instead of MagicMock.

These replace the common ``MagicMock()`` / ``Mock()`` patterns across
the CLI test suite so tests verify *state* rather than implementation
details. (ken: anti-pattern 1 — over-mocking)
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from hop3_cli.config import Config


@dataclass
class StubClient:
    """
    Context-manager RPC client returning a canned response.

    Usage::

        response = Ok(result, 1)
        with patch("hop3_cli.rpc.Client", return_value=StubClient(response)):
            ...
    """

    response: Any  # an Ok or Error from jsonrpcclient

    def __enter__(self):
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    def rpc(self, *args: object, **kwargs: object) -> Any:
        return self.response


class StubConfig(Config):
    """
    Minimal config stub with the most-called methods pre-wired.

    Extends ``Config`` so the type checker accepts it wherever ``Config``
    is expected. Methods are plain Python so a test can override them::

        cfg = StubConfig()
        cfg.get_api_url = lambda: "ssh://root@host"
    """

    def __init__(
        self,
        api_url: str | None = None,
        token: str | None = None,
        current_context: str = "default",
    ) -> None:
        super().__init__()
        self._api_url = api_url
        self._token = token
        self._current_context = current_context

    def get_api_url(self) -> str | None:
        return self._api_url

    def get(self, key: str, default: Any = None) -> Any:
        return default

    def is_configured(self) -> bool:
        return True

    def is_authenticated(self) -> bool:
        return True

    def get_current_context_name(self) -> str | None:
        return None

    def set_context_override(self, context_name: str | None) -> None:
        self._current_context = context_name or self._current_context


def make_http_response(
    status_code: int,
    *,
    json_body: dict[str, Any] | None = None,
    ok: bool | None = None,
) -> SimpleNamespace:
    """
    Build a stub ``requests.Response`` with .status_code, .json(), .ok.

    ``ok`` defaults to ``200 <= status_code < 400`` (matching ``requests``).
    """
    if ok is None:
        ok = 200 <= status_code < 400
    return SimpleNamespace(
        status_code=status_code,
        ok=ok,
        json=lambda: json_body or {},
    )
