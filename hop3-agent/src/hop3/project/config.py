# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from pathlib import Path

from hop3.project.procfile import Procfile


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
            raise ValueError(f"Procfile not found in {self.app_dir}")

        self.procfile = Procfile.from_file(procfile_path)

    def get_file(self, filename: str) -> Path | None:
        """Search for a file, first in the hop3 subdirectory, then in the root."""
        path = self.app_dir / "hop3" / filename
        if not path.exists():
            path = self.app_dir / filename
        if not path.exists():
            return None
        return path

    def parse_app_json(self):
        pass
        # See: https://devcenter.heroku.com/articles/app-json-schema
        # self.app_json = json.loads(Path("app.json").read_text())

    def parse_hop3(self):
        pass

    def get_worker(self, name: str):
        return self.procfile.workers.get(name, "")

    def __repr__(self):
        return f"<AppConfig {self.app_dir}>"
