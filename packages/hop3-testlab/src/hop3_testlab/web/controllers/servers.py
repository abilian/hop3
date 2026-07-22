# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Server pool + cloud credentials (v2 spec §6).

A *server* is just ``{name, target_id, kind, enabled}`` — *where* a build can run;
``target_id`` is what ``run_once`` takes (``docker`` | an SSH host | ``hetzner``).
*Credentials* are how the worker reaches those targets (provider API token + the
SSH key); they live in the DB like other app-level secrets and are redacted here.
You never pick a server for a build — the dispatcher does.
"""

from __future__ import annotations

from typing import Annotated

from dishka import (
    FromDishka,  # ruff:ignore[typing-only-third-party-import] -- runtime: @inject resolves the annotation
)
from dishka.integrations.litestar import inject
from litestar import Controller, get, post
from litestar.enums import RequestEncodingType
from litestar.exceptions import ValidationException
from litestar.params import Body, FromPath
from litestar.response import Redirect, Template
from litestar.status_codes import HTTP_303_SEE_OTHER

from hop3_testlab.credentials import looks_like_private_key, redact
from hop3_testlab.repositories import (  # ruff:ignore[typing-only-first-party-import] -- runtime: @inject resolves them
    CredentialsRepository,
    ServersRepository,
)
from hop3_testlab.web.guards import auth_guard

_FORM = Annotated[dict, Body(media_type=RequestEncodingType.URL_ENCODED)]


class ServersController(Controller):
    """The server pool and the cloud credentials used to reach run targets."""

    path = "/servers"
    guards = [auth_guard]  # ruff:ignore[mutable-class-default]

    @get("/")
    @inject
    async def index(
        self,
        servers: FromDishka[ServersRepository],
        credentials: FromDishka[CredentialsRepository],
    ) -> Template:
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
        creds = [
            {
                "id": c.id,
                "name": c.name,
                "kind": c.kind,
                "server_id": c.server_id,
                "ssh_key_name": c.ssh_key_name,
                "token": redact(c.api_token),  # never the raw token
                "has_key": bool(c.private_key),
            }
            for c in credentials.list_all()
        ]
        return Template(
            template_name="servers/index.html",
            context={"title": "Servers", "servers": rows, "credentials": creds},
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

    # --- Cloud credentials --------------------------------------------------

    @post("/credentials")
    @inject
    async def create_credential(
        self, data: _FORM, credentials: FromDishka[CredentialsRepository]
    ) -> Redirect:
        """Store a provider credential (API token + optional SSH key) in the DB.

        Secrets are kept on the row and never rendered back; bad input (missing
        name/kind/token, non-integer server_id, malformed key) is refused (400),
        not stored.
        """
        name = (data.get("name") or "").strip()
        kind = (data.get("kind") or "hetzner").strip()
        token = (data.get("api_token") or "").strip()
        if not name or not kind or not token:
            msg = "A credential needs a name, a kind, and an API token."
            raise ValidationException(msg)

        server_id = None
        server_id_raw = (data.get("server_id") or "").strip()
        if server_id_raw:
            try:
                server_id = int(server_id_raw)
            except ValueError:
                msg = f"server_id must be an integer, got {server_id_raw!r}."
                raise ValidationException(msg) from None

        private_key = (data.get("private_key") or "").strip()
        if private_key and not looks_like_private_key(private_key):
            msg = (
                "That doesn't look like a private key — expected a "
                "'-----BEGIN … PRIVATE KEY-----' block."
            )
            raise ValidationException(msg)

        credentials.create(
            name=name,
            kind=kind,
            api_token=token,
            server_id=server_id,
            image=(data.get("image") or "ubuntu-24.04").strip(),
            ssh_key_name=(data.get("ssh_key_name") or "").strip() or None,
            private_key=private_key or None,
        )
        return Redirect(path="/servers", status_code=HTTP_303_SEE_OTHER)

    @post("/credentials/{credential_id:int}/delete")
    @inject
    async def delete_credential(
        self,
        credential_id: FromPath[int],
        credentials: FromDishka[CredentialsRepository],
    ) -> Redirect:
        credentials.delete(credential_id)
        return Redirect(path="/servers", status_code=HTTP_303_SEE_OTHER)
