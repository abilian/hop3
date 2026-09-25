# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
``NGINX_INCLUDE_FILE`` / ``CADDY_INCLUDE_FILE``: a snippet from the app's repo.

The value used to resolve against the app's directory, one level above the
source tree, so a file shipped in the repository was reported missing unless
the recipe prefixed ``src/``, and a missing file surfaced as a traceback.
"""

from __future__ import annotations

import pytest

from hop3.core.env import Env
from hop3.lib.console import Abort
from hop3.orm import App
from hop3.plugins.proxy.caddy import CaddyVirtualHost
from hop3.plugins.proxy.nginx import NginxVirtualHost

VARIABLE = {
    NginxVirtualHost: "NGINX_INCLUDE_FILE",
    CaddyVirtualHost: "CADDY_INCLUDE_FILE",
}


@pytest.fixture
def app(tmp_path, monkeypatch) -> App:
    monkeypatch.setattr(App, "app_path", property(lambda self: tmp_path))
    monkeypatch.setattr(App, "src_path", property(lambda self: tmp_path / "src"))
    (tmp_path / "src" / "deploy").mkdir(parents=True)
    return App(name="testapp")


def vhost(proxy, app: App, value: str):
    env = Env({"APP": app.name, "HOST_NAME": "t.example.org", VARIABLE[proxy]: value})
    return proxy(app, env, {"web": "x"})


@pytest.mark.parametrize("proxy", [NginxVirtualHost, CaddyVirtualHost])
def test_the_path_is_relative_to_the_source_tree(proxy, app):
    (app.src_path / "deploy" / "extra.conf").write_text("# from the repository\n")

    assert vhost(proxy, app, "deploy/extra.conf").include_file(VARIABLE[proxy]) == (
        "# from the repository\n"
    )


@pytest.mark.parametrize("proxy", [NginxVirtualHost, CaddyVirtualHost])
def test_a_missing_file_is_refused_by_name(proxy, app):
    with pytest.raises(Abort, match=r"deploy/nope\.conf names no file"):
        vhost(proxy, app, "deploy/nope.conf").include_file(VARIABLE[proxy])


@pytest.mark.parametrize("value", ["../ENV", "/etc/hostname", "deploy/../../ENV"])
def test_a_path_outside_the_source_tree_is_refused(app, value):
    """The snippet is copied into the proxy's config: nothing else gets read."""
    (app.app_path / "ENV").write_text("SECRET=x\n")

    with pytest.raises(Abort, match="points outside the app's source tree"):
        vhost(NginxVirtualHost, app, value).include_file("NGINX_INCLUDE_FILE")


def test_a_symlink_out_of_the_tree_is_refused(app):
    (app.app_path / "ENV").write_text("SECRET=x\n")
    (app.src_path / "deploy" / "link.conf").symlink_to(app.app_path / "ENV")

    with pytest.raises(Abort, match="points outside the app's source tree"):
        vhost(NginxVirtualHost, app, "deploy/link.conf").include_file(
            "NGINX_INCLUDE_FILE"
        )


def test_no_variable_includes_nothing(app):
    proxy = NginxVirtualHost(app, Env({"HOST_NAME": "t"}), {"web": "x"})

    assert proxy.include_file("NGINX_INCLUDE_FILE") == ""
