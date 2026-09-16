# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
A recipe's declared document root reaches the pool that serves it.

The knob existed, was documented, validated its input and aborted with a good
message — and could never be set. `document_root()` was handed
``env.get("PHP_DOCUMENT_ROOT")`` from the toolchain's env, which is parsed
from ``<app_path>/ENV``: a file nothing in Hop3 writes. So every recipe that
declared one got silent auto-detection instead, and for an app whose web root
is not a name on the detection list that means serving the project root —
paheko's would have published `data/paheko.sqlite`, its whole database.

These tests run the declaration end to end, because both halves passed on
their own: `document_root()` had unit tests and the schema had a field, while
nothing joined them.

Every app below has a detectable `www/index.php` *and* declares something
else, so a test that passes proves the declaration won rather than that the
two happened to agree. `document_root()`'s own detection cases live in
test_php_fpm.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hop3.core.protocols import BuildContext
from hop3.lib import Abort
from hop3.toolchains.php import PHPToolchain

if TYPE_CHECKING:
    from pathlib import Path


def _php_app(tmp_path: Path, build_section: dict) -> PHPToolchain:
    """
    An app with two plausible web roots and a database beside them.

    `www/` is what detection finds; `httpdocs/` is what the recipe asks for.
    They differ on purpose — if they agreed, a test could not tell a working
    declaration from an ignored one.
    """
    src = tmp_path / "src"
    (src / "www").mkdir(parents=True)
    (src / "www" / "index.php").touch()
    (src / "httpdocs").mkdir()
    (src / "httpdocs" / "index.php").touch()
    (src / "data").mkdir()
    (src / "data" / "app.sqlite").write_text("the whole database")
    return PHPToolchain(
        BuildContext(
            app_name="paheko",
            source_path=src,
            app_config={"hop3_config": {"build": {"build": "true", **build_section}}},
        )
    )


def _served(tc: PHPToolchain, monkeypatch) -> str:
    """What nginx would be told to serve, after a full build."""
    monkeypatch.setattr(
        "hop3.toolchains.php.php_fpm_binary", lambda: "/usr/sbin/php-fpm8.3"
    )
    return tc.build().runtime.env_vars["PHP_DOCUMENT_ROOT"]


class TestTheRecipeDecidesWhereTheWebRootIs:
    def test_the_declaration_is_read_from_the_recipe(self, tmp_path) -> None:
        tc = _php_app(tmp_path, {"document-root": "httpdocs"})
        assert tc.build_option("document-root") == "httpdocs"

    def test_the_declaration_reaches_the_runtime_config(self, tmp_path, monkeypatch):
        """The property under test: it survives the whole build, and it wins."""
        tc = _php_app(tmp_path, {"document-root": "httpdocs"})
        assert _served(tc, monkeypatch) == str(tmp_path / "src" / "httpdocs")

    def test_without_a_declaration_the_front_controller_is_detected(
        self, tmp_path, monkeypatch
    ):
        tc = _php_app(tmp_path, {})
        assert _served(tc, monkeypatch) == str(tmp_path / "src" / "www")

    def test_an_environment_variable_is_not_the_knob(self, tmp_path, monkeypatch):
        """
        `PHP_DOCUMENT_ROOT` is what the toolchain *writes* for nginx to read,
        not something a recipe sets. Leaving it readable as an input too would
        be two spellings of one contract, and the spelling that looks obvious
        is the one that silently did nothing.
        """
        monkeypatch.setenv("PHP_DOCUMENT_ROOT", "data")
        tc = _php_app(tmp_path, {})
        assert _served(tc, monkeypatch) == str(tmp_path / "src" / "www")

    def test_the_data_directory_is_never_what_gets_served(self, tmp_path, monkeypatch):
        """
        The consequence, as its own assertion: whatever the resolution, the
        app's database must not sit under the directory nginx serves.
        """
        tc = _php_app(tmp_path, {"document-root": "httpdocs"})
        served = _served(tc, monkeypatch)
        assert not (tmp_path / "src" / "data" / "app.sqlite").is_relative_to(served)

    def test_a_declared_root_that_is_not_a_directory_aborts(
        self, tmp_path, monkeypatch
    ):
        """
        Loudly, rather than falling back to detection: a recipe that names a
        root means the detected one is wrong for it, so guessing again would
        serve exactly what the declaration was there to avoid.
        """
        tc = _php_app(tmp_path, {"document-root": "nope"})
        with pytest.raises(Abort):
            _served(tc, monkeypatch)
