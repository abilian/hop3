# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
nginx must accept the longest hostname an app can be given.

With nginx's default `server_names_hash_bucket_size` (64), a 48-character
name (`hop3-tuto-nix-gen-flask.135.181.203.156.sslip.io`) failed `nginx -t`,
and the deploy with it.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest
from hop3_installer.common import InstallStepError
from hop3_installer.server_installer import nginx

#: The longest name DNS allows.
MAX_HOSTNAME_LENGTH = 253


def test_the_bucket_holds_the_longest_legal_hostname():
    match = re.search(
        r"server_names_hash_bucket_size (\d+);", nginx.NGINX_HTTP_SETTINGS
    )
    assert match
    assert int(match.group(1)) > MAX_HOSTNAME_LENGTH


#: hop3-server's `request_max_body_size`, in bytes.
SERVER_UPLOAD_LIMIT = 200 * 1024 * 1024


def test_the_admin_domain_accepts_what_hop3_server_accepts():
    """
    A 27 MB deploy archive was refused by nginx's 1 MB default.

    hop3-server accepts the archive; the platform vhost sets no limit of its
    own and inherits this one.
    """
    match = re.search(r"client_max_body_size (\d+)m;", nginx.NGINX_HTTP_SETTINGS)
    assert match
    assert int(match.group(1)) * 1024 * 1024 >= SERVER_UPLOAD_LIMIT


def test_the_settings_are_written_where_http_includes_them(tmp_path, monkeypatch):
    target = tmp_path / "conf.d" / "hop3-http.conf"
    monkeypatch.setattr(nginx, "NGINX_HTTP_SETTINGS_PATH", target)

    nginx._write_http_settings()

    assert target.read_text() == nginx.NGINX_HTTP_SETTINGS
    assert nginx.NGINX_HTTP_SETTINGS_PATH.parent.name == "conf.d"


#: /proc/uptime of the fake host: 1000.00 s, so ticks run from 100000.
UPTIME_TICKS = 1000 * 100


class Nginx:
    """
    ``run_cmd`` on a host whose nginx answers a reload as ``outcome`` says.

    "applies" forks a worker; "rejects" logs an ``[emerg]`` and forks none, as
    nginx does on a listen conflict; "ignores" does neither. A worker from
    before the reload is always there.
    """

    def __init__(self, tmp_path, monkeypatch, outcome: str = "applies") -> None:
        self.proc = tmp_path / "proc"
        self.log = tmp_path / "error.log"
        self.outcome = outcome
        self.calls: list[list[str]] = []
        self.proc.mkdir()
        (self.proc / "uptime").write_text("1000.00 3000.00\n")
        self._worker(1, UPTIME_TICKS - 500)
        monkeypatch.setattr(nginx, "PROC_ROOT", self.proc)
        monkeypatch.setattr(nginx, "NGINX_ERROR_LOG", self.log)
        monkeypatch.setattr(nginx.os, "sysconf", lambda _name: 100)
        monkeypatch.setattr(nginx, "run_cmd", self)

    def _worker(self, pid: int, start: int) -> None:
        entry = self.proc / str(pid)
        entry.mkdir()
        (entry / "cmdline").write_bytes(b"nginx: worker process\x00")
        fields = " ".join(["S", *["0"] * 18, str(start), "0"])
        (entry / "stat").write_text(f"{pid} (nginx) {fields}\n")

    def __call__(self, cmd, **_kw) -> None:
        self.calls.append(cmd)
        if cmd != ["nginx", "-s", "reload"]:
            return
        if self.outcome == "applies":
            self._worker(2, UPTIME_TICKS + 3)
        elif self.outcome == "rejects":
            self.log.write_text(
                "[emerg] 7#7: bind() to 0.0.0.0:1935 failed (98: Address in use)\n"
            )


