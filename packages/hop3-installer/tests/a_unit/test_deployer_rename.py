# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
The `hop3-deploy` → `hop3-deploy-server` rename (ADR 052 D10).

`hop3-deploy` stays as a deprecated warn-and-delegate shim so no existing
invocation breaks during the one-release migration window.
"""

from __future__ import annotations

from hop3_installer import deprecation
from hop3_installer.deployer import cli


def test_deprecated_main_warns_and_delegates(monkeypatch, capsys):
    deprecation._WARNED.clear()
    ran = {}

    def _stub() -> int:
        ran["yes"] = True
        return 0

    monkeypatch.setattr(cli, "main", _stub)
    rc = cli.deprecated_main()

    assert rc == 0
    assert ran.get("yes")  # delegated to the real main
    err = capsys.readouterr().err
    assert "'hop3-deploy' is deprecated" in err
    assert "hop3-deploy-server" in err
