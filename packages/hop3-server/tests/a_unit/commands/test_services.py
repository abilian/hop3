# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for service management commands."""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from hop3.commands.services import (
    AddonAttachCmd,
    AddonCreateCmd,
    AddonDestroyCmd,
    AddonListCmd,
    AddonShowCmd,
)
from hop3.orm import App
from hop3.orm.repositories import (
    AddonCredentialRepository,
    AppRepository,
    EnvVarRepository,
)


@pytest.fixture
def mock_app_repo():
    """Create a mock app repository."""
    return Mock(spec=AppRepository)


@pytest.fixture
def mock_addon_credential_repo():
    """Create a mock addon credential repository."""
    repo = Mock(spec=AddonCredentialRepository)
    # Add session attribute for commit/expire_all calls
    repo.session = Mock()
    return repo


@pytest.fixture
def mock_env_var_repo():
    """Create a mock env var repository."""
    return Mock(spec=EnvVarRepository)


@pytest.fixture
def mock_app():
    """Create a mock app instance."""
    app = Mock(spec=App)
    app.id = 1
    app.name = "test-app"
    app.env_vars = []  # Initialize as empty list for iteration
    return app


def test_services_create_requires_arguments():
    """Test that services:create requires both service type and name."""
    cmd = AddonCreateCmd()
    result = cmd.call()

    assert len(result) == 1
    assert result[0]["t"] == "text"
    assert "Usage:" in result[0]["text"]


def test_services_create_with_postgres():
    """Test creating a PostgreSQL service."""
    with patch("hop3.commands.services.get_addon") as mock_get_service:
        mock_service = Mock()
        mock_get_service.return_value = mock_service

        cmd = AddonCreateCmd()
        result = cmd.call("postgres", "my-database")

        mock_get_service.assert_called_once_with("postgres", "my-database")
        mock_service.create.assert_called_once()

        # 2 informational items + 1 summary item (ADR 036 D19c).
        assert len(result) == 3
        assert "created successfully" in result[0]["text"]
        assert result[-1]["t"] == "summary"


def test_services_create_handles_errors():
    """Test error handling in services:create."""
    with patch("hop3.commands.services.get_addon") as mock_get_service:
        mock_get_service.side_effect = RuntimeError("Service type not found")

        cmd = AddonCreateCmd()

        # command_context raises ValueError for JSON-RPC error handling
        with pytest.raises(ValueError) as exc_info:
            cmd.call("invalid-type", "my-service")

        assert "Service type not found" in str(exc_info.value)


@pytest.mark.parametrize(
    "bad_name",
    [
        "foo`; DROP DATABASE",
        "ab",  # too short
        "-leading-hyphen",
        "name with spaces",
    ],
)
def test_services_create_rejects_unsafe_addon_name(bad_name):
    """addon_name flowing into raw SQL identifier interpolation must be validated."""
    with patch("hop3.commands.services.get_addon") as mock_get_service:
        cmd = AddonCreateCmd()
        result = cmd.call("postgres", bad_name)

        # Validation rejects before get_addon is called.
        mock_get_service.assert_not_called()
        assert len(result) == 1
        assert result[0]["t"] == "error"
        assert "Invalid service name" in result[0]["text"]


def test_services_attach_requires_app_name(
    mock_app_repo, mock_addon_credential_repo, mock_env_var_repo
):
    """Test that services:attach requires --app parameter."""
    cmd = AddonAttachCmd(
        app_repo=mock_app_repo,
        addon_credential_repo=mock_addon_credential_repo,
        env_var_repo=mock_env_var_repo,
    )
    result = cmd.call("my-database")

    assert len(result) == 1
    assert result[0]["t"] == "error"
    assert "--app parameter is required" in result[0]["text"]


def test_services_attach_app_not_found(
    mock_app_repo, mock_addon_credential_repo, mock_env_var_repo
):
    """Test error when app is not found."""
    mock_app_repo.get_one_or_none.return_value = None

    cmd = AddonAttachCmd(
        app_repo=mock_app_repo,
        addon_credential_repo=mock_addon_credential_repo,
        env_var_repo=mock_env_var_repo,
    )

    # App not found raises ValueError for JSON-RPC error handling
    with pytest.raises(ValueError) as exc_info:
        cmd.call("my-database", "--app", "nonexistent-app")

    assert "not found" in str(exc_info.value)


