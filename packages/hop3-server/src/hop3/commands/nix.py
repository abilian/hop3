# Copyright (c) 2025-2026, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

"""Nix-related CLI commands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from hop3.lib.registry import register

from ._base import Command
from ._errors import command_context
from ._helpers import get_app
from ._response import error, text

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from hop3.orm import App


@register
@dataclass(frozen=True)
class NixEjectCmd(Command):
    """Generate and save a hop3.nix file from the [nix] template config.

    This materializes the auto-generated Nix expression as a real file
    in the app's source directory. After ejection, the NixBuilder uses
    the committed hop3.nix instead of regenerating from the template.

    Use this when the template can't express your app's needs and you
    need to customize the Nix expression directly.
    """

    name: ClassVar[str] = "nix:eject"
    db_session: Session

    def run(self, app_name: str) -> list:
        with command_context(self.name, app_name=app_name):
            app = get_app(self.db_session, app_name)
            return self._eject(app)

    def _eject(self, app: App) -> list:
        from hop3.plugins.build.nix.gen import generate  # noqa: PLC0415
        from hop3.plugins.build.nix.gen.toml_adapter import (  # noqa: PLC0415
            app_spec_from_config,
        )
        from hop3.project.config import AppConfig  # noqa: PLC0415

        # Load app config
        try:
            app_config = AppConfig.from_dir(app.app_path)
        except ValueError as e:
            return [error(f"Can't read app config: {e}")]

        if not app_config.has_hop3_toml:
            return [error("App has no hop3.toml")]

        hop3_config = app_config.hop3_config.to_dict()
        nix_config = hop3_config.get("nix", {})
        if not nix_config.get("template"):
            return [
                error(
                    "No [nix].template in hop3.toml. "
                    "nix:eject only works for template-based Nix apps."
                )
            ]

        # Check if hop3.nix already exists
        nix_file = app.src_path / "hop3.nix"
        if nix_file.exists():
            return [
                error(
                    f"hop3.nix already exists at {nix_file}. "
                    "Remove it first if you want to re-eject from the template."
                )
            ]

        # Generate
        metadata = hop3_config.get("metadata", {})
        spec = app_spec_from_config(nix_config, metadata, app.name)
        nix_text = generate(spec)

        # Add ejection header
        from datetime import datetime, timezone  # noqa: PLC0415

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        header = (
            f"# Ejected from template '{spec.template}' on {now}.\n"
            f"# This file is now yours to customize.\n"
            f"# The [nix] section in hop3.toml is ignored when hop3.nix exists.\n"
        )
        # Replace the GENERATED header with ejected header
        nix_text = nix_text.replace(
            f"# GENERATED from template '{spec.template}' by hop3-nix-gen.\n"
            f"# Run 'hop3 nix:eject {spec.pname}' to materialize for customization.",
            header.rstrip(),
        )

        # Write
        nix_file.write_text(nix_text)

        return [
            text(
                f"Ejected hop3.nix for '{app.name}' from template '{spec.template}'.\n"
                f"File: {nix_file}\n"
                f"The [nix] section in hop3.toml is now ignored — edit hop3.nix directly."
            )
        ]
