# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Toolchains and the remaining server steps abort, except the best-effort ones.

Node's tooling, Go, Postfix, acme.sh, the SSH keys: each failure used to be a
warning the install carried past, or not even that (the SSH key step could not
raise, and printed "SSH keys configured" whatever happened). Rust, Leiningen
and Elixir stay best-effort, and abort when requested with `--with`. See
notes/installer-fail-loud-audit.md.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from hop3_installer.cli_installer import verify as cli_verify
from hop3_installer.common import CommandError, InstallStepError
from hop3_installer.server_installer import (
    deps,
    deps_common,
    email,
    installer,
    python,
    s3,
)
from hop3_installer.server_installer.config import ServerInstallerConfig


def _failed(*_a, **_kw) -> SimpleNamespace:
    return SimpleNamespace(returncode=1, stdout="", stderr="boom")


def test_node_without_npm_stops_the_install():
    with (
        patch.object(deps_common, "cmd_exists", return_value=False),
        pytest.raises(InstallStepError, match="npm is not on PATH"),
    ):
        deps_common.install_node_global_packages()


@pytest.mark.parametrize("required", [False, True])
def test_leiningen_is_best_effort_unless_requested(required, capsys):
    with (
        patch.object(deps_common, "Spinner"),
        patch.object(deps_common, "run_cmd", side_effect=_failed),
        patch.object(deps_common.Path, "exists", return_value=False),
    ):
        if required:
            with pytest.raises(CommandError):
                deps_common.install_leiningen(required=True)
        else:
            deps_common.install_leiningen(required=False)
            assert "Failed to download Leiningen" in capsys.readouterr().out


def test_the_toolchains_follow_their_with_flags(monkeypatch):
    seen: dict[str, bool] = {}
    monkeypatch.setattr(installer, "install_node_global_packages", lambda: None)
    for name in ("rust_toolchain", "leiningen", "elixir"):
        monkeypatch.setattr(
            installer,
            f"install_{name}",
            lambda *, required, name=name: seen.__setitem__(name, required),
        )
    installer._install_optional_toolchains(
        ServerInstallerConfig(features={"clojure", "elixir"})
    )
    assert seen == {"rust_toolchain": False, "leiningen": True, "elixir": True}


def test_an_unknown_distribution_stops_the_install():
    with pytest.raises(InstallStepError, match="--skip-deps"):
        deps.install_system_deps("arch", ServerInstallerConfig())


def test_a_failed_postfix_install_stops_the_install():
    """It warned, and the failure surfaced only when a backend was selected."""
    with pytest.raises(CommandError):
        email._report(SimpleNamespace(returncode=100, stdout="", stderr="E: no"))


def test_ssh_keys_that_cannot_be_configured_stop_the_install(tmp_path, monkeypatch):
    keys = tmp_path / "authorized_keys"
    keys.write_text("ssh-ed25519 AAAA test\n")
    calls: list[dict] = []

    def run_as_hop3(argv, **kwargs):
        calls.append(kwargs)
        if kwargs.get("check"):
            raise CommandError(cmd=argv, returncode=1, stderr="invalid key")
        return SimpleNamespace(returncode=1, stdout="", stderr="invalid key")

    real_path = python.Path
    monkeypatch.setattr(
        python,
        "Path",
        lambda p: keys if str(p) == "/root/.ssh/authorized_keys" else real_path(p),
    )
    monkeypatch.setattr(python, "run_as_hop3", run_as_hop3)
    monkeypatch.setattr(python.os, "chown", lambda *_a: None)
    monkeypatch.setattr(python.pwd, "getpwnam", lambda _n: SimpleNamespace(pw_uid=0))
    monkeypatch.setattr(python.grp, "getgrnam", lambda _n: SimpleNamespace(gr_gid=0))

    with pytest.raises(CommandError):
        python.setup_ssh_keys()
    assert calls[0].get("check") is True


def test_garage_waits_for_a_process_manager_that_is_not_running_yet(capsys):
    """
    `/etc/supervisor/conf.d` exists before supervisord runs, and taking it for
    a running supervisord sent `supervisorctl` at nothing: the failure was
    ignored, until the step started raising and stopped every `--with s3`
    container install.
    """
    with (
        patch.object(s3, "has_systemd", return_value=False),
        patch.object(s3, "process_manager_pending", return_value=True),
        patch.object(s3, "run_cmd", side_effect=AssertionError("no command")),
    ):
        s3._start_service()
    assert "when the process manager does" in capsys.readouterr().out


def test_a_cli_that_does_not_run_fails_verification(tmp_path, monkeypatch):
    """It returned True after an error, and "Installation complete!" followed."""
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "hop3").touch()
    monkeypatch.setattr(cli_verify, "CLI_VENV_DIR", tmp_path)
    monkeypatch.setattr(
        cli_verify,
        "run_cmd",
        lambda *_a, **_kw: SimpleNamespace(returncode=1, stdout="", stderr="Traceback"),
    )
    assert cli_verify.verify_installation() is False
