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

from hop3_installer.server_installer import nginx

#: The longest name DNS allows.
MAX_HOSTNAME_LENGTH = 253


def test_the_bucket_holds_the_longest_legal_hostname():
    match = re.search(
        r"server_names_hash_bucket_size (\d+);", nginx.NGINX_HTTP_SETTINGS
    )
    assert match
    assert int(match.group(1)) > MAX_HOSTNAME_LENGTH


def test_the_settings_are_written_where_http_includes_them(tmp_path, monkeypatch):
    target = tmp_path / "conf.d" / "hop3-http.conf"
    monkeypatch.setattr(nginx, "NGINX_HTTP_SETTINGS_PATH", target)

    nginx._write_http_settings()

    assert target.read_text() == nginx.NGINX_HTTP_SETTINGS
    assert nginx.NGINX_HTTP_SETTINGS_PATH.parent.name == "conf.d"


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
        calls: list[list[str]] = []
        monkeypatch.setattr(nginx, "run_cmd", lambda cmd, **_kw: calls.append(cmd))
        nginx.setup_nginx(SimpleNamespace(skip_nginx=True))
        return calls

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
