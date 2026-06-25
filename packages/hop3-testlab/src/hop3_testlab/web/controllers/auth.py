# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Login / logout (session-cookie auth, v1 single admin)."""

from __future__ import annotations

import secrets
from typing import Annotated

from litestar import Controller, Request, get, post
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Redirect, Template
from litestar.status_codes import HTTP_303_SEE_OTHER

from hop3_testlab.config import TestlabConfig

_FORM = Annotated[dict, Body(media_type=RequestEncodingType.URL_ENCODED)]


class AuthController(Controller):
    """Public login/logout endpoints (no guard)."""

    path = "/auth"

    @get("/login", sync_to_thread=False)
    def login_form(self, request: Request) -> Template:
        # ``?retry=1`` lands here after the CSRF handler cleared a wedged token.
        notice = (
            "Your session expired — please sign in again."
            if request.query_params.get("retry")
            else None
        )
        return Template(
            template_name="auth/login.html",
            context={"title": "Sign in", "notice": notice},
        )

    @post("/login", sync_to_thread=False)
    def login(self, data: _FORM, request: Request) -> Template | Redirect:
        config = TestlabConfig.get_instance()
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""
        ok = (
            bool(config.PASSWORD)
            and secrets.compare_digest(username, config.USERNAME)
            and secrets.compare_digest(password, config.PASSWORD)
        )
        if not ok:
            return Template(
                template_name="auth/login.html",
                context={"title": "Sign in", "error": "Invalid credentials"},
            )
        request.set_session({"user_id": username})
        return Redirect(path="/", status_code=HTTP_303_SEE_OTHER)

    @get("/logout", sync_to_thread=False)
    def logout(self, request: Request) -> Redirect:
        request.clear_session()
        return Redirect(path="/auth/login", status_code=HTTP_303_SEE_OTHER)
