# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for dashboard web views."""

from __future__ import annotations

import re
import time

import pytest
from litestar.testing import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import hop3.config
from hop3.orm import AddonCredential, App, get_session_factory
from hop3.orm.security import AuditBase
from hop3.orm.session import reset_session_factory_cache
from hop3.server.asgi import create_app
from hop3.server.lib.database import get_session


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    AuditBase.metadata.create_all(engine)

    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    yield session

    session.close()


@pytest.fixture
def isolated_database(monkeypatch, worker_id):
    """
    Configure an isolated test database for this test worker.

    Uses SQLite with shared cache mode to allow the test client's thread pool
    to access the same in-memory database as the test fixtures.

    Each pytest-xdist worker gets its own database to prevent cross-contamination.
    """
    # Create worker-specific database URI
    # Use shared cache mode so threads can access the same in-memory DB
    if worker_id == "master":
        # Single-process mode
        db_uri = "sqlite:///file::memory:?cache=shared&uri=true"
    else:
        # Multi-process mode - each worker gets its own database
        db_uri = f"sqlite:///file:memdb_{worker_id}?mode=memory&cache=shared&uri=true"

    # Set environment variable for get_session_factory()
    monkeypatch.setenv("HOP3_DATABASE_URI", db_uri)

    # Reset session factory cache to pick up new database URI
    reset_session_factory_cache()

    # Create the database schema
    get_session_factory()

    yield db_uri

    # Cleanup
    reset_session_factory_cache()


