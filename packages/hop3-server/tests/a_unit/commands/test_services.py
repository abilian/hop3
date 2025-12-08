# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for service management commands."""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
from sqlalchemy.orm import Session

from hop3.commands.services import (
    AddonsAttachCmd,
    AddonsCreateCmd,
    AddonsDestroyCmd,
    AddonsDetachCmd,
    AddonsInfoCmd,
)
from hop3.orm import App, EnvVar


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    session = Mock(spec=Session)
    return session


@pytest.fixture
def mock_app():
    """Create a mock app instance."""
    app = Mock(spec=App)
    app.id = 1
    app.name = "test-app"
    app.env_vars = []  # Initialize as empty list for iteration
    return app


def test_services_create_requires_arguments(mock_db_session):
    """Test that services:create requires both service type and name."""
    cmd = AddonsCreateCmd(db_session=mock_db_session)
    result = cmd.call()

    assert len(result) == 1
    assert result[0]["t"] == "text"
    assert "Usage:" in result[0]["text"]


def test_services_create_with_postgres(mock_db_session):
    """Test creating a PostgreSQL service."""
    with patch("hop3.commands.services.get_addon") as mock_get_service:
        mock_service = Mock()
        mock_get_service.return_value = mock_service

        cmd = AddonsCreateCmd(db_session=mock_db_session)
        result = cmd.call("postgres", "my-database")

        mock_get_service.assert_called_once_with("postgres", "my-database")
        mock_service.create.assert_called_once()

        assert len(result) == 2
        assert "created successfully" in result[0]["text"]


def test_services_create_handles_errors(mock_db_session):
    """Test error handling in services:create."""
    with patch("hop3.commands.services.get_addon") as mock_get_service:
        mock_get_service.side_effect = RuntimeError("Service type not found")

        cmd = AddonsCreateCmd(db_session=mock_db_session)
        result = cmd.call("invalid-type", "my-service")

        assert len(result) == 1
        assert result[0]["t"] == "error"
        assert "Service type not found" in result[0]["text"]


def test_services_attach_requires_app_name(mock_db_session):
    """Test that services:attach requires --app parameter."""
    cmd = AddonsAttachCmd(db_session=mock_db_session)
    result = cmd.call("my-database")

    assert len(result) == 1
    assert result[0]["t"] == "error"
    assert "--app parameter is required" in result[0]["text"]


def test_services_attach_app_not_found(mock_db_session):
    """Test error when app is not found."""
    with patch("hop3.orm.repositories.AppRepository") as mock_repo_class:
        mock_repo = mock_repo_class.return_value
        mock_repo.get_one_or_none.return_value = None

        cmd = AddonsAttachCmd(db_session=mock_db_session)
        result = cmd.call("my-database", "--app", "nonexistent-app")

        assert len(result) == 1
        assert result[0]["t"] == "error"
        assert "not found" in result[0]["text"]


def test_services_attach_success(mock_db_session, mock_app):
    """Test successful service attachment."""
    with (
        patch("hop3.orm.repositories.AppRepository") as mock_repo_class,
        patch("hop3.commands.services.get_addon") as mock_get_service,
        patch("hop3.commands.services.get_credential_encryptor") as mock_encryptor,
    ):
        mock_repo = mock_repo_class.return_value
        mock_repo.get_one_or_none.return_value = mock_app

        mock_service = Mock()
        mock_service.get_connection_details.return_value = {
            "DATABASE_URL": "postgresql://user:pass@localhost/db",
            "PGHOST": "localhost",
        }
        mock_get_service.return_value = mock_service

        # Mock encryptor
        mock_enc_instance = mock_encryptor.return_value
        mock_enc_instance.encrypt.return_value = "encrypted_data"

        # Mock query to return no existing credential and no env vars
        def query_side_effect(model):
            mock_query = Mock()
            mock_query.filter_by.return_value.first.return_value = None
            return mock_query

        mock_db_session.query.side_effect = query_side_effect

        cmd = AddonsAttachCmd(db_session=mock_db_session)
        result = cmd.call("my-database", "--app", "test-app")

        assert len(result) == 3
        assert "attached" in result[0]["text"].lower()
        assert "DATABASE_URL" in result[1]["text"]
        mock_db_session.commit.assert_called_once()


