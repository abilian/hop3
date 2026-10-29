# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
nix.conf and the daemon restart are reconciled on every install.

They were not: once hop3's `.bashrc` sourced the Nix profile, an early return
skipped the nix.conf write and the daemon restart, so a redeploy never brought
a server's nix.conf up to Hop3's settings (`sandbox = relaxed`, `min-free = 0`).
"""

from __future__ import annotations

import subprocess

from hop3_installer.server_installer import nix


class Recorder:
    """A runner that records every command and succeeds."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, cmd, **_kw) -> subprocess.CompletedProcess:
        self.calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, "", "")


class LocalShell:
    """Stands in for `su - hop3 -c`: runs the script here, records it."""

    def __init__(self) -> None:
        self.scripts: list[str] = []

    def __call__(self, script, *, check=False, stdin_text=None, **_kw):
        self.scripts.append(script)
        result = subprocess.run(
            ["sh", "-c", script],
            input=stdin_text,
            capture_output=True,
            text=True,
            check=False,
        )
        if check and result.returncode:
            raise subprocess.CalledProcessError(result.returncode, script)
        return result


def _configure(tmp_path, *, daemon_mode: bool, shell=None) -> Recorder:
    run = Recorder()
    nix._configure_hop3_nix_access(
        daemon_mode=daemon_mode,
        home=tmp_path / "home",
        etc_conf=tmp_path / "etc" / "nix" / "nix.conf",
        run=run,
        as_hop3_shell=shell or LocalShell(),
        systemd=True,
    )
    return run


def _settings(text: str) -> list[str]:
    return [line for line in text.splitlines() if "=" in line]


def test_an_already_configured_daemon_install_still_gets_nix_conf(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".bashrc").write_text(f". {nix.NIX_DAEMON_PROFILE}\n")
    conf = tmp_path / "etc" / "nix" / "nix.conf"
    conf.parent.mkdir(parents=True)
    conf.write_text("build-users-group = nixbld\nsandbox = true\n")

    run = _configure(tmp_path, daemon_mode=True)

    assert _settings(conf.read_text()) == [
        "build-users-group = nixbld",
        "sandbox = relaxed",
        "min-free = 0",
    ]
    assert ["systemctl", "enable", "nix-daemon"] in run.calls
    assert ["systemctl", "restart", "nix-daemon"] in run.calls


def test_a_redeploy_restarts_the_daemon_and_leaves_nix_conf_alone(tmp_path):
    (tmp_path / "home").mkdir()
    _configure(tmp_path, daemon_mode=True)
    conf = tmp_path / "etc" / "nix" / "nix.conf"
    first = conf.read_text()
    bashrc = (tmp_path / "home" / ".bashrc").read_text()

    run = _configure(tmp_path, daemon_mode=True)

    assert conf.read_text() == first
    assert (tmp_path / "home" / ".bashrc").read_text() == bashrc
    assert ["systemctl", "enable", "nix-daemon"] in run.calls
    assert ["systemctl", "restart", "nix-daemon"] in run.calls


def test_single_user_conf_is_reconciled_and_given_to_hop3(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".bashrc").write_text(f". {nix.NIX_SINGLE_USER_PROFILE}\n")
    conf = home / ".config" / "nix" / "nix.conf"
    conf.parent.mkdir(parents=True)
    conf.write_text(
        "\n# Hop3 nix settings (see server_installer/nix.py)\nsandbox = relaxed\n"
    )

    run = _configure(tmp_path, daemon_mode=False)

    assert _settings(conf.read_text()) == ["sandbox = relaxed", "min-free = 0"]
    assert not any("nix-daemon" in cmd for cmd in run.calls)


def test_root_never_touches_a_path_under_hop3s_home(tmp_path):
    """
    An app runs as hop3 and can plant `~/.config/nix/nix.conf -> /etc/passwd`.
    Root used to read, rewrite and chown that path on every redeploy.
    """
    home = tmp_path / "home"
    home.mkdir()
    shell = LocalShell()

    runs = [_configure(tmp_path, daemon_mode=False, shell=shell) for _ in range(2)]

    assert not any(str(home) in " ".join(cmd) for run in runs for cmd in run.calls)
    assert any(".bashrc" in script for script in shell.scripts)
    assert any("nix.conf" in script for script in shell.scripts)
    # And a redeploy adds nothing a second time.
    assert (home / ".bashrc").read_text().count("# Nix package manager") == 1


def test_reconciled_nix_conf_is_a_fixed_point():
    once = nix.reconciled_nix_conf("max-jobs = 4\nmin-free = 1G\n")
    assert nix.reconciled_nix_conf(once) == once
    assert _settings(once) == ["max-jobs = 4", "sandbox = relaxed", "min-free = 0"]
