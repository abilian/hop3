# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3.project.procfile import Procfile

if TYPE_CHECKING:
    from pathlib import Path


class AppConfig:
    app_dir: Path
    procfile: Procfile
    # XXX: not used yet
    app_json: dict

    @property
    def workers(self) -> dict:
        return self.procfile.workers

    @property
    def web_workers(self):
        return self.procfile.web_workers

    @property
    def pre_build(self):
        return self.procfile.workers.get("prebuild", "")

    @property
    def post_build(self):
        return self.procfile.workers.get("postbuild", "")

    @property
    def pre_run(self):
        return self.procfile.workers.get("prerun", "")

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
        self.parse_procfile()
        self.parse_app_json()
        self.parse_hop3()

    def parse_procfile(self) -> None:
        # See: https://devcenter.heroku.com/articles/procfile
        procfile_path = self.get_file("Procfile")
        if not procfile_path:
            msg = f"Procfile not found in {self.app_dir}"
            raise ValueError(msg)

        self.procfile = Procfile.from_file(procfile_path)

    def get_file(self, filename: str) -> Path | None:
        """
        Search for a file, first in the "hop3" subdirectory, then in the root.

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
        """
        Parse application-specific JSON data.

        This is intended to process and interpret JSON data
        relevant to the application. It doesn't take any parameters
        nor does it return any values.
        """
        # See: https://devcenter.heroku.com/articles/app-json-schema
        # self.app_json = json.loads(Path("app.json").read_text())

    def parse_hop3(self) -> None:
        """
        Parse th hop3-specific configuration file (currently, none).
        """

    def get_worker(self, name: str):
        """
        Retrieve a worker's details by name from the procfile.

        Input:
        - name (str): The name of the worker to retrieve.

        Returns:
        - str: Details of the worker if found, otherwise an empty string.
        """
        # Attempt to retrieve the worker's details from the 'workers' dictionary.
        return self.procfile.workers.get(name, "")

    def __repr__(self) -> str:
        return f"<AppConfig {self.app_dir}>"
