# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Profiles controller: edit the test modes (dev / ci / nightly / …) from the UI.

Modes are seeded in code (``hop3_testing.selector.modes.MODES``) and overlaid by
a user overrides file that every mode-resolution path reads. Built-in modes can
be overridden or reset to their default; custom modes can be added or deleted.
"""

from __future__ import annotations

import re

from hop3_testing.selector import (
    BUILTIN_MODE_NAMES,
    VALID_PRIORITIES,
    VALID_TARGETS,
    VALID_TIERS,
    ModeConfig,
    customized_mode_names,
    delete_mode,
    load_modes,
    reset_mode,
    save_mode,
)
from litestar import Controller, Request, get, post
from litestar.response import Redirect, Template
from litestar.status_codes import HTTP_303_SEE_OTHER

from hop3_testlab.web.guards import auth_guard

_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")

_FLASH = {
    "saved": ("ok", "Profile saved."),
    "deleted": ("ok", "Profile deleted."),
    "reset": ("ok", "Profile reset to its built-in default."),
    "invalid": (
        "warn",
        "Invalid profile — check the name, tiers, priorities and targets.",
    ),
    "protected": ("warn", "Built-in profiles can't be deleted — reset them instead."),
}


class ProfilesController(Controller):
    """CRUD for test-execution profiles (modes), persisted to the overrides file."""

    path = "/profiles"
    guards = [auth_guard]  # noqa: RUF012

    @get("/")
    async def index(self, request: Request) -> Template:
        effective = load_modes()
        customized = customized_mode_names()
        rows = [
            {
                "name": name,
                "builtin": name in BUILTIN_MODE_NAMES,
                "customized": name in customized,
                "tiers": cfg.tiers,
                "priorities": cfg.priorities,
                "targets": cfg.targets,
                "description": cfg.description,
                "max_duration_minutes": cfg.max_duration_minutes,
                "representative": cfg.representative,
            }
            for name, cfg in sorted(effective.items())
        ]
        flash_key = str(request.query_params.get("msg") or "")
        return Template(
            template_name="profiles/index.html",
            context={
                "title": "Profiles",
                "profiles": rows,
                "flash": _FLASH.get(flash_key),
                "valid_tiers": list(VALID_TIERS),
                "valid_priorities": list(VALID_PRIORITIES),
                "valid_targets": list(VALID_TARGETS),
            },
        )

    @post("/save")
    async def save(self, request: Request) -> Redirect:
        """Create or override a profile from the submitted form."""
        form = await request.form()
        name = (form.get("name") or "").strip()
        config = _config_from_form(name, form)
        if config is None:
            return _back("invalid")
        save_mode(name, config)
        return _back("saved")

    @post("/reset")
    async def reset(self, request: Request) -> Redirect:
        """Reset a built-in profile to its seed default."""
        form = await request.form()
        name = (form.get("name") or "").strip()
        if name not in BUILTIN_MODE_NAMES:
            return _back("invalid")
        reset_mode(name)
        return _back("reset")

    @post("/delete")
    async def delete(self, request: Request) -> Redirect:
        """Delete a custom profile (built-ins are protected)."""
        form = await request.form()
        name = (form.get("name") or "").strip()
        if name in BUILTIN_MODE_NAMES:
            return _back("protected")
        delete_mode(name)
        return _back("deleted")


def _back(msg: str) -> Redirect:
    return Redirect(path=f"/profiles?msg={msg}", status_code=HTTP_303_SEE_OTHER)


def _checklist(form, key: str, valid: tuple[str, ...]) -> list[str] | None:
    """Selected values for a checkbox group, or None if any is out of range."""
    values = [v for v in form.getall(key) if v]
    if any(v not in valid for v in values):
        return None
    return values


def _config_from_form(name: str, form) -> ModeConfig | None:
    """Validate a submitted profile form into a ModeConfig, or None if invalid."""
    if not _NAME_RE.match(name):
        return None
    tiers = _checklist(form, "tiers", VALID_TIERS)
    priorities = _checklist(form, "priorities", VALID_PRIORITIES)
    targets = _checklist(form, "targets", VALID_TARGETS)
    if not tiers or not priorities or not targets:
        return None  # each group must keep at least one value

    raw_duration = (form.get("max_duration_minutes") or "").strip()
    try:
        max_duration = int(raw_duration) if raw_duration else None
    except ValueError:
        return None
    if max_duration is not None and max_duration <= 0:
        return None

    return ModeConfig(
        name=name,
        tiers=tiers,
        priorities=priorities,
        targets=targets,
        description=(form.get("description") or "").strip(),
        max_duration_minutes=max_duration,
        representative=bool(form.get("representative")),
    )
