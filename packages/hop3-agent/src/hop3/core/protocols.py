# Copyright (c) 2024, Abilian SAS
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from .app import App
    from .env import Env


class Proxy(Protocol):
    """A protocol for proxies (front-ends).

    Currently, the only proxy is Nginx.

    Later we will add more proxies, such as Apache Httpd, Caddy, Traefik, Sozu, etc.
    """

    app: App
    env: Env
    workers: dict[str, str]

    def setup(self) -> None: ...
