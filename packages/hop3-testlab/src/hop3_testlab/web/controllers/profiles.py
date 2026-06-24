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
from litestar.exceptions import NotFoundException, ValidationException
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


def _selection_to_form(selection: dict) -> dict:
    """Reverse of `_selection_from_form`: flatten a selection dict back to the
    form's string fields, so the edit form can be pre-filled."""
    out = {"mode": selection.get("mode", "")}
    for key in _LIST_RULES:
        value = selection.get(key) or []
        out[key] = ", ".join(value) if isinstance(value, list) else str(value)
    return out


def _validate_source(source_url: str, source_ref: str) -> None:
    """Fail loud on bad source input rather than storing a profile that breaks
    at run. Shared by create and update."""
    if not is_allowed_source_url(source_url):
        msg = f"Unsafe or unsupported source URL: {source_url!r}"
        raise ValidationException(msg)
    if not source_ref:
        msg = "source_ref must not be empty"
        raise ValidationException(msg)


def _profile_row(profile) -> dict:
    return {
        "id": profile.id,
        "name": profile.name,
        "source": f"{profile.source_name} @ {profile.source_ref}",
        "platform_ref": profile.platform_ref or "(engine default)",
        "selection": profile.selection or {},
    }


def _profile_detail(profile) -> dict:
    return {
        "id": profile.id,
        "name": profile.name,
        "source_name": profile.source_name,
        "source_url": profile.source_url,
        "source_ref": profile.source_ref,
        "platform_ref": profile.platform_ref,
        "selection": profile.selection or {},
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
    }


def _unique_copy_name(profiles: ProfilesRepository, base: str) -> str:
    """A free name for a duplicate (the column is unique): '<base> (copy)', then
    '<base> (copy 2)', ..."""
    candidate = f"{base} (copy)"
    n = 2
    while profiles.by_name(candidate) is not None:
        candidate = f"{base} (copy {n})"
        n += 1
    return candidate


def _slug_from_url(url: str) -> str:
    """A short, filesystem-friendly label for a source, derived from the repo
    URL's last path segment. It only names the source's git cache dir (never used
    for lookup), so it needn't be unique or user-supplied."""
    leaf = url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git").strip()
    return leaf or "repo"


def _fields_from_form(data: dict) -> dict | None:
    """Validate and extract the writable profile fields from a create/edit form.

    Returns None when the form is blank (no name / no source URL) so the caller
    can bounce back to the form; raises ValidationException on bad input.
    """
    name = (data.get("name") or "").strip()
    source_url = (data.get("source_url") or "").strip()
    source_ref = (data.get("source_ref") or "main").strip()
    if not name or not source_url:
        return None
    _validate_source(source_url, source_ref)
    return {
        "name": name,
        # Auto-derived from the URL — names the git cache dir, not a user field.
        "source_name": _slug_from_url(source_url),
        "source_url": source_url,
        "source_ref": source_ref,
        "platform_ref": (data.get("platform_ref") or "").strip() or None,
        "selection": _selection_from_form(data),
    }


class ProfilesController(Controller):
    """Build profiles: list / view / create / edit / duplicate / start / delete."""

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

    @get("/{profile_id:int}")
    @inject
    async def detail(
        self, profile_id: FromPath[int], profiles: FromDishka[ProfilesRepository]
    ) -> Template:
        profile = profiles.get(profile_id)
        if profile is None:
            msg = f"No profile {profile_id}"
            raise NotFoundException(msg)
        return Template(
            template_name="profiles/detail.html",
            context={
                "title": f"Profile: {profile.name}",
                "p": _profile_detail(profile),
            },
        )

    @get("/{profile_id:int}/edit")
    @inject
    async def edit_form(
        self, profile_id: FromPath[int], profiles: FromDishka[ProfilesRepository]
    ) -> Template:
        profile = profiles.get(profile_id)
        if profile is None:
            msg = f"No profile {profile_id}"
            raise NotFoundException(msg)
        return Template(
            template_name="profiles/edit.html",
            context={
                "title": f"Edit: {profile.name}",
                "p": _profile_detail(profile),
                "form": _selection_to_form(profile.selection or {}),
                "modes": list_modes(),
            },
        )

    @post("/")
    @inject
    async def create(
        self, data: _FORM, profiles: FromDishka[ProfilesRepository]
    ) -> Redirect:
        fields = _fields_from_form(data)
        if fields is None:  # blank form
            return Redirect(path="/profiles", status_code=HTTP_303_SEE_OTHER)
        profiles.create(**fields)
        return Redirect(path="/profiles", status_code=HTTP_303_SEE_OTHER)

    @post("/{profile_id:int}/edit")
    @inject
    async def update(
        self,
        profile_id: FromPath[int],
        data: _FORM,
        profiles: FromDishka[ProfilesRepository],
    ) -> Redirect:
        if profiles.get(profile_id) is None:
            msg = f"No profile {profile_id}"
            raise NotFoundException(msg)
        fields = _fields_from_form(data)
        if fields is None:  # blank form — back to the editor
            return Redirect(
                path=f"/profiles/{profile_id}/edit", status_code=HTTP_303_SEE_OTHER
            )
        # The name column is unique; refuse a rename onto another profile loudly
        # rather than 500 on the constraint.
        clash = profiles.by_name(fields["name"])
        if clash is not None and clash.id != profile_id:
            msg = f"A profile named {fields['name']!r} already exists"
            raise ValidationException(msg)
        profiles.update(profile_id, **fields)
        return Redirect(path=f"/profiles/{profile_id}", status_code=HTTP_303_SEE_OTHER)

    @post("/{profile_id:int}/duplicate")
    @inject
    async def duplicate(
        self, profile_id: FromPath[int], profiles: FromDishka[ProfilesRepository]
    ) -> Redirect:
        """Copy a profile under a fresh name and land on its edit form."""
        src = profiles.get(profile_id)
        if src is None:
            msg = f"No profile {profile_id}"
            raise NotFoundException(msg)
        copy = profiles.create(
            name=_unique_copy_name(profiles, src.name),
            source_name=src.source_name,
            source_url=src.source_url,
            source_ref=src.source_ref,
            platform_ref=src.platform_ref,
            selection=dict(src.selection or {}),
        )
        return Redirect(
            path=f"/profiles/{copy.id}/edit", status_code=HTTP_303_SEE_OTHER
        )

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