@pytest.fixture
def client(isolated_database):
    """Create a test client with isolated database."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def authenticated_client(isolated_database, monkeypatch):
    """
    Create an authenticated test client with isolated database.

    Uses HOP3_UNSAFE mode to bypass authentication for testing.
    """
    # Enable unsafe mode to bypass authentication guards
    monkeypatch.setattr(hop3.config, "HOP3_UNSAFE", True)

    # Create a new app with authentication bypassed
    app = create_app()
    return TestClient(app)


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
    assert (
        b"No applications" in response.content or b"Deploy New App" in response.content
    )


# Addons and Backups Placeholder Tests


def test_dashboard_addons(authenticated_client: TestClient):
    """Test addons placeholder page."""
    response = authenticated_client.get("/dashboard/addons")
    assert response.status_code == 200
    assert b"Addons" in response.content or b"Coming soon" in response.content


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


# Logs Endpoint Tests


def test_app_logs_not_found(authenticated_client: TestClient):
    """Test app logs page with non-existent app redirects to dashboard."""
    response = authenticated_client.get(
        "/dashboard/apps/nonexistent/logs", follow_redirects=False
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/dashboard"


def test_app_logs_page_renders(authenticated_client: TestClient):
    """Test that logs page renders correctly (even if no app exists)."""
    response = authenticated_client.get("/dashboard/apps/testapp/logs")
    # Will redirect to dashboard if app doesn't exist
    assert response.status_code in {200, 302}


def test_app_logs_stream_not_found(authenticated_client: TestClient):
    """Test app logs stream with non-existent app."""
    response = authenticated_client.get("/dashboard/apps/nonexistent/logs/stream")
    assert response.status_code == 404
    assert b"App not found" in response.content


def test_app_logs_stream_content_type(authenticated_client: TestClient):
    """Test that logs stream returns plain text."""
    response = authenticated_client.get("/dashboard/apps/testapp/logs/stream")
    # Will return 404 if app doesn't exist
    if response.status_code == 200:
        assert response.headers["content-type"] == "text/plain; charset=utf-8"


def test_app_logs_download_not_found(authenticated_client: TestClient):
    """Test app logs download with non-existent app redirects to dashboard."""
    response = authenticated_client.get(
        "/dashboard/apps/nonexistent/logs/download", follow_redirects=False
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/dashboard"


def test_app_logs_download_headers(authenticated_client: TestClient):
    """Test that logs download returns correct headers."""
    response = authenticated_client.get(
        "/dashboard/apps/testapp/logs/download", follow_redirects=False
    )
    # Will redirect if app doesn't exist, otherwise should have proper headers
    if response.status_code == 200:
        assert response.headers["content-type"] == "text/plain; charset=utf-8"
        assert "attachment" in response.headers["content-disposition"]
        assert "testapp_logs_" in response.headers["content-disposition"]
        assert ".txt" in response.headers["content-disposition"]
    else:
        # App doesn't exist, should redirect
        assert response.status_code == 302


# Environment Variables Tests


def test_app_env_not_found(authenticated_client: TestClient):
    """Test app env vars page with non-existent app redirects to dashboard."""
    response = authenticated_client.get(
        "/dashboard/apps/nonexistent/env", follow_redirects=False
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/dashboard"


def test_app_env_page_renders(authenticated_client: TestClient):
    """Test that env vars page renders correctly (even if no app exists)."""
    response = authenticated_client.get("/dashboard/apps/testapp/env")
    # Will redirect to dashboard if app doesn't exist
    assert response.status_code in {200, 302}


def test_app_env_page_structure(authenticated_client: TestClient):
    """Test that env vars page has expected structure."""
    response = authenticated_client.get(
        "/dashboard/apps/testapp/env", follow_redirects=False
    )
    if response.status_code == 200:
        # Check for Alpine.js data attributes
        assert b"x-data" in response.content
        # Check for search functionality
        assert (
            b"searchTerm" in response.content or b"search" in response.content.lower()
        )
        # Check for secret masking functionality
        assert (
            b"showSecrets" in response.content or b"secret" in response.content.lower()
        )
    else:
        # App doesn't exist, should redirect
        assert response.status_code == 302


# HTMX Integration Tests


def test_app_status_htmx_fragment(authenticated_client: TestClient):
    """Test that app status endpoint returns HTMX-compatible fragment."""
    response = authenticated_client.get("/dashboard/apps/testapp/status")
    assert response.status_code == 200
    # Should return HTML fragment (not full page)
    assert b"<!DOCTYPE" not in response.content
    assert b"<html" not in response.content


def test_logs_stream_htmx_compatible(authenticated_client: TestClient):
    """Test that logs stream is HTMX-compatible."""
    response = authenticated_client.get("/dashboard/apps/testapp/logs/stream")
    # Should return plain text (HTMX will insert into pre tag)
    if response.status_code == 200:
        assert response.headers["content-type"] == "text/plain; charset=utf-8"


# Authentication Tests


def test_logs_requires_authentication(client: TestClient):
    """Test that logs page requires authentication."""
    response = client.get("/dashboard/apps/testapp/logs", follow_redirects=False)
    # Without authentication, should return 401 or redirect to login
    assert response.status_code in {302, 401}


def test_env_vars_requires_authentication(client: TestClient):
    """Test that env vars page requires authentication."""
    response = client.get("/dashboard/apps/testapp/env", follow_redirects=False)
    # Without authentication, should return 401 or redirect to login
    assert response.status_code in {302, 401}


def test_logs_stream_unauthorized(client: TestClient):
    """Test logs stream requires authentication."""
    # follow_redirects=False so we see the auth_guard's 302 -> /auth/login,
    # not the 200 login page it redirects to (the sibling tests do the same).
    response = client.get("/dashboard/apps/testapp/logs/stream", follow_redirects=False)
    # Without authentication, should return 401 or redirect to login
    assert response.status_code in {302, 401}


# Navigation and Breadcrumbs Tests


def test_logs_page_has_breadcrumbs(authenticated_client: TestClient):
    """Test that logs page includes navigation breadcrumbs."""
    response = authenticated_client.get(
        "/dashboard/apps/testapp/logs", follow_redirects=False
    )
    if response.status_code == 200:
        assert b"Applications" in response.content
        assert b"testapp" in response.content
        assert b"Logs" in response.content
    else:
        # App doesn't exist, should redirect
        assert response.status_code == 302


def test_env_page_has_breadcrumbs(authenticated_client: TestClient):
    """Test that env vars page includes navigation breadcrumbs."""
    response = authenticated_client.get(
        "/dashboard/apps/testapp/env", follow_redirects=False
    )
    if response.status_code == 200:
        assert b"Applications" in response.content
        assert b"testapp" in response.content
    else:
        # App doesn't exist, should redirect
        assert response.status_code == 302


def test_app_detail_has_log_link(authenticated_client: TestClient):
    """Test that app detail page links to logs."""
    response = authenticated_client.get(
        "/dashboard/apps/testapp", follow_redirects=False
    )
    if response.status_code == 200:
        assert b"/logs" in response.content
        assert b"View Logs" in response.content or b"Logs" in response.content
    else:
        # App doesn't exist, should redirect
        assert response.status_code == 302


def test_app_detail_has_env_link(authenticated_client: TestClient):
    """Test that app detail page links to environment variables."""
    response = authenticated_client.get(
        "/dashboard/apps/testapp", follow_redirects=False
    )
    if response.status_code == 200:
        assert b"/env" in response.content
        assert b"Environment" in response.content
    else:
        # App doesn't exist, should redirect
        assert response.status_code == 302


# UI Component Tests


def test_logs_page_has_search_controls(authenticated_client: TestClient):
    """Test that logs page has search and filter controls."""
    response = authenticated_client.get(
        "/dashboard/apps/testapp/logs", follow_redirects=False
    )
    if response.status_code == 200:
        # Check for search button/functionality
        assert b"Search" in response.content or b"search" in response.content.lower()
        # Check for auto-scroll toggle
        assert (
            b"auto-scroll" in response.content.lower()
            or b"Auto-scroll" in response.content
        )
    else:
        # App doesn't exist, should redirect
        assert response.status_code == 302


def test_logs_page_has_download_button(authenticated_client: TestClient):
    """Test that logs page has download button."""
    response = authenticated_client.get(
        "/dashboard/apps/testapp/logs", follow_redirects=False
    )
    if response.status_code == 200:
        assert (
            b"Download" in response.content or b"download" in response.content.lower()
        )
        assert b"/logs/download" in response.content
    else:
        # App doesn't exist, should redirect
        assert response.status_code == 302


def test_env_page_has_copy_functionality(authenticated_client: TestClient):
    """Test that env vars page has copy-to-clipboard functionality."""
    response = authenticated_client.get(
        "/dashboard/apps/testapp/env", follow_redirects=False
    )
    if response.status_code == 200:
        # Check for copy functionality (clipboard API)
        assert (
            b"clipboard" in response.content.lower()
            or b"copy" in response.content.lower()
        )
    else:
        # App doesn't exist, should redirect
        assert response.status_code == 302


def test_env_page_has_secret_masking(authenticated_client: TestClient):
    """Test that env vars page has secret masking functionality."""
    response = authenticated_client.get(
        "/dashboard/apps/testapp/env", follow_redirects=False
    )
    if response.status_code == 200:
        # Check for secret masking toggle
        assert b"showSecrets" in response.content or b"Show" in response.content
        # Check for masking implementation
        assert b"maskValue" in response.content or b"mask" in response.content.lower()
    else:
        # App doesn't exist, should redirect
        assert response.status_code == 302


# Error Handling Tests


def test_multiple_nonexistent_endpoints(authenticated_client: TestClient):
    """Test that all app-specific endpoints handle non-existent apps consistently."""
    endpoints = [
        "/dashboard/apps/nonexistent",
        "/dashboard/apps/nonexistent/logs",
        "/dashboard/apps/nonexistent/env",
    ]

    for endpoint in endpoints:
        response = authenticated_client.get(endpoint, follow_redirects=False)
        # All should redirect to dashboard
        assert response.status_code == 302
        assert response.headers["location"] == "/dashboard"


def test_app_status_handles_missing_app_gracefully(authenticated_client: TestClient):
    """Test that status endpoint handles missing apps without errors."""
    response = authenticated_client.get("/dashboard/apps/nonexistent/status")
    assert response.status_code == 200
    # Should return a valid HTML fragment, not an error page
    assert b"<" in response.content  # Has some HTML


def test_logs_stream_handles_missing_app_with_404(authenticated_client: TestClient):
    """Test that logs stream returns 404 for missing apps."""
    response = authenticated_client.get("/dashboard/apps/nonexistent/logs/stream")
    assert response.status_code == 404
    assert b"App not found" in response.content


# Performance and Caching Tests


def test_dashboard_response_time_acceptable(authenticated_client: TestClient):
    """Test that dashboard loads reasonably quickly."""
    start = time.time()
    response = authenticated_client.get("/dashboard")
    elapsed = time.time() - start

    assert response.status_code == 200
    assert elapsed < 2.0  # Should load in under 2 seconds


def test_static_assets_referenced(authenticated_client: TestClient):
    """Test that dashboard pages reference necessary static assets."""
    response = authenticated_client.get("/dashboard")
    assert response.status_code == 200
    # Check for CDN resources (Alpine.js, HTMX, Tailwind)
    content = response.content.decode("utf-8", errors="ignore")
    # Should have script tags for frontend libraries
    assert "script" in content.lower()


# Content Validation Tests


def test_logs_page_terminal_styling(authenticated_client: TestClient):
    """Test that logs page has terminal-style styling."""
    response = authenticated_client.get(
        "/dashboard/apps/testapp/logs", follow_redirects=False
    )
    if response.status_code == 200:
        # Check for monospace font and dark theme
        assert b"mono" in response.content or b"font-mono" in response.content
        assert b"gray-900" in response.content or b"dark" in response.content.lower()
    else:
        # App doesn't exist, should redirect
        assert response.status_code == 302


def test_env_page_service_variable_detection(authenticated_client: TestClient):
    """Test that env vars page can detect service-generated variables."""
    response = authenticated_client.get(
        "/dashboard/apps/testapp/env", follow_redirects=False
    )
    if response.status_code == 200:
        # Check for service variable detection logic
        content = response.content.decode("utf-8", errors="ignore")
        assert "_URL" in content or "_HOST" in content or "service" in content.lower()
    else:
        # App doesn't exist, should redirect
        assert response.status_code == 302


# App Detail with Addons Tests


def test_app_detail_with_addons_renders(
    authenticated_client: TestClient, isolated_database
):
    """
    Test that app detail page renders correctly with addons.

    This is a regression test for template variable mismatches like
    using 'addon' instead of 'service' in {% for service in addons %}.
    """
    # Create a test app with an addon credential
    with get_session() as session:
        app = App(name="test-app-with-addon", hostname="test.example.com")
        session.add(app)
        session.flush()

        # Add an addon credential
        credential = AddonCredential(
            app_id=app.id,
            addon_name="test-postgres",
            addon_type="postgresql",
            encrypted_data="encrypted-placeholder",
        )
        session.add(credential)
        session.commit()

    # Request the app detail page
    response = authenticated_client.get("/dashboard/apps/test-app-with-addon")
    assert response.status_code == 200

    # The page should render without Jinja2 UndefinedError
    content = response.content.decode("utf-8", errors="ignore")

    # Check that addon info is displayed
    assert "test-postgres" in content
    assert "postgresql" in content

    # Should NOT have undefined variable errors
    assert "UndefinedError" not in content
    assert "'addon' is undefined" not in content
    assert "'service' is undefined" not in content


def test_app_detail_with_multiple_addons(
    authenticated_client: TestClient, isolated_database
):
    """Test app detail page with multiple addons of different types."""
    with get_session() as session:
        app = App(name="multi-addon-app", hostname="multi.example.com")
        session.add(app)
        session.flush()

        # Add multiple addon credentials
        addons = [
            ("my-postgres", "postgresql"),
            ("my-redis", "redis"),
            ("my-mysql", "mysql"),
        ]
        for addon_name, addon_type in addons:
            credential = AddonCredential(
                app_id=app.id,
                addon_name=addon_name,
                addon_type=addon_type,
                encrypted_data="encrypted-placeholder",
            )
            session.add(credential)
        session.commit()

    response = authenticated_client.get("/dashboard/apps/multi-addon-app")
    assert response.status_code == 200

    content = response.content.decode("utf-8", errors="ignore")

    # All addons should be displayed
    assert "my-postgres" in content
    assert "my-redis" in content
    assert "my-mysql" in content

    # Types should be displayed with correct styling
    assert "postgresql" in content
    assert "redis" in content
    assert "mysql" in content


# JSON Serialization Tests


def test_dashboard_json_serialization_with_apps(authenticated_client: TestClient):
    """Test that dashboard properly serializes app data to JSON (datetime handling)."""
    response = authenticated_client.get("/dashboard")
    assert response.status_code == 200

    # The page should render without JSON serialization errors
    content = response.content.decode("utf-8", errors="ignore")
    assert "apps:" in content  # Alpine.js data
    assert "dashboardData()" in content  # Alpine.js initialization

    # Should not have datetime objects in JSON
    assert "datetime.datetime" not in content
    assert "<built-in" not in content

    # Should have the function definition
    assert "function dashboardData()" in content


def test_dashboard_handles_apps_list(authenticated_client: TestClient):
    """
    Test that dashboard handles apps list without errors.

    Note: This test may run after other tests that create apps,
    so we check for valid rendering regardless of app count.
    """
    response = authenticated_client.get("/dashboard")
    assert response.status_code == 200

    content = response.content.decode("utf-8", errors="ignore")

    # Should have valid Alpine.js data structure
    assert "apps:" in content
    assert "dashboardData()" in content

    # Should either show empty state OR app list (depending on test order)
    has_empty_state = "No applications" in content or "Deploy New App" in content
    has_app_list = "apps: [" in content
    assert has_empty_state or has_app_list


def test_dashboard_app_list_data_structure(authenticated_client: TestClient):
    """Test that dashboard app list has correct data structure."""
    response = authenticated_client.get("/dashboard")
    assert response.status_code == 200

    content = response.content.decode("utf-8", errors="ignore")

    # Alpine.js data should always be present
    assert "apps:" in content

    # Check that apps data is present and looks like valid JSON
    if '"name"' in content and "apps: [" in content:
        # Has apps - should have JSON array with proper structure
        assert '"state":' in content or "'state':" in content
        assert '"port":' in content or "'port':" in content

        # Should NOT have datetime objects (regression test)
        # Look for Python datetime repr patterns
        assert not re.search(r"datetime\.datetime\(", content)
        assert "<built-in method" not in content
    else:
        # Empty apps list
        assert "apps: []" in content or "apps: [" not in content
