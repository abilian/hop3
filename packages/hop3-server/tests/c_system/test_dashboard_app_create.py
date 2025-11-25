# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for dashboard app creation UI."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest
from advanced_alchemy.base import BigIntAuditBase
from litestar.testing import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from hop3.config import HopConfig
from hop3.orm import App, reset_session_factory_cache
from hop3.server.asgi import create_app
from hop3.server.lib.database import get_session

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def setup_secret_key():
    """Set up a test secret key."""
    os.environ["HOP3_SECRET_KEY"] = "test-secret-key-for-integration-testing"
    yield
    os.environ.pop("HOP3_SECRET_KEY", None)


@pytest.fixture
def db_session(tmp_path: Path):
    """Create an in-memory SQLite database for testing."""
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    BigIntAuditBase.metadata.create_all(engine)

    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    yield session

    session.close()


@pytest.fixture(autouse=False)
def test_client(tmp_path: Path, monkeypatch):
    """Create an authenticated test client with in-memory database.

    This is a system test fixture that uses REAL implementations:
    - Real App.create() method (creates actual directories in tmp_path)
    - Real database operations (in-memory SQLite for speed)
    - Real template rendering
    - Real route handlers

    Only authentication is mocked for test convenience.
    """
    # CRITICAL: Set environment variable BEFORE any imports
    # This ensures get_session_factory() uses in-memory database
    # Use shared in-memory database (file::memory:?cache=shared) so all
    # connections share the same database
    monkeypatch.setenv(
        "HOP3_DATABASE_URI", "sqlite:///file::memory:?cache=shared&uri=true"
    )

    # Reset any existing config singleton first
    HopConfig.reset_instance()

    # Reset session factory cache to ensure fresh database
    reset_session_factory_cache()

    # Create test config with custom HOP3_ROOT
    test_config = HopConfig(hop3_root=tmp_path)
    HopConfig.set_instance(test_config)

    # Create required directory structure
    (tmp_path / "apps").mkdir(exist_ok=True)
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "logs").mkdir(exist_ok=True)

    # Enable unsafe mode to bypass authentication
    import hop3.config

    monkeypatch.setattr(hop3.config, "HOP3_UNSAFE", True)

    # Create Litestar app - will use in-memory database via environment variable
    # Uses real App.create() and all real business logic
    app = create_app()
    client = TestClient(app)

    yield client

    # Cleanup: reset config singleton and session factory cache for next test
    HopConfig.reset_instance()
    reset_session_factory_cache()


def test_app_create_form_loads(test_client):
    """Test that the app creation form loads successfully."""
    response = test_client.get("/dashboard/apps/new")

    assert response.status_code == 200

    # Debug: print response content if assertion fails
    if b"Create New Application" not in response.content:
        print("\n=== RESPONSE CONTENT ===")
        print(response.content.decode()[:500])
        print("=== END RESPONSE ===\n")

    assert b"Create New Application" in response.content
    assert b"Application Name" in response.content
    assert b"Builder" in response.content
    assert b"Environment Variables" in response.content


def test_app_create_validation_missing_name(test_client):
    """Test validation when app name is missing."""
    response = test_client.post(
        "/dashboard/apps/new",
        data={
            "app_name": "",
            "builder": "python",
            "env_vars": "",
        },
    )

    assert response.status_code == 200
    assert b"App name is required" in response.content


def test_app_create_validation_short_name(test_client):
    """Test validation when app name is too short."""
    response = test_client.post(
        "/dashboard/apps/new",
        data={
            "app_name": "ab",
            "builder": "python",
            "env_vars": "",
        },
    )

    assert response.status_code == 200
    assert b"at least 3 characters" in response.content


def test_app_create_validation_long_name(test_client):
    """Test validation when app name is too long."""
    long_name = "a" * 64
    response = test_client.post(
        "/dashboard/apps/new",
        data={
            "app_name": long_name,
            "builder": "python",
            "env_vars": "",
        },
    )

    assert response.status_code == 200
    assert b"less than 64 characters" in response.content


def test_app_create_validation_invalid_chars(test_client):
    """Test validation when app name contains invalid characters."""
    response = test_client.post(
        "/dashboard/apps/new",
        data={
            "app_name": "my app with spaces",
            "builder": "python",
            "env_vars": "",
        },
    )

    assert response.status_code == 200
    assert b"letters, numbers, hyphens, and underscores" in response.content


