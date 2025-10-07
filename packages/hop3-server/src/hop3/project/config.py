# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Application configuration management.

This module implements the "Convention over Configuration" principle:
- Procfile is the convention (default, simple)
- hop3.toml is configuration (optional, advanced)
- Precedence: hop3.toml > Procfile > defaults
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hop3.project.hop3_config import Hop3Config
from hop3.project.procfile import Procfile

if TYPE_CHECKING:
    from pathlib import Path


class AppConfig:
    """Application configuration manager.

    Supports multiple configuration sources with precedence:
    1. hop3.toml (if present) - Advanced configuration
    2. Procfile (if present) - Simple convention
    3. Defaults - Fallback values

    Attributes:
        app_dir: Root directory of the application
        procfile: Parsed Procfile (may be empty if not present)
        hop3_config: Parsed hop3.toml (may be empty if not present)
        app_json: Parsed app.json (Heroku compatibility, not used yet)
        has_procfile: True if Procfile was found
        has_hop3_toml: True if hop3.toml was found
    """

    app_dir: Path
    procfile: Procfile
    hop3_config: Hop3Config
    app_json: dict
    has_procfile: bool
    has_hop3_toml: bool

    @property
    def workers(self) -> dict:
        """Get worker processes with precedence: hop3.toml > Procfile.

        Returns:
            Dictionary mapping worker names to commands
        """
        # Start with Procfile workers (convention)
        workers = dict(self.procfile.workers)

        # Override/extend with hop3.toml workers (configuration)
        if self.has_hop3_toml:
            hop3_workers = self.hop3_config.get_workers_from_run_section()
            workers.update(hop3_workers)

        return workers

    @property
    def web_workers(self):
        """Get web worker processes.

        Returns:
            Dictionary of web workers (wsgi, jwsgi, rwsgi, web)
        """
        web_worker_names = {"wsgi", "jwsgi", "rwsgi", "web"}
        return {k: v for k, v in self.workers.items() if k in web_worker_names}

    @property
    def pre_build(self):
        """Get prebuild command with precedence: hop3.toml > Procfile.

        Returns:
            Prebuild command string, empty if not defined
        """
        # Check hop3.toml first
        if self.has_hop3_toml:
            before_build = self.hop3_config.before_build_commands
            if before_build:
                return " && ".join(before_build)

        # Fall back to Procfile
        return self.workers.get("prebuild", "")

    @property
    def post_build(self):
        """Get postbuild command.

        Returns:
            Postbuild command string, empty if not defined
        """
        return self.workers.get("postbuild", "")

    @property
    def pre_run(self):
        """Get prerun command with precedence: hop3.toml > Procfile.

        Returns:
            Prerun command string, empty if not defined
        """
        # Check hop3.toml first
        if self.has_hop3_toml:
            before_run = self.hop3_config.before_run_commands
            if before_run:
                return " && ".join(before_run)

        # Fall back to Procfile
        return self.workers.get("prerun", "")

    @property
    def src_dir(self):
        return self.app_dir / "src"

    @classmethod
    def from_dir(cls, path: Path) -> AppConfig:
        self = cls()
        self.app_dir = path
        self.parse()
        return self

    def parse(self) -> None:
        self.parse_hop3()  # Parse hop3.toml first (if exists)
        self.parse_procfile()  # Parse Procfile second (if exists)
        self.parse_app_json()

    def parse_procfile(self) -> None:
        # See: https://devcenter.heroku.com/articles/procfile
        procfile_path = self.get_file("Procfile")
        if procfile_path:
            self.procfile = Procfile.from_file(procfile_path)
            self.has_procfile = True
        else:
            # Procfile is optional - use empty defaults
            self.procfile = Procfile()
            self.has_procfile = False

    def get_file(self, filename: str) -> Path | None:
        """Search for a file, first in the "hop3" subdirectory, then in the
        root.

        Input:
        - filename: str - The name of the file to search for.

        Returns:
        - Path | None: The Path object of the file if found, otherwise None.
        """
        path = self.src_dir / "hop3" / filename
        if path.exists():
            return path

        path = self.src_dir / filename
        if path.exists():
            return path

        return None

    def parse_app_json(self) -> None:
        """Parse application-specific JSON data.

        This is intended to process and interpret JSON data relevant to
        the application. It doesn't take any parameters nor does it
        return any values.
        """
        # See: https://devcenter.heroku.com/articles/app-json-schema
        # self.app_json = json.loads(Path("app.json").read_text())
        self.app_json = {}

    def parse_hop3(self) -> None:
        """Parse the hop3.toml configuration file if present."""
        hop3_path = self.get_file("hop3.toml")
        if hop3_path:
            self.hop3_config = Hop3Config.from_file(hop3_path)
            self.has_hop3_toml = True
        else:
            # hop3.toml is optional - use empty defaults
            self.hop3_config = Hop3Config()
            self.has_hop3_toml = False

    def get_worker(self, name: str):
        """Retrieve a worker's details by name from the procfile.

        Input:
        - name (str): The name of the worker to retrieve.

        Returns:
        - str: Details of the worker if found, otherwise an empty string.
        """
        # Attempt to retrieve the worker's details from the 'workers' dictionary.
        return self.procfile.workers.get(name, "")

    def __repr__(self) -> str:
        return f"<AppConfig {self.app_dir}>"

    def to_dict(self) -> dict[str, Any]:
        """
        Serializes the AppConfig instance into a dictionary.

        Returns:
            A dictionary representation of the application configuration.
        """
        return {
            "app_dir": str(self.app_dir),
            "src_dir": str(self.src_dir),
            "has_procfile": self.has_procfile,
            "has_hop3_toml": self.has_hop3_toml,
            "procfile": {
                "workers": self.workers,
                "web_workers": self.web_workers,
                "pre_build": self.pre_build,
                "post_build": self.post_build,
                "pre_run": self.pre_run,
            },
            "app_json": self.app_json,
            "hop3_config": self.hop3_config.to_dict() if self.has_hop3_toml else {},
        }