# NOTE: attach/detach now route their env-var injection through
# `sync_addon_env_vars` (a real encrypt → store → decrypt → namespace round-trip
# that picks primary vs prefixed vars). That can't be represented with mocked
# repos/encryptor, and the project prefers state-verification over mock-behavior
# tests. The full behaviour — attach (primary/secondary/update), detach (removal
# + auto-promote), and promote — is covered against a real DB in
# tests/b_integration/commands/test_services_commands_integration.py and
# test_addon_promote.py. The former white-box attach/detach unit tests lived here.


def test_services_destroy_success(mock_addon_credential_repo):
    """Test successful service destruction."""
    with patch("hop3.commands.services.get_addon") as mock_get_service:
        mock_service = Mock()
        mock_get_service.return_value = mock_service

        # Mock list_by_addon to return empty list of credentials
        mock_addon_credential_repo.list_by_addon.return_value = []

        cmd = AddonDestroyCmd(addon_credential_repo=mock_addon_credential_repo)
        result = cmd.call("my-database", "--type", "postgres")

        mock_service.destroy.assert_called_once()
        assert "destroyed successfully" in result[0]["text"]


def test_addon_list_all_instances(mock_app_repo, mock_addon_credential_repo):
    """`addon list` lists provisioned instances with their attached apps."""
    cred = Mock()
    cred.addon_type = "postgres"
    cred.addon_name = "db1"
    cred.app = Mock(name="web")
    cred.app.name = "web"
    mock_addon_credential_repo.list_all_with_apps.return_value = [cred]

    cmd = AddonListCmd(
        app_repo=mock_app_repo, addon_credential_repo=mock_addon_credential_repo
    )
    with patch(
        "hop3.commands.services.list_addon_instances",
        return_value=[("postgres", "db1"), ("redis", "cache1")],
    ):
        result = cmd.call()

    table_item = next(item for item in result if item["t"] == "table")
    assert ["db1", "postgres", "web"] in table_item["rows"]
    assert ["cache1", "redis", "-"] in table_item["rows"]


def test_addon_list_empty(mock_app_repo, mock_addon_credential_repo):
    """`addon list` with no instances tells the user how to create one."""
    cmd = AddonListCmd(
        app_repo=mock_app_repo, addon_credential_repo=mock_addon_credential_repo
    )
    with patch("hop3.commands.services.list_addon_instances", return_value=[]):
        result = cmd.call()

    assert any("No addon instances" in item.get("text", "") for item in result)


def test_addon_list_for_app(mock_app_repo, mock_addon_credential_repo, mock_app):
    """`addon list --app X` lists addons attached to that app."""
    cred = Mock()
    cred.addon_type = "postgres"
    cred.addon_name = "db1"
    mock_app.addon_credentials = [cred]
    mock_app_repo.get_one_or_none.return_value = mock_app

    cmd = AddonListCmd(
        app_repo=mock_app_repo, addon_credential_repo=mock_addon_credential_repo
    )
    result = cmd.call("--app", "test-app")

    table_item = next(item for item in result if item["t"] == "table")
    assert ["db1", "postgres"] in table_item["rows"]


def test_addon_list_for_app_not_found(mock_app_repo, mock_addon_credential_repo):
    """`addon list --app X` fails loudly when the app does not exist."""
    mock_app_repo.get_one_or_none.return_value = None

    cmd = AddonListCmd(
        app_repo=mock_app_repo, addon_credential_repo=mock_addon_credential_repo
    )
    result = cmd.call("--app", "ghost")

    assert result[0]["t"] == "error"
    assert "not found" in result[0]["text"]


def test_services_info_success():
    """Test successful service info retrieval."""
    with patch("hop3.commands.services.get_addon") as mock_get_service:
        mock_service = Mock()
        mock_service.info.return_value = {
            "addon_name": "my-database",
            "type": "postgres",
            "size_mb": 42.5,
            "table_count": 10,
        }
        mock_get_service.return_value = mock_service

        cmd = AddonShowCmd()
        result = cmd.call("my-database")

        mock_service.info.assert_called_once()
        assert "my-database" in result[0]["text"]
        assert "42.5" in result[0]["text"]
