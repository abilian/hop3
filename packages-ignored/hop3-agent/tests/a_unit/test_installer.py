# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from io import StringIO
from pathlib import Path

from hop3.oses.helpers import Linux


def test_put_file() -> None:
    platform = Linux()
    dummy = StringIO("dummy")
    platform.put_file("test", dummy, "/tmp/test_installer.py")

    assert Path("/tmp/test_installer.py").exists()

    Path("/tmp/test_installer.py").unlink()


def test_ensure_link() -> None:
    platform = Linux()
    Path("/tmp/dummy").touch()
    platform.ensure_link("test", "/tmp/dummy", "/tmp/dummy2")

    assert Path("/tmp/dummy2").exists()

    Path("/tmp/dummy").unlink()
    Path("/tmp/dummy2").unlink()
