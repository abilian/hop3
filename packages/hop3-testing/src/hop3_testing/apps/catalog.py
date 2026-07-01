# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Test application data class for deployment sessions."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AppSource:
    """Represents a test application for deployment.

    This is a simple data class used by DeploymentSession to track
    app metadata during deployment and testing.
    """

    name: str
    path: Path
    category: str = ""
    description: str = ""

    @property
    def has_check_script(self) -> bool:
        """Check if app has a check.py script."""
        return (self.path / "check.py").exists()

    @property
    def has_procfile(self) -> bool:
        """Check if app has a Procfile.

        Checks for Procfile in:
        1. Root directory (standard location)
        2. hop3/ subdirectory (alternate config path)
        """
        return (self.path / "Procfile").exists() or (
            self.path / "hop3" / "Procfile"
        ).exists()

    @property
    def declared_hostname(self) -> str | None:
        """The hostname this app pins for itself in hop3.toml, or None.

        An app "declares its own hostname" when its hop3.toml sets either a
        ``[domains].list`` entry or a plain-string ``[env].HOST_NAME``. In that
        case the harness must NOT inject ``{app_name}.test.local`` (the app's
        own value wins at deploy, and the nginx probe must target the app's real
        server_name). Returns the first declared host (the primary server_name),
        or None when the app declares none — Procfile-only apps, or a hop3.toml
        with neither [domains] nor a string [env].HOST_NAME (audit L5).
        """
        hop3_toml = self.path / "hop3.toml"
        if not hop3_toml.exists():
            return None
        try:
            with hop3_toml.open("rb") as f:
                data = tomllib.load(f)
        except (tomllib.TOMLDecodeError, OSError):
            return None

        domains = data.get("domains")
        if isinstance(domains, dict):
            hosts = domains.get("list")
            if isinstance(hosts, list) and hosts:
                return str(hosts[0])

        env = data.get("env")
        if isinstance(env, dict):
            host_name = env.get("HOST_NAME")
            # Only a plain-string HOST_NAME yields a usable probe host; a dynamic
            # [env] ref ({ key = ... }) can't be resolved statically.
            if isinstance(host_name, str) and host_name:
                # HOST_NAME may carry several space/comma-separated hosts; the
                # first is the primary server_name.
                return host_name.replace(",", " ").split()[0]

        return None
