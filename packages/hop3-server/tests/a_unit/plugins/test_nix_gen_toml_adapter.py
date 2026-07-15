# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: AGPL-3.0-only

"""Tests for the TOML → AppSpec adapter."""

from __future__ import annotations

import pytest

from hop3.plugins.build.nix.gen import generate
from hop3.plugins.build.nix.gen.templates.base import pinned_nixpkgs_header
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


# A real nixos-25.05 pin (the one etherpad uses). Shapes matter: the adapter now
# validates them, so these fixtures must be well-formed.
_REAL_REV = "ac62194c3917d5f474c1a844b6fd6da2db95077d"
_REAL_SHA = "0v6bd1xk8a2aal83karlvc853x44dg1n4nk08jg3dajqyy0s98np"


def test_nixpkgs_pin_override_threaded_into_spec():
    # An app needing a package the default pin predates (etherpad-lite lives in
    # nixos-25.05, not the default 24.11) overrides the nixpkgs pin per-app.
    nix_config = {
        "template": "nixpkgs-wrapper",
        "nixpkgs-package": "etherpad-lite",
        "nixpkgs-rev": _REAL_REV,
        "nixpkgs-sha256": _REAL_SHA,
    }
    spec = app_spec_from_config(nix_config, {"id": "etherpad"}, "etherpad")
    assert spec.nixpkgs_rev == _REAL_REV
    assert spec.nixpkgs_sha256 == _REAL_SHA


def test_nixpkgs_pin_override_requires_both_keys():
    # A rev needs its fetchTarball hash — one without the other is an error.
    with pytest.raises(ValueError, match="must be set together"):
        app_spec_from_config(
            {"template": "nixpkgs-wrapper", "nixpkgs-rev": _REAL_REV}, {}, "x"
        )


@pytest.mark.parametrize(
    ("rev", "sha", "match"),
    [
        # The real bug: etherpad shipped these literal placeholders, and the
        # generator interpolated them into hop3.nix verbatim. The deploy then died
        # with an opaque "hash '…' has wrong length" — 0.68s of nothing useful.
        ("REPLACE_WITH_A_NIXOS_25_05_COMMIT_SHA", _REAL_SHA, "40-character git"),
        (_REAL_REV, "REPLACE_WITH_NIX_PREFETCH_URL_OUTPUT", "nix sha256 hash"),
        ("deadbeef", _REAL_SHA, "40-character git"),  # too short
        (_REAL_REV, "sha-xyz", "nix sha256 hash"),
    ],
)
def test_malformed_nixpkgs_pin_is_rejected_at_parse_time(rev, sha, match):
    """A pin we already know is broken must abort here, not ship a broken build."""
    with pytest.raises(ValueError, match=match):
        app_spec_from_config(
            {
                "template": "nixpkgs-wrapper",
                "nixpkgs-package": "etherpad-lite",
                "nixpkgs-rev": rev,
                "nixpkgs-sha256": sha,
            },
            {},
            "etherpad",
        )


def test_nixpkgs_pin_override_rejected_on_non_wrapper_template():
    # Fail loud rather than silently ignore a pin the template can't honour.
    with pytest.raises(ValueError, match=r"only.*nixpkgs-wrapper"):
        app_spec_from_config(
            {
                "template": "python-venv",
                "nixpkgs-rev": "deadbeef",
                "nixpkgs-sha256": "sha-xyz",
            },
            {},
            "x",
        )


def test_pinned_nixpkgs_header_override():
    overridden = pinned_nixpkgs_header("REV123", "SHA456")
    assert "REV123" in overridden
    assert "SHA456" in overridden
    # The default (unoverridden) header keeps the global pin.
    assert "REV123" not in pinned_nixpkgs_header()


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

    assert "import (fetchTarball {" in nix_text  # pinned nixpkgs, not <nixpkgs>
    assert "<nixpkgs>" not in nix_text
    assert 'pname = "miniflux"' in nix_text
    assert 'version = "2.1.1"' in nix_text
    assert "''${PORT:-8080}" in nix_text
    assert "$out/hop3/runtime.json" in nix_text
