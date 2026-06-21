# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Build profiles — *what* to build (source@ref + platform ref + selection rules).

Replaces the old mode-overrides picker: a profile is a saved composition spec you
**Start** (enqueue), never a hand-picked app list. Apps are chosen by *rules*
(reusing the engine `Selector`); the queue/dispatcher picks the server. (v2 §5)
"""

from __future__ import annotations

from typing import Annotated

from dishka import FromDishka  # noqa: TC002 -- runtime: @inject resolves the annotation
from dishka.integrations.litestar import inject
from hop3_testing.selector.modes import list_modes
from litestar import Controller, get, post
from litestar.enums import RequestEncodingType
from litestar.exceptions import ValidationException
from litestar.params import Body, FromPath
from litestar.response import Redirect, Template
from litestar.status_codes import HTTP_303_SEE_OTHER

from hop3_testlab.repositories import (  # noqa: TC001 -- runtime: @inject resolves them
    BuildQueueRepository,
    ProfilesRepository,
)
from hop3_testlab.sources import is_allowed_source_url
from hop3_testlab.web.guards import auth_guard

_FORM = Annotated[dict, Body(media_type=RequestEncodingType.URL_ENCODED)]

# Free-text rule fields the form offers, each a comma-separated list in the JSON.
_LIST_RULES = ("tiers", "priorities", "types", "tags")


def _selection_from_form(data: dict) -> dict:
    """Build a profile's selection-rule dict from the form (never an app list)."""
    selection: dict = {}
    mode = (data.get("mode") or "").strip()
    if mode:
        selection["mode"] = mode
    for key in _LIST_RULES:
        raw = (data.get(key) or "").strip()
        if raw:
            selection[key] = [v.strip() for v in raw.split(",") if v.strip()]
    return selection


def _profile_row(profile) -> dict:
    return {
        "id": profile.id,
        "name": profile.name,
        "source": f"{profile.source_name} @ {profile.source_ref}",
        "platform_ref": profile.platform_ref or "(engine default)",
        "selection": profile.selection or {},
    }


class ProfilesController(Controller):
    """Build profiles: create / start / delete (no manual app selection)."""

    path = "/profiles"
    guards = [auth_guard]  # noqa: RUF012

    @get("/")
    @inject
    async def index(self, profiles: FromDishka[ProfilesRepository]) -> Template:
        return Template(
            template_name="profiles/index.html",
            context={
                "title": "Profiles",
                "profiles": [_profile_row(p) for p in profiles.list_all()],
                "modes": list_modes(),
            },
        )

    @post("/")
    @inject
    async def create(
        self, data: _FORM, profiles: FromDishka[ProfilesRepository]
    ) -> Redirect:
        name = (data.get("name") or "").strip()
        source_url = (data.get("source_url") or "").strip()
        source_ref = (data.get("source_ref") or "main").strip()
        if not name or not source_url:
            return Redirect(
                path="/profiles", status_code=HTTP_303_SEE_OTHER
            )  # blank form
        # Fail loud on bad input rather than storing a profile that breaks at run.
        if not is_allowed_source_url(source_url):
            msg = f"Unsafe or unsupported source URL: {source_url!r}"
            raise ValidationException(msg)
        if not source_ref:
            msg = "source_ref must not be empty"
            raise ValidationException(msg)
        profiles.create(
            name=name,
            source_name=(data.get("source_name") or "main-repo").strip(),
            source_url=source_url,
            source_ref=source_ref,
            platform_ref=(data.get("platform_ref") or "").strip() or None,
            selection=_selection_from_form(data),
        )
        return Redirect(path="/profiles", status_code=HTTP_303_SEE_OTHER)

    @post("/{profile_id:int}/start")
    @inject
    async def start(
        self,
        profile_id: FromPath[int],
        profiles: FromDishka[ProfilesRepository],
        queue: FromDishka[BuildQueueRepository],
    ) -> Redirect:
        """Start a build: **enqueue** (no target — the dispatcher picks a free
        pool server). Returns to the queue."""
        if profiles.get(profile_id) is None:
            return Redirect(path="/profiles", status_code=HTTP_303_SEE_OTHER)
        queue.enqueue(profile_id, actor="web")
        return Redirect(path="/queue?started=1", status_code=HTTP_303_SEE_OTHER)

    @post("/{profile_id:int}/delete")
    @inject
    async def delete(
        self, profile_id: FromPath[int], profiles: FromDishka[ProfilesRepository]
    ) -> Redirect:
        profiles.delete(profile_id)
        return Redirect(path="/profiles", status_code=HTTP_303_SEE_OTHER)
