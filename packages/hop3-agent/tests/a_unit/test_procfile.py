# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
# SPDX-License-Identifier: MIT

from __future__ import annotations

import tempfile

import pytest

from hop3.project.procfile import Procfile, parse_procfile

PROCFILE1 = """
web: gunicorn -w 4 -b
"""

PROCFILE2 = """
web: gunicorn -w 4 -b
cron: * * * * * echo "hello"
"""

# BAD_PROCFILE1 = """
# web: gunicorn -w 4 -b
# web: gunicorn -w 4 -b
# """

BAD_PROCFILE2 = """
web: gunicorn -w 4 -b
cron: 60 * * * * echo "hello"
"""


def test_procfile_1() -> None:
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8") as f:
        f.write(PROCFILE1)
        f.seek(0)
        workers = parse_procfile(f.name)
        assert workers == {"web": "gunicorn -w 4 -b"}


def test_procfile_2() -> None:
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8") as f:
        f.write(PROCFILE2)
        f.seek(0)
        workers = parse_procfile(f.name)
        assert workers == {
            "web": "gunicorn -w 4 -b",
            "cron": '* * * * * echo "hello"',
        }


def test_procfile_3() -> None:
    procfile = Procfile.from_str(PROCFILE1)
    assert procfile.web_workers == {"web": "gunicorn -w 4 -b"}
    assert procfile.workers == {"web": "gunicorn -w 4 -b"}


def test_procfile_4() -> None:
    procfile = Procfile.from_str(PROCFILE2)
    assert procfile.web_workers == {"web": "gunicorn -w 4 -b"}
    assert procfile.workers == {
        "web": "gunicorn -w 4 -b",
        "cron": '* * * * * echo "hello"',
    }


def get_bad_procfiles():
    bad_procfiles = [
        objs for (name, objs) in globals().items() if name.startswith("BAD_PROCFILE")
    ]
    return bad_procfiles


@pytest.mark.parametrize("bad_procfile", get_bad_procfiles())
def test_bad_procfiles(bad_procfile) -> None:
    with pytest.raises(ValueError):  # noqa: PT011
        Procfile.from_str(bad_procfile)
