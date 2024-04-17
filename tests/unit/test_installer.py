# Copyright (c) 2023-2024, Abilian SAS

import os
from io import StringIO
from pathlib import Path

from hop3.oses.helpers import Linux


def test_put_file():
    platform = Linux()
    dummy = StringIO("dummy")
    platform.put_file("test", dummy, "/tmp/test_installer.py")

    assert Path("/tmp/test_installer.py").exists()

    os.unlink("/tmp/test_installer.py")


def test_ensure_link():
    platform = Linux()
    Path("/tmp/dummy").touch()
    platform.ensure_link("test", "/tmp/dummy", "/tmp/dummy2")

    assert Path("/tmp/dummy2").exists()

    os.unlink("/tmp/dummy")
    os.unlink("/tmp/dummy2")
