# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for dashboard web views."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient

from hop3.orm.security import AuditBase
from hop3.server.asgi import create_app


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    """Set up test environment."""
    # ruff: noqa: PLC0415
    import importlib

    from hop3 import config

    monkeypatch.setenv("HOP3_SECRET_KEY", "test-secret-for-dashboard-testing")
    monkeypatch.setenv("HOP3_SESSION_SECRET", "test-session-secret-for-dashboard")
    monkeypatch.setenv("HOP3_ENABLE_AUTH", "true")
    # Use UNSAFE mode to bypass authentication for testing
    monkeypatch.setenv("HOP3_UNSAFE", "true")

    # Need to reload config after setting env vars
    importlib.reload(config)

    yield

    # CRITICAL: Reload config again after test to pick up cleaned environment
    # monkeypatch automatically restores env vars, but config module is cached
    importlib.reload(config)


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    AuditBase.metadata.create_all(engine)

    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    yield session

    session.close()


# Note: Database fixtures removed because views run in thread pool
# and SQLite connections can't be shared across threads.
# These tests now focus on testing that pages render correctly
# without requiring specific database state.


@pytest.fixture
def client():
    """Create a test client."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def authenticated_client(client: TestClient):
    """Create an authenticated test client.

    Note: Using HOP3_UNSAFE=true from setup_test_env to bypass authentication.
    The views will use the default database (which may be empty), but that's OK
    for testing that the pages render correctly.
    """
    return client


# Root Endpoint Tests


def test_root_redirect(client: TestClient):
    """Test that root redirects (location depends on auth setup)."""
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 302
    # In test mode, may redirect to either dashboard or login depending on middleware setup
    assert response.headers["location"] in {"/dashboard", "/auth/login"}


# Dashboard Index Tests


def test_dashboard_index_authenticated(authenticated_client: TestClient):
    """Test dashboard index page with authenticated user."""
    response = authenticated_client.get("/dashboard")
    assert response.status_code == 200
    assert b"Applications" in response.content
    # Dashboard page should render (may show empty state if no apps)


def test_dashboard_index_empty(authenticated_client: TestClient):
    """Test dashboard index with no applications."""
    response = authenticated_client.get("/dashboard")
    assert response.status_code == 200
    assert b"No applications" in response.content or b"Deploy New App" in response.content


# Services and Backups Placeholder Tests


def test_dashboard_services(authenticated_client: TestClient):
    """Test services placeholder page."""
    response = authenticated_client.get("/dashboard/services")
    assert response.status_code == 200
    assert b"Services" in response.content or b"Coming soon" in response.content


def test_dashboard_backups(authenticated_client: TestClient):
    """Test backups placeholder page."""
    response = authenticated_client.get("/dashboard/backups")
    assert response.status_code == 200
    assert b"Backups" in response.content or b"Coming soon" in response.content


# App Detail Tests


def test_app_detail_not_found(authenticated_client: TestClient):
    """Test app detail with non-existent app redirects to dashboard."""
    response = authenticated_client.get(
        "/dashboard/apps/nonexistent", follow_redirects=False
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/dashboard"


# App Status Endpoint Tests (HTMX Polling)


def test_app_status_not_found(authenticated_client: TestClient):
    """Test app status with non-existent app."""
    response = authenticated_client.get("/dashboard/apps/nonexistent/status")
    assert response.status_code == 200
    # Should return empty or error fragment (not 404)


# Mobile Responsive Tests


def test_dashboard_mobile_card_view(authenticated_client: TestClient):
    """Test that dashboard includes mobile-responsive design."""
    response = authenticated_client.get("/dashboard")
    assert response.status_code == 200
    # Check for responsive classes (either in cards or empty state message)
    assert b"sm:" in response.content  # Should have mobile-responsive classes
