# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
# SPDX-License-Identifier: MIT

from __future__ import annotations

import tempfile
from pathlib import Path

from hop3.project.config import AppConfig

PROCFILE1 = """
web: gunicorn -w 4 -b
"""

PROCFILE2 = """
prebuild: echo "hello"
postbuild: echo "goodbye"
prerun: echo "prerun"

web: gunicorn -w 4 -b
cron: * * * * * echo "hello"
"""


def test_config_1() -> None:
    with tempfile.TemporaryDirectory() as d:
        dir_path = Path(d)
        Path(dir_path, "Procfile").write_text(PROCFILE1)
        config = AppConfig.from_dir(dir_path)
        assert config.web_workers == {"web": "gunicorn -w 4 -b"}
        assert config.workers == {"web": "gunicorn -w 4 -b"}


def test_config_2() -> None:
    with tempfile.TemporaryDirectory() as d:
        dir_path = Path(d)
        Path(dir_path, "Procfile").write_text(PROCFILE2)
        config = AppConfig.from_dir(dir_path)
        assert config.workers == {
            "web": "gunicorn -w 4 -b",
            "cron": '* * * * * echo "hello"',
            "prebuild": 'echo "hello"',
            "postbuild": 'echo "goodbye"',
            "prerun": 'echo "prerun"',
        }

        assert config.web_workers == {"web": "gunicorn -w 4 -b"}
        assert config.pre_build == 'echo "hello"'
        assert config.post_build == 'echo "goodbye"'
        assert config.pre_run == 'echo "prerun"'
