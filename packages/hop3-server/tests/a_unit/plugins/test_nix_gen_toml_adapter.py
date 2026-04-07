# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: AGPL-3.0-only

"""Tests for the TOML → AppSpec adapter."""

from __future__ import annotations

import pytest

from hop3.plugins.build.nix.gen.toml_adapter import app_spec_from_config


def test_minimal_spec():
    nix_config = {
        "template": "prebuilt-binary",
        "url": "https://example.com/bin",
        "sha256": "abc123",
        "executable": True,
        "binary-name": "myapp",
    }
    metadata = {"id": "myapp", "version": "1.0", "description": "My app"}

    spec = app_spec_from_config(nix_config, metadata, "myapp")

    assert spec.pname == "myapp"
    assert spec.version == "1.0"
    assert spec.template == "prebuilt-binary"
    assert spec.binary_name == "myapp"
    assert spec.source.url == "https://example.com/bin"
    assert spec.source.executable is True


def test_missing_template_raises():
    with pytest.raises(ValueError, match="template is required"):
        app_spec_from_config({}, {}, "test")


def test_metadata_fallbacks():
    nix_config = {"template": "prebuilt-binary", "binary-name": "x"}
    spec = app_spec_from_config(nix_config, {}, "fallback-name")
    assert spec.pname == "fallback-name"
    assert spec.version == ""


def test_php_fields():
    nix_config = {
        "template": "php-app",
        "url": "https://example.com/wp.tar.gz",
        "sha256": "x",
        "archive": "tar-gz",
        "php-version": "php83",
        "php-extensions": ["mysqli", "gd"],
        "needs-composer": True,
        "composer-extra-flags": ["--ignore-platform-reqs"],
        "serve-mode": "artisan",
        "web-root": "htdocs",
        "post-install-dirs": ["storage", "cache"],
        "extra-paths": ["${php}/bin"],
    }

    spec = app_spec_from_config(nix_config, {"id": "wp"}, "wp")

    assert spec.php_version == "php83"
    assert spec.php_extensions == ["mysqli", "gd"]
    assert spec.needs_composer is True
    assert spec.composer_extra_flags == ["--ignore-platform-reqs"]
    assert spec.serve_mode == "artisan"
    assert spec.web_root == "htdocs"
    assert spec.post_install_dirs == ["storage", "cache"]
    assert spec.extra_paths == ["${php}/bin"]


def test_config_files_parsing():
    nix_config = {
        "template": "prebuilt-binary",
        "binary-name": "x",
        "config-files": [
            {
                "path": "app.ini",
                "format": "ini",
                "sections": {"server": {"port": "${PORT}"}},
            },
            {
                "path": "config.yml",
                "format": "raw",
                "raw-content": "port: ${PORT}\n",
                "create-if-missing": True,
            },
        ],
    }

    spec = app_spec_from_config(nix_config, {"id": "t"}, "t")

    assert len(spec.config_files) == 2
    assert spec.config_files[0].path == "app.ini"
    assert spec.config_files[0].format == "ini"
    assert spec.config_files[0].sections == {"server": {"port": "${PORT}"}}
    assert spec.config_files[1].path == "config.yml"
    assert spec.config_files[1].raw_content == "port: ${PORT}\n"
    assert spec.config_files[1].create_if_missing is True


def test_file_mappings_parsing():
    nix_config = {
        "template": "prebuilt-archive",
        "exec-target": "mybin",
        "file-mappings": [
            {"source": "bin/mybin", "destination": "bin/", "executable": True},
            {"source": "lib/*", "destination": "share/myapp/"},
        ],
    }

    spec = app_spec_from_config(nix_config, {"id": "t"}, "t")

    assert len(spec.file_mappings) == 2
    assert spec.file_mappings[0].source == "bin/mybin"
    assert spec.file_mappings[0].executable is True
    assert spec.file_mappings[1].source == "lib/*"
    assert spec.file_mappings[1].recursive is True


def test_conditional_env_parsing():
    nix_config = {
        "template": "prebuilt-binary",
        "binary-name": "x",
        "conditional-env": [
            {
                "name": "DATABASE_URL",
                "condition-var": "DATABASE_URL",
                "value": "postgres://${PGUSER}@localhost",
            },
        ],
    }

    spec = app_spec_from_config(nix_config, {"id": "t"}, "t")

    assert len(spec.conditional_env_exports) == 1
    cev = spec.conditional_env_exports[0]
    assert cev.name == "DATABASE_URL"
    assert cev.condition_var == "DATABASE_URL"
    assert "${PGUSER}" in cev.value


def test_wrapper_fields():
    nix_config = {
        "template": "prebuilt-binary",
        "binary-name": "x",
        "exec-target": "mybin",
        "exec-args": ["serve", "--port", "8080"],
        "local-vars": {"PORT": "${PORT:-8080}"},
        "env-exports": {"DEBUG": "false"},
        "pre-exec": ["mkdir -p data"],
        "runtime-env": {"APP_ENV": "production"},
    }

    spec = app_spec_from_config(nix_config, {"id": "t"}, "t")

    assert spec.exec_target == "mybin"
    assert spec.exec_args == ["serve", "--port", "8080"]
    assert spec.local_vars == {"PORT": "${PORT:-8080}"}
    assert spec.env_exports == {"DEBUG": "false"}
    assert spec.pre_exec_commands == ["mkdir -p data"]
    assert spec.runtime_env == {"APP_ENV": "production"}


def test_end_to_end_generate_from_toml():
    """Full round trip: TOML dict → AppSpec → generate → valid Nix string."""
    from hop3.plugins.build.nix.gen import generate

    nix_config = {
        "template": "prebuilt-binary",
        "url": "https://example.com/miniflux-linux-amd64",
        "sha256": "abc123",
        "executable": True,
        "binary-name": "miniflux",
        "env-exports": {"LISTEN_ADDR": "0.0.0.0:${PORT:-8080}"},
        "runtime-env": {"RUN_MIGRATIONS": "1"},
    }
    metadata = {"id": "miniflux", "version": "2.1.1", "description": "RSS reader"}

    spec = app_spec_from_config(nix_config, metadata, "miniflux")
    nix_text = generate(spec)

    assert "{ pkgs ? import <nixpkgs> {} }" in nix_text
    assert 'pname = "miniflux"' in nix_text
    assert 'version = "2.1.1"' in nix_text
    assert "''${PORT:-8080}" in nix_text
    assert "$out/hop3/runtime.json" in nix_text
