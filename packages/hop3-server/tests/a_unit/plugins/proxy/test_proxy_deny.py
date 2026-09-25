# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
Paths the proxy never answers: ``[proxy] deny``, and hidden files for PHP.

PHP apps keep data under the tree the proxy serves (a SQLite file, compiled
templates, uploads) and protect it with an upstream ``.htaccess``. nginx and
Caddy never read one, so the deny has to be in the vhost itself.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from hop3.core.artifacts import (
    ARTIFACT_FILENAME,
    BuildArtifact,
    ProxySettings,
    RuntimeConfig,
    load_proxy_settings,
)
from hop3.core.env import Env
from hop3.lib.console import Abort
from hop3.orm import App
from hop3.plugins.proxy.caddy import CaddyVirtualHost
from hop3.plugins.proxy.nginx import NginxVirtualHost
from hop3.plugins.proxy.traefik import TraefikVirtualHost
from hop3.project.schema import ProxySection


@pytest.fixture
def app(tmp_path, monkeypatch) -> App:
    monkeypatch.setattr(App, "app_path", property(lambda self: tmp_path))
    monkeypatch.setattr(App, "src_path", property(lambda self: tmp_path / "src"))
    return App(name="testapp")


def built(app: App, **runtime: object) -> App:
    BuildArtifact(kind="php", app_name=app.name, runtime=RuntimeConfig(**runtime)).save(
        app.app_path / ARTIFACT_FILENAME
    )
    return app


def conf(proxy, app: App) -> str:
    env = Env({
        "APP": app.name,
        "PORT": "8000",
        "HOST_NAME": "testapp.example.org",
        "BIND_ADDRESS": "127.0.0.1",
        "PHP_DOCUMENT_ROOT": "/home/hop3/apps/testapp/src",
    })
    vhost = proxy(app, env, {"web": "x"})
    vhost.setup_backend()
    vhost.extra_setup()
    return vhost.get_proxy_conf()


# --- the key ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("declared", "normalized"),
    [
        (["/data"], ("/data",)),
        (["/data/"], ("/data",)),
        (["/_data/templates_c", "/storage"], ("/_data/templates_c", "/storage")),
    ],
)
def test_deny_paths_are_normalized(declared, normalized):
    assert ProxySection.model_validate({"deny": declared}).deny == normalized


@pytest.mark.parametrize(
    "path",
    ["data", "/", "", "/data/../etc", "/./data", "/data//x", "/da ta", "/data$"],
)
def test_a_deny_path_that_is_not_a_plain_url_path_is_refused(path):
    """Each entry is rendered into proxy config, so nothing but a path gets in."""
    with pytest.raises(ValidationError, match="deny entry"):
        ProxySection.model_validate({"deny": [path]})


def test_the_artifact_carries_the_deny_list(app):
    built(app, proxy_deny=["/data"])

    assert load_proxy_settings(app.app_path) == ProxySettings(deny=("/data",))


# --- rendering --------------------------------------------------------------


def test_nginx_refuses_the_path_and_everything_beneath_it(app):
    rendered = conf(NginxVirtualHost, built(app, proxy_deny=["/data"]))

    assert "location = /data { return 404; }" in rendered
    # `^~`: the prefix wins over the `.php` regex, so a script there is not run.
    assert "location ^~ /data/ { return 404; }" in rendered


def test_caddy_refuses_the_path_and_everything_beneath_it(app):
    rendered = conf(CaddyVirtualHost, built(app, proxy_deny=["/data"]))

    assert "@hop3_denied path /data /data/*" in rendered
    assert "respond @hop3_denied 404" in rendered


@pytest.mark.parametrize("proxy", [NginxVirtualHost, CaddyVirtualHost])
def test_nothing_is_denied_by_default(proxy, app):
    rendered = conf(proxy, built(app))

    assert "hop3_denied" not in rendered
    assert "return 404; }" not in rendered
    assert "_DENY" not in rendered  # the placeholder was expanded, to nothing


def test_traefik_refuses_an_app_that_denies_a_path(app):
    vhost = TraefikVirtualHost(
        built(app, proxy_deny=["/data"]), Env({"HOST_NAME": "x"}), {"web": "x"}
    )

    with pytest.raises(Abort, match=r"declares \[proxy\] deny \(/data\)"):
        vhost.refuse_unsupported()


# --- hidden files under a PHP document root --------------------------------


def test_nginx_never_serves_a_hidden_file_from_a_php_tree(app):
    rendered = conf(NginxVirtualHost, built(app, backend_protocol="fastcgi"))

    hidden = r"location ~ /\.(?!well-known/) { return 404; }"
    assert hidden in rendered
    # First among the regex locations: a script in a hidden directory is
    # refused, never handed to php-fpm.
    assert rendered.index(hidden) < rendered.index(r"location ~ [^/]\.php")


def test_caddy_never_serves_a_hidden_file_from_a_php_tree(app):
    rendered = conf(CaddyVirtualHost, built(app, backend_protocol="fastcgi"))

    assert "path_regexp /[.]" in rendered
    assert "not path /.well-known/*" in rendered
    assert "respond @hop3_hidden 404" in rendered
