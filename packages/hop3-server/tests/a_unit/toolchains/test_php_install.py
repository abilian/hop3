# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The PHP toolchain must not re-run composer over a prebuild's vendor/ tree.

Symfony on a host whose php-redis predates symfony/cache's `ext-redis >= 6.1`
requirement installs in before-build with `--ignore-platform-req=ext-redis`.
The toolchain's own `composer install` omits that flag, so re-running it after
the prebuild already produced vendor/ fails where the prebuild succeeded. When
vendor/ (with its autoloader) is already present, the toolchain step is skipped.
"""

from __future__ import annotations

import pytest

from hop3.core.env import Env
from hop3.toolchains import PHPToolchain, php as php_mod


def test_install_dependencies_skips_when_vendor_exists(tmp_path, monkeypatch) -> None:
    src = tmp_path / "src"
    (src / "vendor").mkdir(parents=True)
    (src / "vendor" / "autoload.php").write_text("<?php\n")
    (src / "composer.json").write_text("{}")

    tc = PHPToolchain("myapp", tmp_path)
    monkeypatch.setattr(php_mod, "emit", lambda *_a, **_k: None)

    def _boom(*_a, **_k):
        pytest.fail("toolchain ran composer install over an existing vendor/")

    monkeypatch.setattr(tc, "shell", _boom)
    tc.install_dependencies(Env({}))  # must skip, must not shell out


def test_install_dependencies_installs_when_no_vendor(tmp_path, monkeypatch) -> None:
    src = tmp_path / "src"
    src.mkdir(parents=True)
    (src / "composer.json").write_text("{}")

    tc = PHPToolchain("myapp", tmp_path)
    monkeypatch.setattr(php_mod, "emit", lambda *_a, **_k: None)
    calls: list[str] = []
    monkeypatch.setattr(tc, "shell", lambda cmd, **_k: calls.append(cmd))

    tc.install_dependencies(Env({}))

    assert any("composer install" in c for c in calls)
