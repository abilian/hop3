# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
Install a modern Elixir (>= 1.15): Phoenix's phx_new rejects the distro's 1.14.

We keep the distro Erlang/OTP and drop in a precompiled Elixir matching the
installed OTP major version, symlinked into /usr/local/bin.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from hop3_installer.server_installer import deps_common


def _ok(stdout: str = "") -> MagicMock:
    return MagicMock(returncode=0, stdout=stdout, stderr="")


def test_elixir_version_gate():
    assert deps_common._elixir_at_least("Elixir 1.17.3 (Erlang/OTP 25)", (1, 15))
    assert deps_common._elixir_at_least("Elixir 1.15.0", (1, 15))
    assert not deps_common._elixir_at_least("Elixir 1.14.0", (1, 15))
    assert not deps_common._elixir_at_least("no version here", (1, 15))


def test_detect_otp_major_parses_release():
    with patch.object(deps_common, "run_cmd", return_value=_ok("25")):
        assert deps_common._detect_otp_major() == "25"
    with patch.object(deps_common, "run_cmd", return_value=_ok("26.1.2")):
        assert deps_common._detect_otp_major() == "26"
    with patch.object(deps_common, "run_cmd", return_value=MagicMock(returncode=1)):
        assert deps_common._detect_otp_major() is None


def test_install_elixir_skips_when_recent_enough():
    with (
        patch.object(deps_common, "cmd_exists", return_value=True),
        patch.object(
            deps_common, "run_cmd", return_value=_ok("Elixir 1.17.3")
        ) as run_cmd,
    ):
        deps_common.install_elixir()

    joined = [" ".join(c.args[0]) for c in run_cmd.call_args_list]
    assert not any("curl" in c for c in joined)  # no download when already recent


def test_install_elixir_downloads_otp_matching_build_and_symlinks():
    def fake_run(cmd, **kw):
        text = cmd if isinstance(cmd, str) else " ".join(cmd)
        if "otp_release" in text:
            return _ok("25")
        if "--version" in text:
            return _ok("Elixir 1.17.3 (compiled with Erlang/OTP 25)")
        return _ok("")

    calls: list = []

    def recording_run(cmd, **kw):
        calls.append(cmd)
        return fake_run(cmd, **kw)

    with (
        # elixir absent (so the version gate fails -> install); erl present
        patch.object(deps_common, "cmd_exists", side_effect=lambda c: c == "erl"),
        patch.object(deps_common, "run_cmd", side_effect=recording_run),
        patch.object(deps_common, "Spinner"),
        patch.object(deps_common, "create_symlink", return_value=True) as symlink,
        patch.object(deps_common.Path, "mkdir"),
        patch.object(deps_common.Path, "exists", return_value=True),
        patch.object(deps_common.Path, "chmod"),
    ):
        deps_common.install_elixir()

    joined = [c if isinstance(c, str) else " ".join(c) for c in calls]
    # downloaded the OTP-25 build for the pinned version
    assert any(
        "elixir-otp-25.zip" in c and deps_common.ELIXIR_VERSION in c for c in joined
    )
    # symlinked the elixir/mix/iex/elixirc binaries into /usr/local/bin
    assert symlink.call_count == len(deps_common._ELIXIR_BINS)
