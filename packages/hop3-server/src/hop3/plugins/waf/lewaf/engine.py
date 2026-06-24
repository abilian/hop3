# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""LeWAF engine — compiles a per-app ``[waf]`` policy to a SecLang rules file
and builds the ``lewaf-proxy`` command that fronts the app.

Deliberately imports only the (pure) compiler + CRS locator, **never** ``lewaf``
at module level: this module is imported by ``scan_package('hop3.plugins')`` on
every server start, but ``lewaf`` is an optional extra (``hop3-server[waf]``,
Python 3.12+). ``proxy_command`` only assembles an argv (no import); actually
running the proxy is the deployer's job (Emperor vassal) / the test's.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from hop3.waf import WafCompileError, compile_bans, compile_rules_file, crs_dir

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from hop3.project.schema import WafSection


class LeWafEngine:
    """Generates LeWAF SecLang rules files; one ``<app>.conf`` per WAF-enabled app."""

    name = "lewaf"

    def __init__(
        self, rules_dir: Path | None = None, log_dir: Path | None = None
    ) -> None:
        # None → resolve from HopConfig lazily (production); tests pass tmp dirs.
        self._rules_dir = rules_dir
        self._log_dir = log_dir

    @property
    def rules_dir(self) -> Path:
        if self._rules_dir is not None:
            return self._rules_dir
        from hop3.config import config  # noqa: PLC0415

        return config.WAF_RULES

    @property
    def log_dir(self) -> Path:
        if self._log_dir is not None:
            return self._log_dir
        # Tests pass only rules_dir; co-locate the audit log there so they stay
        # hermetic. Production (no args) uses the configured WAF_LOG.
        if self._rules_dir is not None:
            return self._rules_dir
        from hop3.config import config  # noqa: PLC0415

        return config.WAF_LOG

    def _rules_path(self, app_name: str) -> Path:
        return self.rules_dir / f"{app_name}.conf"

    def _bans_path(self, app_name: str) -> Path:
        return self.rules_dir / f"{app_name}.bans.conf"

    def _config_path(self, app_name: str) -> Path:
        return self.rules_dir / f"{app_name}.yaml"

    def audit_path(self, app_name: str) -> Path:
        """JSONL audit stream the proxy writes and the ban scorer reads."""
        return self.log_dir / f"{app_name}.audit.jsonl"

    def configure_app(
        self, app_name: str, policy: WafSection, networks: Mapping[str, list[str]]
    ) -> Path:
        """Compile the full rules file (CRS baseline + access overlay) to
        ``<rules_dir>/<app_name>.conf`` and write the ``<app_name>.yaml`` proxy
        config (``rule_files`` + JSONL ``audit_logging``).

        Returns the rules-file path. Raises ``WafCompileError`` (from the
        compiler) if the policy can't be expressed on the engine — the caller
        turns that into a loud deploy abort.
        """
        rules_path = self._rules_path(app_name)
        rules_path.parent.mkdir(parents=True, exist_ok=True)
        rules_path.write_text(compile_rules_file(app_name, policy, networks, crs_dir()))

        # The ban denylist is a separate file the scorer rewrites; create it
        # empty if absent (preserve active bans across a redeploy). Loaded BEFORE
        # the policy so a banned source is rejected first (ADR 050 §2 order).
        bans_path = self._bans_path(app_name)
        if not bans_path.exists():
            bans_path.write_text(compile_bans([]))

        audit_path = self.audit_path(app_name)
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        # The proxy loads rules via the YAML `rule_files:` path (full SecLang
        # parser) — the only path that handles the CRS Include directives — and
        # writes one JSONL audit line per blocked request for the ban scorer.
        self._config_path(app_name).write_text(
            "rule_files:\n"
            f'  - "{bans_path}"\n'
            f'  - "{rules_path}"\n'
            "audit_logging:\n"
            "  enabled: true\n"
            f'  output: "{audit_path}"\n'
            "  format: json\n"
            "  mask_sensitive: true\n"
        )
        return rules_path

    def write_bans(self, app_name: str, banned: list[str]) -> Path:
        """Rewrite the app's ban denylist file; return its path (scorer applies
        it by then reloading the proxy)."""
        bans_path = self._bans_path(app_name)
        bans_path.parent.mkdir(parents=True, exist_ok=True)
        bans_path.write_text(compile_bans(banned))
        return bans_path

    def remove_app(self, app_name: str) -> None:
        """Remove the app's rules / config / bans / audit files (destroy)."""
        self._rules_path(app_name).unlink(missing_ok=True)
        self._bans_path(app_name).unlink(missing_ok=True)
        self._config_path(app_name).unlink(missing_ok=True)
        self.audit_path(app_name).unlink(missing_ok=True)

    def validate(self, app_name: str) -> None:
        """Dry-run: load the compiled rules into the engine, raising on any parse
        error — the compile-before-commit gate (ADR 050 §5).

        Lazily imports ``lewaf`` (the ``waf`` extra); a missing extra is itself a
        loud failure the caller turns into an actionable deploy abort.
        """
        from lewaf.integration import WAF, WAFConfig  # noqa: PLC0415 - optional extra

        try:
            WAF(WAFConfig(rule_files=[str(self._rules_path(app_name))]))
        except Exception as e:
            msg = f"generated WAF rules for '{app_name}' failed to load: {e}"
            raise WafCompileError(msg) from e

    def proxy_command(
        self,
        app_name: str,
        upstream_url: str,
        listen_port: int,
        *,
        listen_host: str = "127.0.0.1",
        trusted_proxy_count: int = 1,
    ) -> list[str]:
        """The ``lewaf-proxy`` argv that fronts ``upstream_url`` for ``app_name``.

        Run via the hop3 launcher (``_proxy_main``) with the same interpreter as
        the server venv (where the ``waf`` extra installs ``lewaf``), so it needs
        no PATH lookup. The launcher uses LeWAF's YAML ``rule_files`` path — the
        only one that loads the CRS (the stock ``lewaf-proxy --rules-file`` can't,
        see ``_proxy_main``). ``trusted_proxy_count=1`` makes LeWAF read the real
        client IP from the single nginx hop's ``X-Forwarded-For`` and ignore
        client-forged entries (Security invariant 1). The app's web socket must
        be reachable only via this proxy (Security invariant 3).
        """
        return [
            sys.executable,
            "-m",
            "hop3.plugins.waf.lewaf._proxy_main",
            "--upstream",
            upstream_url,
            "--config",
            str(self._config_path(app_name)),
            "--host",
            listen_host,
            "--port",
            str(listen_port),
            "--trusted-proxy-count",
            str(trusted_proxy_count),
        ]
