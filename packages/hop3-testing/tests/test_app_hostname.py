# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Host derivation for nginx-served apps (audit L5).

The harness probes nginx with the app's server_name. It must inject a synthetic
`{app_name}.test.local` for apps that declare no host (Procfile apps AND
hop3.toml apps), and use the declared host for apps that pin one — otherwise the
probe misses the vhost, falls to default_server, and 301s.
"""

from __future__ import annotations

from hop3_testing.apps.catalog import AppSource
from hop3_testing.apps.preparation import AppPreparation


def _app(
    tmp_path, hop3_toml: str | None = None, *, procfile: bool = False
) -> AppSource:
    if hop3_toml is not None:
        (tmp_path / "hop3.toml").write_text(hop3_toml)
    if procfile:
        (tmp_path / "Procfile").write_text("web: run\n")
    return AppSource(name="app", path=tmp_path)


# ---- AppSource.declared_hostname ----


def test_declared_hostname_from_env_host_name(tmp_path):
    assert (
        _app(tmp_path, '[env]\nHOST_NAME = "hop3.cloud"\n').declared_hostname
        == "hop3.cloud"
    )


def test_declared_hostname_from_domains_list(tmp_path):
    app = _app(tmp_path, '[domains]\nlist = ["a.example.com", "b.example.com"]\n')
    assert app.declared_hostname == "a.example.com"


def test_declared_hostname_domains_wins_over_env(tmp_path):
    app = _app(
        tmp_path,
        '[domains]\nlist = ["a.example.com"]\n[env]\nHOST_NAME = "z.example.com"\n',
    )
    assert app.declared_hostname == "a.example.com"


def test_declared_hostname_none_when_neither(tmp_path):
    assert _app(tmp_path, '[build]\nbuilder = "nix"\n').declared_hostname is None


def test_declared_hostname_none_without_hop3_toml(tmp_path):
    assert _app(tmp_path, procfile=True).declared_hostname is None


def test_declared_hostname_malformed_toml_is_none(tmp_path):
    assert _app(tmp_path, "this is not [[[ valid toml").declared_hostname is None


def test_declared_hostname_first_of_comma_list(tmp_path):
    assert (
        _app(tmp_path, '[env]\nHOST_NAME = "x.test, y.test"\n').declared_hostname
        == "x.test"
    )


def test_declared_hostname_dict_ref_is_none(tmp_path):
    # A dynamic [env] ref can't be resolved statically -> None (so injection happens).
    assert (
        _app(tmp_path, '[env]\nHOST_NAME = { key = "domain" }\n').declared_hostname
        is None
    )


# ---- AppPreparation.test_hostname follows the declared host ----


def test_test_hostname_uses_declared_host(tmp_path):
    app = _app(tmp_path, '[env]\nHOST_NAME = "hop3.cloud"\n')
    assert AppPreparation(app=app, app_name="app-123").test_hostname == "hop3.cloud"


def test_test_hostname_synthetic_when_undeclared(tmp_path):
    app = _app(tmp_path, procfile=True)
    prep = AppPreparation(app=app, app_name="static-hello-123")
    assert prep.test_hostname == "static-hello-123.test.local"


# ---- _ensure_env_file: inject for undeclared (incl. hop3.toml), skip declared ----


def test_env_injected_for_procfile_app(tmp_path):
    prep = AppPreparation(app=_app(tmp_path, procfile=True), app_name="proc")
    prep.temp_dir = tmp_path
    prep._ensure_env_file()
    assert (tmp_path / "ENV").read_text() == "HOST_NAME=proc.test.local\n"


def test_env_injected_for_hop3_toml_static_app(tmp_path):
    # THE L5 REGRESSION: a hop3.toml app with no declared host now gets HOST_NAME
    # too (previously injection was gated on has_procfile, so it was skipped).
    prep = AppPreparation(
        app=_app(tmp_path, '[build]\nbuilder = "nix"\n'), app_name="static"
    )
    prep.temp_dir = tmp_path
    prep._ensure_env_file()
    assert (tmp_path / "ENV").read_text() == "HOST_NAME=static.test.local\n"


def test_env_skipped_when_app_declares_host(tmp_path):
    app = _app(tmp_path, '[env]\nHOST_NAME = "hop3.cloud"\n')
    prep = AppPreparation(app=app, app_name="declared")
    prep.temp_dir = tmp_path
    prep._ensure_env_file()
    assert not (tmp_path / "ENV").exists()  # the app's own host wins; probe uses it
