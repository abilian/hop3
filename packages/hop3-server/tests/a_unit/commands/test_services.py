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
    AddonDetachCmd,
    AddonShowCmd,
)
from hop3.orm import App, EnvVar
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


def test_services_attach_success(
    mock_app_repo, mock_addon_credential_repo, mock_env_var_repo, mock_app
):
    """Test successful service attachment."""
    with (
        patch("hop3.commands.services.get_addon") as mock_get_service,
        patch("hop3.commands.services.get_credential_encryptor") as mock_encryptor,
    ):
        mock_app_repo.get_one_or_none.return_value = mock_app

        mock_service = Mock()
        mock_service.get_connection_details.return_value = {
            "DATABASE_URL": "postgresql://user:pass@localhost/db",
            "PGHOST": "localhost",
        }
        mock_get_service.return_value = mock_service

        # Mock encryptor
        mock_enc_instance = mock_encryptor.return_value
        mock_enc_instance.encrypt.return_value = "encrypted_data"

        # Mock credential repo to return no existing credential
        mock_addon_credential_repo.get_by_app_addon.return_value = None

        # Mock env var repo to return no existing vars
        mock_env_var_repo.get_by_app_and_name.return_value = None

        cmd = AddonAttachCmd(
            app_repo=mock_app_repo,
            addon_credential_repo=mock_addon_credential_repo,
            env_var_repo=mock_env_var_repo,
        )
        result = cmd.call("my-database", "--app", "test-app")

        # 3 informational items + 1 summary item (ADR 036 D19c).
        assert len(result) == 4
        assert "attached" in result[0]["text"].lower()
        assert "DATABASE_URL" in result[1]["text"]
        assert result[-1]["t"] == "summary"
        mock_addon_credential_repo.session.commit.assert_called_once()


def test_services_attach_updates_existing_vars(
    mock_app_repo, mock_addon_credential_repo, mock_env_var_repo, mock_app
):
    """Test that services:attach updates existing environment variables."""
    with (
        patch("hop3.commands.services.get_addon") as mock_get_service,
        patch("hop3.commands.services.get_credential_encryptor") as mock_encryptor,
    ):
        # Create existing env var
        existing_var = Mock(spec=EnvVar)
        existing_var.name = "DATABASE_URL"
        existing_var.value = "old_value"
        mock_app.env_vars = [existing_var]  # Initialize with existing var

        mock_app_repo.get_one_or_none.return_value = mock_app

        mock_service = Mock()
        mock_service.get_connection_details.return_value = {
            "DATABASE_URL": "postgresql://user:pass@localhost/db",
        }
        mock_get_service.return_value = mock_service

        # Mock encryptor
        mock_enc_instance = mock_encryptor.return_value
        mock_enc_instance.encrypt.return_value = "encrypted_data"

        # Mock credential repo to return no existing credential
        mock_addon_credential_repo.get_by_app_addon.return_value = None

        # Mock env var repo to return existing var
        mock_env_var_repo.get_by_app_and_name.return_value = existing_var

        cmd = AddonAttachCmd(
            app_repo=mock_app_repo,
            addon_credential_repo=mock_addon_credential_repo,
            env_var_repo=mock_env_var_repo,
        )
        result = cmd.call("my-database", "--app", "test-app")

        assert "Updated DATABASE_URL" in result[1]["text"]
        assert existing_var.value == "postgresql://user:pass@localhost/db"


def test_services_detach_success(
    mock_app_repo, mock_addon_credential_repo, mock_env_var_repo, mock_app
):
    """Test successful service detachment."""
    with patch("hop3.commands.services.get_credential_encryptor") as mock_encryptor:
        mock_app_repo.get_one_or_none.return_value = mock_app

        # Mock stored credential
        mock_credential = Mock()
        mock_credential.encrypted_data = "encrypted_data"
        mock_addon_credential_repo.get_by_app_addon.return_value = mock_credential

        # Mock decryptor
        mock_enc_instance = mock_encryptor.return_value
        mock_enc_instance.decrypt.return_value = {
            "DATABASE_URL": "postgresql://user:pass@localhost/db",
            "PGHOST": "localhost",
        }

        # Mock existing env var
        existing_var = Mock(spec=EnvVar)
        mock_env_var_repo.get_by_app_and_name.return_value = existing_var

        cmd = AddonDetachCmd(
            app_repo=mock_app_repo,
            addon_credential_repo=mock_addon_credential_repo,
            env_var_repo=mock_env_var_repo,
        )
        result = cmd.call("my-database", "--app", "test-app")

        assert "detached" in result[0]["text"].lower()
        mock_addon_credential_repo.delete.assert_called()
        mock_addon_credential_repo.session.commit.assert_called_once()


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
