# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""LeWAF engine — compiles a per-app ``[waf]`` policy to a SecLang rules file.

Deliberately imports only the (pure) compiler, **never** ``lewaf`` at module
level: this module is imported by ``scan_package('hop3.plugins')`` on every
server start, but ``lewaf`` is an optional extra (``hop3-server[waf]``, Python
3.12+). The proxy-lifecycle methods that do need ``lewaf`` (start/stop/reload)
arrive with the proxy-running slice and must import it lazily.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3.waf import compile_policy

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from hop3.project.schema import WafSection


class LeWafEngine:
    """Generates LeWAF SecLang rules files; one ``<app>.conf`` per WAF-enabled app."""

    name = "lewaf"

    def __init__(self, rules_dir: Path | None = None) -> None:
        # None → resolve from HopConfig lazily (production); tests pass a tmp dir.
        self._rules_dir = rules_dir

    @property
    def rules_dir(self) -> Path:
        if self._rules_dir is not None:
            return self._rules_dir
        from hop3.config import config  # noqa: PLC0415

        return config.WAF_RULES

    def _rules_path(self, app_name: str) -> Path:
        return self.rules_dir / f"{app_name}.conf"

    def configure_app(
        self, app_name: str, policy: WafSection, networks: Mapping[str, list[str]]
    ) -> Path:
        """Compile the policy and write ``<rules_dir>/<app_name>.conf``.

        Raises ``WafCompileError`` (from the compiler) if the policy can't be
        expressed on the engine — the caller turns that into a loud deploy abort.
        """
        path = self._rules_path(app_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(compile_policy(app_name, policy, networks))
        return path

    def remove_app(self, app_name: str) -> None:
        """Remove the app's rules file (on destroy or when WAF is disabled)."""
        self._rules_path(app_name).unlink(missing_ok=True)
