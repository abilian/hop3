# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for RuntimeManifestBuilder."""

from __future__ import annotations

from pathlib import Path

import pytest

from hop3.core.manifest import RuntimeManifestBuilder
from hop3.project.config import AppConfig


@pytest.fixture
def app_dir(tmp_path: Path) -> Path:
    """Create a minimal app directory structure."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    return tmp_path


@pytest.fixture
def app_config_with_procfile(app_dir: Path) -> AppConfig:
    """Create AppConfig with a Procfile."""
    procfile = app_dir / "src" / "Procfile"
    procfile.write_text("web: gunicorn app:app\nworker: celery -A tasks worker\n")
    return AppConfig.from_dir(app_dir)


@pytest.fixture
def app_config_with_hop3_toml(app_dir: Path) -> AppConfig:
    """Create AppConfig with hop3.toml."""
    hop3_toml = app_dir / "src" / "hop3.toml"
    hop3_toml.write_text("""
[run]
start = "gunicorn app:app --workers 4"
before-run = ["python manage.py migrate"]
static = {"/static" = "static/"}
healthcheck = "/health"
healthcheck-timeout = 60

[env]
DEBUG = "false"
""")
    return AppConfig.from_dir(app_dir)


@pytest.fixture
def app_config_with_both(app_dir: Path) -> AppConfig:
    """Create AppConfig with both Procfile and hop3.toml."""
    procfile = app_dir / "src" / "Procfile"
    procfile.write_text("web: gunicorn app:app\nworker: celery -A tasks worker\n")

    hop3_toml = app_dir / "src" / "hop3.toml"
    hop3_toml.write_text("""
[run]
start = "gunicorn app:app --workers 8"
before-run = ["python manage.py migrate", "python manage.py collectstatic"]
""")
    return AppConfig.from_dir(app_dir)


class TestRuntimeManifestBuilder:
    """Tests for RuntimeManifestBuilder."""

    def test_build_with_procfile_only(self, app_config_with_procfile: AppConfig):
        """Builder should extract workers from Procfile."""
        builder = RuntimeManifestBuilder(app_config_with_procfile)
        runtime = builder.build()

        assert "web" in runtime.workers
        assert runtime.workers["web"] == "gunicorn app:app"
        assert "worker" in runtime.workers
        assert runtime.workers["worker"] == "celery -A tasks worker"

    def test_build_with_hop3_toml_only(self, app_config_with_hop3_toml: AppConfig):
        """Builder should extract config from hop3.toml."""
        builder = RuntimeManifestBuilder(app_config_with_hop3_toml)
        runtime = builder.build()

        # Workers from [run] start
        assert "web" in runtime.workers
        assert "--workers 4" in runtime.workers["web"]

        # Before-run commands
        assert len(runtime.before_run) == 1
        assert "migrate" in runtime.before_run[0]

        # Static paths
        assert runtime.static_paths == {"/static": "static/"}

        # Healthcheck
        assert runtime.healthcheck_path == "/health"
        assert runtime.healthcheck_timeout == 60

    def test_build_with_both_prefers_hop3_toml(self, app_config_with_both: AppConfig):
        """Builder should prefer hop3.toml over Procfile for web worker."""
        builder = RuntimeManifestBuilder(app_config_with_both)
        runtime = builder.build()

        # hop3.toml web command takes precedence
        assert "--workers 8" in runtime.workers["web"]

        # Procfile worker is still included
        assert "worker" in runtime.workers
        assert "celery" in runtime.workers["worker"]

    def test_build_preserves_toolchain_env(self, app_config_with_hop3_toml: AppConfig):
        """Builder should preserve env vars from toolchain."""
        builder = RuntimeManifestBuilder(app_config_with_hop3_toml)
        runtime = builder.build(
            env_vars={"PYTHONPATH": "/app/src", "VIRTUAL_ENV": "/app/venv"},
            path_prepend=["/app/venv/bin"],
            working_dir="/app/src",
        )

        # Toolchain env vars preserved
        assert runtime.env_vars["PYTHONPATH"] == "/app/src"
        assert runtime.env_vars["VIRTUAL_ENV"] == "/app/venv"

        # hop3.toml env vars added (toolchain takes precedence)
        assert "DEBUG" in runtime.env_vars

        # Path prepend preserved
        assert "/app/venv/bin" in runtime.path_prepend

        # Working dir preserved
        assert runtime.working_dir == "/app/src"

    def test_build_empty_config(self, app_dir: Path):
        """Builder should handle empty config gracefully."""
        config = AppConfig.from_dir(app_dir)
        builder = RuntimeManifestBuilder(config)
        runtime = builder.build()

        assert runtime.workers == {}
        assert runtime.before_run == []
        assert runtime.static_paths == {}
        assert runtime.healthcheck_path == ""

    def test_build_excludes_lifecycle_hooks_from_workers(self, app_dir: Path):
        """Builder should not include prebuild/postbuild/prerun in workers."""
        procfile = app_dir / "src" / "Procfile"
        procfile.write_text(
            "web: gunicorn app:app\n"
            "prebuild: npm install\n"
            "postbuild: npm run build\n"
            "prerun: python setup.py\n"
        )
        config = AppConfig.from_dir(app_dir)
        builder = RuntimeManifestBuilder(config)
        runtime = builder.build()

        # Only web should be in workers
        assert "web" in runtime.workers
        assert "prebuild" not in runtime.workers
        assert "postbuild" not in runtime.workers
        assert "prerun" not in runtime.workers

    def test_build_before_run_from_procfile_prerun(self, app_dir: Path):
        """Builder should extract before_run from Procfile prerun if no hop3.toml."""
        procfile = app_dir / "src" / "Procfile"
        procfile.write_text("web: gunicorn app:app\nprerun: python setup.py\n")
        config = AppConfig.from_dir(app_dir)
        builder = RuntimeManifestBuilder(config)
        runtime = builder.build()

        assert len(runtime.before_run) == 1
        assert runtime.before_run[0] == "python setup.py"

    def test_build_hop3_toml_before_run_takes_precedence(self, app_dir: Path):
        """Builder should prefer hop3.toml before-run over Procfile prerun."""
        procfile = app_dir / "src" / "Procfile"
        procfile.write_text("web: gunicorn app:app\nprerun: echo 'from procfile'\n")

        hop3_toml = app_dir / "src" / "hop3.toml"
        hop3_toml.write_text("""
