# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""The Elixir toolchain must not wipe a release that before-build produced.

Phoenix deploys run `MIX_ENV=prod mix release` in `before-build`, which writes
`_build/prod/rel/<app>/bin/<app>`. The toolchain (which runs afterwards) used to
`rmtree(_build)` "to avoid stale artifacts", deleting that release — so the
runtime's `exec _build/prod/rel/<app>/bin/<app>` came up "not found". Each deploy
already extracts a fresh src tree, so there is nothing stale to clean.
"""

from __future__ import annotations

from types import SimpleNamespace

from hop3.toolchains import ElixirToolchain


def test_build_keeps_existing_release(tmp_path, monkeypatch) -> None:
    src = tmp_path / "src"
    bin_dir = src / "_build" / "prod" / "rel" / "myapp" / "bin"
    bin_dir.mkdir(parents=True)
    release_bin = bin_dir / "myapp"
    release_bin.write_text("#!/bin/sh\necho ok\n")
    (src / "mix.exs").write_text("")
    (src / "deps").mkdir()

    tc = ElixirToolchain("myapp", tmp_path)
    # Don't actually shell out to mix; just record that it was asked to.
    monkeypatch.setattr(tc, "_install_hex_and_rebar", lambda *_a, **_k: None)
    monkeypatch.setattr(tc, "shell", lambda *_a, **_k: SimpleNamespace(returncode=0))

    tc.build()

    # The release built by before-build must survive the toolchain's build step.
    assert release_bin.exists(), "toolchain wiped the before-build release"