class TestAReloadIsVerified:
    """
    `nginx -s reload` exits 0 before nginx reads the config; on a listen
    conflict nginx then logs `[emerg]` and keeps the old one. The installer
    printed "Nginx reloaded" either way.
    """

    def test_a_reload_that_forks_new_workers_is_applied(self, tmp_path, monkeypatch):
        nginx_host = Nginx(tmp_path, monkeypatch)
        nginx.reload_nginx()
        assert nginx_host.calls == [["nginx", "-s", "reload"]]

    def test_a_rejected_reload_fails_with_nginxs_own_line(self, tmp_path, monkeypatch):
        Nginx(tmp_path, monkeypatch, outcome="rejects")
        with pytest.raises(InstallStepError, match=r"\[emerg\].*Address in use"):
            nginx.reload_nginx()

    def test_an_error_logged_before_the_reload_is_not_its_cause(
        self, tmp_path, monkeypatch
    ):
        Nginx(tmp_path, monkeypatch, outcome="ignores")
        (tmp_path / "error.log").write_text("[emerg] an old incident\n")
        monkeypatch.setattr(nginx, "RELOAD_VERIFY_S", 0.0)
        with pytest.raises(InstallStepError, match="no new worker process"):
            nginx.reload_nginx()

    def test_the_settings_reload_is_verified_too(self, tmp_path, monkeypatch):
        Nginx(tmp_path, monkeypatch, outcome="rejects")
        monkeypatch.setattr(nginx, "NGINX_HTTP_SETTINGS_PATH", tmp_path / "x.conf")
        monkeypatch.setattr(nginx, "process_manager_pending", lambda: False)
        with pytest.raises(InstallStepError, match="did not apply"):
            nginx.reconcile_http_settings()


class TestARedeployReconcilesThem:
    """
    A redeploy runs the installer with `--skip-nginx`. The setting first
    shipped inside the skipped step, so it reached fresh installs only, and
    the server it was written for kept failing.
    """

    @staticmethod
    def _redeploy(monkeypatch, target, *, pending=False) -> list[list[str]]:
        monkeypatch.setattr(nginx, "NGINX_HTTP_SETTINGS_PATH", target)
        monkeypatch.setattr(nginx, "process_manager_pending", lambda: pending)
        host = Nginx(target.parent, monkeypatch)
        nginx.setup_nginx(SimpleNamespace(skip_nginx=True))
        return host.calls

    def test_an_existing_server_gets_them_validated_and_reloaded(
        self, tmp_path, monkeypatch
    ):
        target = tmp_path / "hop3-http.conf"

        calls = self._redeploy(monkeypatch, target)

        assert target.read_text() == nginx.NGINX_HTTP_SETTINGS
        assert calls == [["nginx", "-t"], ["nginx", "-s", "reload"]]

    def test_up_to_date_settings_leave_nginx_alone(self, tmp_path, monkeypatch):
        target = tmp_path / "hop3-http.conf"
        target.write_text(nginx.NGINX_HTTP_SETTINGS)

        assert self._redeploy(monkeypatch, target) == []

    def test_no_reload_before_the_process_manager_runs_nginx(
        self, tmp_path, monkeypatch
    ):
        calls = self._redeploy(monkeypatch, tmp_path / "hop3-http.conf", pending=True)

        assert calls == [["nginx", "-t"]]


class TestTheSiteReachesARunningNginx:
    """
    Under a process manager the install wrote the site and stopped there, so a
    running nginx kept the old one: after `--clean`, the removed vhosts.
    """

    @staticmethod
    def _start(tmp_path, monkeypatch, *, systemd: bool, pending: bool = False) -> list:
        monkeypatch.setattr(nginx, "process_manager_pending", lambda: pending)
        host = Nginx(tmp_path, monkeypatch)
        nginx._start_nginx(systemd=systemd)
        return host.calls

    def test_a_running_nginx_under_a_process_manager_is_reloaded(
        self, tmp_path, monkeypatch
    ):
        calls = self._start(tmp_path, monkeypatch, systemd=False)
        assert calls == [["nginx", "-s", "reload"]]

    def test_a_rejected_reload_under_a_process_manager_stops_the_install(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(nginx, "process_manager_pending", lambda: False)
        Nginx(tmp_path, monkeypatch, outcome="rejects")
        with pytest.raises(InstallStepError, match=r"\[emerg\]"):
            nginx._start_nginx(systemd=False)

    def test_an_nginx_the_process_manager_has_not_started_is_left_to_it(
        self, tmp_path, monkeypatch
    ):
        assert self._start(tmp_path, monkeypatch, systemd=False, pending=True) == []

    def test_systemd_restarts_it(self, tmp_path, monkeypatch):
        assert self._start(tmp_path, monkeypatch, systemd=True) == [
            ["systemctl", "enable", "nginx"],
            ["systemctl", "restart", "nginx"],
        ]