def test_services_attach_updates_existing_vars(mock_db_session, mock_app):
    """Test that services:attach updates existing environment variables."""
    with (
        patch("hop3.orm.repositories.AppRepository") as mock_repo_class,
        patch("hop3.commands.services.get_addon") as mock_get_service,
        patch("hop3.commands.services.get_credential_encryptor") as mock_encryptor,
    ):
        # Create existing env var and add to mock app's env_vars
        existing_var = Mock(spec=EnvVar)
        existing_var.name = "DATABASE_URL"
        existing_var.value = "old_value"
        mock_app.env_vars = [existing_var]  # Initialize with existing var

        mock_repo = mock_repo_class.return_value
        mock_repo.get_one_or_none.return_value = mock_app

        mock_service = Mock()
        mock_service.get_connection_details.return_value = {
            "DATABASE_URL": "postgresql://user:pass@localhost/db",
        }
        mock_get_service.return_value = mock_service

        # Mock encryptor
        mock_enc_instance = mock_encryptor.return_value
        mock_enc_instance.encrypt.return_value = "encrypted_data"

        # Mock query to return no credential (env vars now handled via app.env_vars)
        def query_side_effect(model):
            mock_query = Mock()
            mock_query.filter_by.return_value.first.return_value = None
            return mock_query

        mock_db_session.query.side_effect = query_side_effect

        cmd = AddonsAttachCmd(db_session=mock_db_session)
        result = cmd.call("my-database", "--app", "test-app")

        assert "Updated DATABASE_URL" in result[1]["text"]
        assert existing_var.value == "postgresql://user:pass@localhost/db"


def test_services_detach_success(mock_db_session, mock_app):
    """Test successful service detachment."""
    with (
        patch("hop3.orm.repositories.AppRepository") as mock_repo_class,
        patch("hop3.commands.services.get_credential_encryptor") as mock_encryptor,
    ):
        mock_repo = mock_repo_class.return_value
        mock_repo.get_one_or_none.return_value = mock_app

        # Mock stored credential
        mock_credential = Mock()
        mock_credential.encrypted_data = "encrypted_data"

        # Mock decryptor
        mock_enc_instance = mock_encryptor.return_value
        mock_enc_instance.decrypt.return_value = {
            "DATABASE_URL": "postgresql://user:pass@localhost/db",
            "PGHOST": "localhost",
        }

        # Mock existing env var
        existing_var = Mock(spec=EnvVar)

        # Mock query to return credential first, then env vars
        def query_side_effect(model):
            mock_query = Mock()
            if model.__name__ == "AddonCredential":
                mock_query.filter_by.return_value.first.return_value = mock_credential
            else:  # EnvVar
                mock_query.filter_by.return_value.first.return_value = existing_var
            return mock_query

        mock_db_session.query.side_effect = query_side_effect

        cmd = AddonsDetachCmd(db_session=mock_db_session)
        result = cmd.call("my-database", "--app", "test-app")

        assert "detached" in result[0]["text"].lower()
        mock_db_session.delete.assert_called()
        mock_db_session.commit.assert_called_once()


def test_services_destroy_success(mock_db_session):
    """Test successful service destruction."""
    with patch("hop3.commands.services.get_addon") as mock_get_service:
        mock_service = Mock()
        mock_get_service.return_value = mock_service

        # Mock query to return empty list of credentials
        mock_query = Mock()
        mock_query.filter_by.return_value.all.return_value = []
        mock_db_session.query.return_value = mock_query

        cmd = AddonsDestroyCmd(db_session=mock_db_session)
        result = cmd.call("my-database", "--service-type", "postgres")

        mock_service.destroy.assert_called_once()
        assert "destroyed successfully" in result[0]["text"]


def test_services_info_success(mock_db_session):
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

        cmd = AddonsInfoCmd(db_session=mock_db_session)
        result = cmd.call("my-database")

        mock_service.info.assert_called_once()
        assert "my-database" in result[0]["text"]
        assert "42.5" in result[0]["text"]
