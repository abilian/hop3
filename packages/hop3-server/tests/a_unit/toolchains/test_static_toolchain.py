# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
StaticToolchain detection: Procfile `static:` OR hop3.toml `[run.workers]`.

A static site must be declarable without a Procfile (convention over
configuration): a ``static`` worker in ``hop3.toml`` is equivalent to a
``static:`` Procfile line.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3.toolchains.static import StaticToolchain

if TYPE_CHECKING:
    from pathlib import Path

_HOP3_TOML = '[metadata]\nid = "app"\n'


def _src(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    return src


def test_accepts_procfile_static(tmp_path: Path):
    src = _src(tmp_path)
    (src / "Procfile").write_text("static: public\n")
    (src / "public").mkdir()
    tc = StaticToolchain("app", tmp_path)
    assert tc.accept()
    assert tc.build().metadata["static_dir"] == "public"


def test_accepts_hop3_toml_worker_without_procfile(tmp_path: Path):
    src = _src(tmp_path)
    (src / "hop3.toml").write_text(_HOP3_TOML + '[run.workers]\nstatic = "dist"\n')
    (src / "dist").mkdir()
    tc = StaticToolchain("app", tmp_path)
    assert tc.accept()  # no Procfile required
    assert tc.build().metadata["static_dir"] == "dist"


def test_accepts_build_static_dir_first_class(tmp_path: Path):
    # [build].static-dir is the first-class, Procfile-free way to set the served
    # directory (e.g. "site"): no Procfile and no worker notation needed.
    src = _src(tmp_path)
    (src / "hop3.toml").write_text(
        _HOP3_TOML + '[build]\ntoolchain = "static"\nstatic-dir = "site"\n'
    )
    (src / "site").mkdir()
    tc = StaticToolchain("app", tmp_path)
    assert tc.accept()
    artifact = tc.build()
    assert artifact.metadata["static_dir"] == "site"
    assert artifact.runtime.workers == {"static": "site"}


def test_build_static_dir_wins_over_worker_and_procfile(tmp_path: Path):
    # Precedence: [build].static-dir > [run.workers].static > Procfile.
    src = _src(tmp_path)
    (src / "Procfile").write_text("static: public\n")
    (src / "hop3.toml").write_text(
        _HOP3_TOML + '[build]\nstatic-dir = "site"\n[run.workers]\nstatic = "dist"\n'
    )
    (src / "site").mkdir()
    tc = StaticToolchain("app", tmp_path)
    assert tc.build().metadata["static_dir"] == "site"


def test_hop3_toml_takes_precedence_over_procfile(tmp_path: Path):
    # hop3.toml is Hop3's own config; a Procfile is a generic, cross-tool file,
    # so hop3.toml wins (matching AppConfig.workers precedence).
    src = _src(tmp_path)
    (src / "Procfile").write_text("static: public\n")
    (src / "hop3.toml").write_text(_HOP3_TOML + '[run.workers]\nstatic = "dist"\n')
    (src / "dist").mkdir()
    tc = StaticToolchain("app", tmp_path)
    assert tc.build().metadata["static_dir"] == "dist"


def test_rejects_when_no_static_declared(tmp_path: Path):
    src = _src(tmp_path)
    (src / "hop3.toml").write_text(_HOP3_TOML)
    tc = StaticToolchain("app", tmp_path)
    assert not tc.accept()


def test_build_declares_static_worker_in_runtime(tmp_path: Path):
    # The served dir is declared as a "static" worker in the artifact runtime —
    # the Procfile-free channel every toolchain uses. The deployer and nginx
    # read this to serve files directly; without it nginx emitted an invalid
    # `upstream 127.0.0.1:0`.
    src = _src(tmp_path)
    (src / "hop3.toml").write_text(_HOP3_TOML + '[run.workers]\nstatic = "dist"\n')
    (src / "dist").mkdir()
    artifact = StaticToolchain("app", tmp_path).build()
    assert artifact.runtime.workers == {"static": "dist"}


def test_build_defaults_to_public_when_toolchain_forced_without_declaration(
    tmp_path: Path,
):
    # `[build].toolchain = "static"` forces the toolchain even though accept() is
    # False (nothing declared). build() must still produce a usable artifact —
    # defaulting the served dir to "public" — so a static site needs no Procfile.
    src = _src(tmp_path)
    (src / "hop3.toml").write_text(_HOP3_TOML)
    (src / "public").mkdir()
    artifact = StaticToolchain("app", tmp_path).build()
    assert artifact.metadata["static_dir"] == "public"
    assert artifact.runtime.workers == {"static": "public"}
