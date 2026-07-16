# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Integration tests: generate each spec and check basic properties."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hop3.plugins.build.nix.gen.registry import generate, list_templates

from .conftest import ALL_FIXTURE_NAMES

if TYPE_CHECKING:
    from hop3.plugins.build.nix.gen.spec import AppSpec


def test_templates_registered():
    names = list_templates()
    assert "prebuilt-binary" in names
    assert "prebuilt-archive" in names
    assert "php-app" in names
    assert "node-prebuilt" in names
    assert "java-war" in names
    assert "python-venv" in names
    assert "nixpkgs-wrapper" in names


@pytest.mark.parametrize("fixture_name", ALL_FIXTURE_NAMES)
def test_spec_generates_without_error(
    fixture_name: str, request: pytest.FixtureRequest
):
    spec: AppSpec = request.getfixturevalue(fixture_name)
    result = generate(spec)
    assert isinstance(result, str)
    assert len(result) > 100


@pytest.mark.parametrize("fixture_name", ALL_FIXTURE_NAMES)
def test_output_contains_required_elements(
    fixture_name: str, request: pytest.FixtureRequest
):
    spec: AppSpec = request.getfixturevalue(fixture_name)
    output = generate(spec)

    assert "import (fetchTarball {" in output  # pinned nixpkgs, not <nixpkgs>
    assert "<nixpkgs>" not in output
    assert "\nlet\n" in output
    assert f'pname = "{spec.pname}"' in output
    assert "package = app;" in output
    assert "$out/hop3/runtime.json" in output

    if spec.version:
        assert f'version = "{spec.version}"' in output
    else:
        assert "version =" in output


@pytest.mark.parametrize("fixture_name", ALL_FIXTURE_NAMES)
def test_output_uses_nix_escaped_vars(
    fixture_name: str, request: pytest.FixtureRequest
):
    spec: AppSpec = request.getfixturevalue(fixture_name)
    output = generate(spec)

    has_shell_vars = any("${" in v for v in spec.local_vars.values()) or any(
        "${" in v for v in spec.env_exports.values()
    )
    if has_shell_vars:
        assert "''${" in output


def test_prebuilt_binary_has_dontunpack(miniflux_spec: AppSpec):
    output = generate(miniflux_spec)
    assert "dontUnpack = true" in output


def test_prebuilt_archive_has_source_root(grafana_spec: AppSpec):
    output = generate(grafana_spec)
    assert "sourceRoot" in output


def test_php_app_has_php_binding(wordpress_spec: AppSpec):
    output = generate(wordpress_spec)
    assert "php = pkgs.php82.withExtensions" in output
    assert "all.mysqli" in output


def test_java_war_has_jdk(jenkins_spec: AppSpec):
    output = generate(jenkins_spec)
    assert "jdk = pkgs.jdk17" in output
    assert "jenkins.war" in output


def test_python_venv_has_pip(isso_spec: AppSpec):
    output = generate(isso_spec)
    assert "pip install isso gunicorn" in output
    assert "__noChroot = true" in output


def test_nixpkgs_wrapper_uses_package(radicale_spec: AppSpec):
    output = generate(radicale_spec)
    assert "radicale = pkgs.radicale" in output
    assert "dontUnpack = true" in output


def test_config_file_ini_generation(gitea_spec: AppSpec):
    output = generate(gitea_spec)
    assert "[server]" in output
    assert "HTTP_PORT" in output
    assert "SECRET_KEY" in output


def test_conditional_env_var(miniflux_spec: AppSpec):
    output = generate(miniflux_spec)
    assert 'if [ -z "$DATABASE_URL" ]' in output
    assert "PGUSER" in output