def test_app_create_success(test_client, tmp_path: Path):
    """Test successful app creation."""
    response = test_client.post(
        "/dashboard/apps/new",
        data={
            "app_name": "test-app",
            "builder": "python",
            "env_vars": "DEBUG=true\nAPI_KEY=secret123",
        },
        follow_redirects=False,
    )

    # Should redirect to app detail page
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard/apps/test-app?created=true"

    # Verify app was created in database (use the same database as the app)
    with get_session() as session:
        app = session.query(App).filter_by(name="test-app").first()
        assert app is not None
        assert app.name == "test-app"

        # Verify environment variables
        env_vars = {var.name: var.value for var in app.env_vars}
        assert env_vars["DEBUG"] == "true"
        assert env_vars["API_KEY"] == "secret123"
        assert env_vars["BUILDER"] == "python"

    # SYSTEM TEST: Verify file system state (real App.create() was called)
    app_path = tmp_path / "apps" / "test-app"
    assert app_path.exists(), "App directory should exist"
    assert app_path.is_dir(), "App path should be a directory"

    # Verify all subdirectories were created by App.create()
    # Note: These match the actual paths created by App.create() in app.py:68-69
    assert (app_path / "git").exists(), "git directory should exist (repo_path)"
    assert (app_path / "src").exists(), "src directory should exist (src_path)"
    assert (app_path / "data").exists(), "data directory should exist (data_path)"
    assert (app_path / "log").exists(), "log directory should exist (log_path)"


def test_app_create_auto_detect_builder(test_client, tmp_path: Path):
    """Test app creation with auto-detect builder."""
    response = test_client.post(
        "/dashboard/apps/new",
        data={
            "app_name": "auto-app",
            "builder": "auto",
            "env_vars": "",
        },
        follow_redirects=False,
    )

    # Should redirect to app detail page
    assert response.status_code == 303

    # Verify app was created without BUILDER env var
    with get_session() as session:
        app = session.query(App).filter_by(name="auto-app").first()
        assert app is not None

        # BUILDER env var should not be set for auto-detect
        env_vars = {var.name: var.value for var in app.env_vars}
        assert "BUILDER" not in env_vars


def test_app_create_duplicate_name(test_client, tmp_path: Path):
    """Test that creating an app with duplicate name fails."""
    # Create first app
    test_client.post(
        "/dashboard/apps/new",
        data={
            "app_name": "duplicate-app",
            "builder": "python",
            "env_vars": "",
        },
    )

    # Try to create second app with same name
    response = test_client.post(
        "/dashboard/apps/new",
        data={
            "app_name": "duplicate-app",
            "builder": "nodejs",
            "env_vars": "",
        },
    )

    assert response.status_code == 200
    assert b"already exists" in response.content


def test_app_create_env_vars_parsing(test_client, tmp_path: Path):
    """Test environment variable parsing with comments and blank lines."""
    response = test_client.post(
        "/dashboard/apps/new",
        data={
            "app_name": "env-test",
            "builder": "nodejs",
            "env_vars": """
# Database configuration
DATABASE_URL=postgres://localhost/db

# API settings
API_KEY=secret
API_HOST=example.com

# Empty line above should be ignored
            """,
        },
        follow_redirects=False,
    )

    assert response.status_code == 303

    # Verify environment variables
    with get_session() as session:
        app = session.query(App).filter_by(name="env-test").first()
        env_vars = {var.name: var.value for var in app.env_vars}

        assert env_vars["DATABASE_URL"] == "postgres://localhost/db"
        assert env_vars["API_KEY"] == "secret"
        assert env_vars["API_HOST"] == "example.com"
        assert env_vars["BUILDER"] == "nodejs"


def test_app_create_valid_name_formats(test_client, tmp_path: Path):
    """Test that various valid app name formats work."""
    valid_names = [
        "my-app",
        "my_app",
        "app123",
        "my-app-123",
        "my_app_123",
        "app-with-many-dashes",
        "app_with_many_underscores",
    ]

    for app_name in valid_names:
        response = test_client.post(
            "/dashboard/apps/new",
            data={
                "app_name": app_name,
                "builder": "static",
                "env_vars": "",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303, (
            f"Failed to create app with name: {app_name}"
        )
