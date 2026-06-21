# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Server pool CRUD — the targets the dispatcher runs builds on (v2 spec §6).

A server is just ``{name, target_id, kind, enabled}``; ``target_id`` is what
``run_once`` takes (``docker`` | an SSH host | ``hetzner``). Credentials stay in
config, never in a row. You never pick a server for a build — the dispatcher does.
"""

from __future__ import annotations

from typing import Annotated

from dishka import FromDishka  # noqa: TC002 -- runtime: @inject resolves the annotation
from dishka.integrations.litestar import inject
from litestar import Controller, get, post
from litestar.enums import RequestEncodingType
from litestar.params import Body, FromPath
from litestar.response import Redirect, Template
from litestar.status_codes import HTTP_303_SEE_OTHER

from hop3_testlab.repositories import (
    ServersRepository,  # noqa: TC001 -- runtime: @inject resolves it
)
from hop3_testlab.web.guards import auth_guard

_FORM = Annotated[dict, Body(media_type=RequestEncodingType.URL_ENCODED)]


class ServersController(Controller):
    """The server pool: targets builds can run on."""

    path = "/servers"
    guards = [auth_guard]  # noqa: RUF012

    @get("/")
    @inject
    async def index(self, servers: FromDishka[ServersRepository]) -> Template:
        rows = [
            {
                "id": s.id,
                "name": s.name,
                "target_id": s.target_id,
                "kind": s.kind,
                "enabled": s.enabled,
            }
            for s in servers.list_all()
        ]
        return Template(
            template_name="servers/index.html",
            context={"title": "Servers", "servers": rows},
        )

    @post("/")
    @inject
    async def create(
        self, data: _FORM, servers: FromDishka[ServersRepository]
    ) -> Redirect:
        name = (data.get("name") or "").strip()
        target_id = (data.get("target_id") or "").strip()
        if name and target_id:
            servers.create(
                name=name, target_id=target_id, kind=(data.get("kind") or "ssh").strip()
            )
        return Redirect(path="/servers", status_code=HTTP_303_SEE_OTHER)

    @post("/{server_id:int}/toggle")
    @inject
    async def toggle(
        self, server_id: FromPath[int], servers: FromDishka[ServersRepository]
    ) -> Redirect:
        server = servers.get(server_id)
        if server is not None:
            servers.update(server_id, enabled=not server.enabled)
        return Redirect(path="/servers", status_code=HTTP_303_SEE_OTHER)

    @post("/{server_id:int}/delete")
    @inject
    async def delete(
        self, server_id: FromPath[int], servers: FromDishka[ServersRepository]
    ) -> Redirect:
        servers.delete(server_id)
        return Redirect(path="/servers", status_code=HTTP_303_SEE_OTHER)
