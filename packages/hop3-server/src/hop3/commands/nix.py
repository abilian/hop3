# Copyright (c) 2025-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Nix-related CLI commands."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, ClassVar

from hop3.core.roles import Role
from hop3.lib.args import pop_app_flag, reject_extra_args
from hop3.lib.registry import register

from ._base import Command
from ._errors import command_context
from ._helpers import get_app
from ._response import blob, error, summary

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from hop3.orm import App


@register
@dataclass(frozen=True)
class NixEjectCmd(Command):
    """
    Print the hop3.nix an app's [nix] template generates, to edit by hand.

    Usage: hop3 nix eject [--app <app>] > hop3.nix

    Generates the expression the NixBuilder builds at deploy time from the
    app's [nix] section and writes it to stdout, with a header naming the
    template and the date. Save it as hop3.nix in your project, remove the
    [nix] section from hop3.toml (a build refuses an app that has both), and
    deploy: the file is yours from then on.

    Use this when the template can't express your app's needs.

    Examples:
        hop3 nix eject --app myapp > hop3.nix
    """

    # Hidden per ADR 036 D3: removed from user-visible CLI surface. Still
    # invokable explicitly (`hop3 nix eject --app <app>`) for dev/recovery.
    name: ClassVar[tuple[str, ...]] = ("nix", "eject")
    min_role: ClassVar[Role] = Role.DEPLOYER
    hidden: ClassVar[bool] = True
    db_session: Session

    def call(self, *args: str, **kwargs: object) -> list[dict]:
        app_name, rest = pop_app_flag(args)
        if not app_name:
            raise self.usage_error()
        reject_extra_args(rest)
        with command_context(" ".join(self.name), app_name=app_name):
            app = get_app(self.db_session, app_name)
            return self._eject(app)

    def _eject(self, app: App) -> list[dict]:
        from hop3.plugins.build.nix.gen import (  # ruff:ignore[import-outside-top-level]
            generate,
        )
        from hop3.plugins.build.nix.gen.templates.base import (  # ruff:ignore[import-outside-top-level]
            ejected,
        )
        from hop3.plugins.build.nix.gen.toml_adapter import (  # ruff:ignore[import-outside-top-level]
            app_spec_from_config,
        )
        from hop3.project.config import (  # ruff:ignore[import-outside-top-level]
            AppConfig,
        )

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
                    "nix eject only works for template-based Nix apps."
                )
            ]

        spec = app_spec_from_config(
            nix_config, hop3_config.get("metadata", {}), app.name
        )
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        nix_text = ejected(generate(spec), spec.template, today)
        encoded = base64.b64encode(nix_text.encode()).decode("ascii")
        return [
            blob(encoded, filename="hop3.nix"),
            summary(
                f"ejected '{app.name}' from template '{spec.template}'. Save it as "
                "hop3.nix, remove [nix] from hop3.toml, and deploy."
            ),
        ]
