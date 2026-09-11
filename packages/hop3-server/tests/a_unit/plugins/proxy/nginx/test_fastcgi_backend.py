# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
nginx speaks to each backend in the protocol that backend understands.

`proxy_pass` at a php-fpm pool sends it HTTP, which it does not speak. The
protocol is read from the build artifact — the same field the readiness gate
reads, so the two cannot disagree about what an app is.
"""

from __future__ import annotations

import pytest

from hop3.core.artifacts import ARTIFACT_FILENAME, BuildArtifact, RuntimeConfig
from hop3.core.env import Env
from hop3.orm import App
from hop3.plugins.proxy.nginx import NginxVirtualHost

ENV = {
    "APP": "testapp",
    "PORT": "8000",
    "HOST_NAME": "testapp.com",
    "BIND_ADDRESS": "127.0.0.1",
}


@pytest.fixture
def app_path(tmp_path, monkeypatch):
    monkeypatch.setattr(App, "app_path", property(lambda self: tmp_path))
    return tmp_path


def write_artifact(path, protocol: str) -> None:
    BuildArtifact(
        kind="php", app_name="testapp", runtime=RuntimeConfig(backend_protocol=protocol)
    ).save(path / ARTIFACT_FILENAME)


def rendered(document_root: str = "/home/hop3/apps/testapp/src/public") -> str:
    env = Env(dict(ENV))
    env["PHP_DOCUMENT_ROOT"] = document_root
    host = NginxVirtualHost(App(name="testapp"), env, {"web": "php-fpm -F"})
    host.setup_backend()
    host.setup_cache()
    host.setup_static()
    host.extra_setup()
    return host.get_proxy_conf()


class TestAFastcgiAppGetsAFastcgiVhost:
    def test_it_passes_to_the_pool_not_over_http(self, app_path) -> None:
        write_artifact(app_path, "fastcgi")
        config = rendered()
        assert "fastcgi_pass 127.0.0.1:8000;" in config
        assert "proxy_pass" not in config

    def test_it_serves_from_the_declared_document_root(self, app_path) -> None:
        write_artifact(app_path, "fastcgi")
        assert "root /home/hop3/apps/testapp/src/public;" in rendered()

    def test_unknown_paths_go_to_the_front_controller(self, app_path) -> None:
        write_artifact(app_path, "fastcgi")
        assert "try_files $uri $uri/ /index.php?$query_string;" in rendered()

    def test_a_missing_script_is_refused_rather_than_routed(self, app_path) -> None:
        """Handing an absent .php path to index.php is the RCE shape."""
        write_artifact(app_path, "fastcgi")
        assert "if (!-f $document_root$fastcgi_script_name) { return 404; }" in (
            rendered()
        )

    def test_nginx_variables_survive_expansion(self, app_path) -> None:
        """`expand_vars` leaves names it does not know alone; check it did."""
        write_artifact(app_path, "fastcgi")
        config = rendered()
        assert "$document_root$fastcgi_script_name" in config
        assert "$fastcgi_path_info" in config


class TestEveryOtherAppIsUnchanged:
    def test_an_http_app_still_gets_proxy_pass(self, app_path) -> None:
        write_artifact(app_path, "http")
        config = rendered()
        assert "proxy_pass http://127.0.0.1:8000;" in config
        assert "fastcgi_pass" not in config

    def test_an_app_with_no_artifact_still_gets_proxy_pass(self, app_path) -> None:
        """Everything deployed before the field existed speaks HTTP."""
        config = rendered()
        assert "proxy_pass http://127.0.0.1:8000;" in config
        assert "fastcgi_pass" not in config