[run]
before-run = ["echo 'from hop3.toml'"]
""")
        config = AppConfig.from_dir(app_dir)
        builder = RuntimeManifestBuilder(config)
        runtime = builder.build()

        # hop3.toml takes precedence
        assert len(runtime.before_run) == 1
        assert "hop3.toml" in runtime.before_run[0]


class TestRuntimeManifestBuilderIntegration:
    """Integration tests for RuntimeManifestBuilder with real configs."""

    def test_django_style_config(self, app_dir: Path):
        """Test typical Django app configuration."""
        hop3_toml = app_dir / "src" / "hop3.toml"
        hop3_toml.write_text("""
[metadata]
id = "django-app"

[run]
start = "gunicorn config.wsgi:application --bind 0.0.0.0:$PORT"
before-run = [
    "python manage.py migrate --noinput",
    "python manage.py collectstatic --noinput"
]
static = {"/static" = "staticfiles/"}
healthcheck = "/health/"

[env]
DJANGO_SETTINGS_MODULE = "config.settings.production"

[[addons]]
type = "postgres"
""")
        config = AppConfig.from_dir(app_dir)
        builder = RuntimeManifestBuilder(config)
        runtime = builder.build(
            env_vars={"PYTHONPATH": "/app/src"},
            path_prepend=["/app/venv/bin"],
            working_dir="/app/src",
        )

        assert "gunicorn" in runtime.workers["web"]
        assert len(runtime.before_run) == 2
        assert "migrate" in runtime.before_run[0]
        assert "collectstatic" in runtime.before_run[1]
        assert runtime.static_paths == {"/static": "staticfiles/"}
        assert runtime.healthcheck_path == "/health/"
        assert runtime.env_vars["PYTHONPATH"] == "/app/src"

    def test_node_style_config(self, app_dir: Path):
        """Test typical Node.js app configuration."""
        hop3_toml = app_dir / "src" / "hop3.toml"
        hop3_toml.write_text("""
[metadata]
id = "node-app"

[build]
build = "npm run build"

[run]
start = "node dist/server.js"
static = {"/assets" = "dist/assets/"}
healthcheck = "/api/health"
healthcheck-timeout = 10

[[addons]]
type = "redis"
""")
        config = AppConfig.from_dir(app_dir)
        builder = RuntimeManifestBuilder(config)
        runtime = builder.build(
            env_vars={"NODE_ENV": "production"},
            path_prepend=["/app/node_modules/.bin"],
        )

        assert "node" in runtime.workers["web"]
        assert runtime.static_paths == {"/assets": "dist/assets/"}
        assert runtime.healthcheck_path == "/api/health"
        assert runtime.healthcheck_timeout == 10
