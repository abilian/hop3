# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""`hop3 version` says "unknown" only for an uninstalled package, never for a bug."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError

import pytest

from hop3.commands import misc
from hop3.commands.misc import VersionCmd


def test_uninstalled_package_reads_unknown(monkeypatch):
    def missing(name: str) -> str:
        raise PackageNotFoundError(name)

    monkeypatch.setattr(misc, "get_version", missing)

    [item] = VersionCmd().call()

    assert item["text"] == "hop3-server unknown (not installed as a package)"


def test_other_failures_are_not_hidden_as_unknown(monkeypatch):
    def broken(name: str) -> str:
        msg = "corrupt METADATA"
        raise ValueError(msg)

    monkeypatch.setattr(misc, "get_version", broken)

    with pytest.raises(ValueError, match="corrupt METADATA"):
        VersionCmd().call()
