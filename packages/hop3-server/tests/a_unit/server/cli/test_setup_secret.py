# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Secret-key config write must be 0600 and atomic (audit M1, CWE-732)."""

from __future__ import annotations

import stat

import toml

from hop3.server.cli.setup import _write_secret_config, server_restart_command


def test_secret_config_written_owner_only(tmp_path):
    cfg = tmp_path / "hop3-server.toml"
    _write_secret_config(cfg, {"HOP3_SECRET_KEY": "s3cret", "OTHER": 1})

    mode = stat.S_IMODE(cfg.stat().st_mode)
    assert mode == 0o600, f"secret file must be 0600, got {oct(mode)}"
    assert toml.load(cfg) == {"HOP3_SECRET_KEY": "s3cret", "OTHER": 1}


def test_secret_config_tightens_preexisting_loose_file(tmp_path):
    # A pre-existing world-readable config must end up 0600 after the write.
    cfg = tmp_path / "hop3-server.toml"
    cfg.write_text("OTHER = 1\n")
    cfg.chmod(0o644)

    _write_secret_config(cfg, {"OTHER": 1, "HOP3_SECRET_KEY": "k"})

    assert stat.S_IMODE(cfg.stat().st_mode) == 0o600


def test_restart_hint_uses_systemd_when_it_is_pid_1(tmp_path):
    comm = tmp_path / "comm"
    comm.write_text("systemd\n")

    assert server_restart_command(comm) == "systemctl restart hop3-server"


def test_restart_hint_uses_supervisor_otherwise(tmp_path):
    # The old hint, `sudo systemctl restart hop3`, named no real unit and
    # did nothing under supervisor.
    comm = tmp_path / "comm"
    comm.write_text("supervisord\n")

    assert server_restart_command(comm) == "supervisorctl restart hop3-server"
