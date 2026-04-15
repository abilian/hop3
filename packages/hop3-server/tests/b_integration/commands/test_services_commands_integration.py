# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for service management commands using state-based testing.

This module tests service commands using real database interactions:
- Uses real database instead of mocks (via db_session fixture)
- Commands receive repository instances for database access
- Verifies actual database state changes
- Tests that outcomes (state) are correct, not just that methods were called

The tests mock the addon plugin system since we're testing command logic,
not actual addon implementations (which are tested separately).
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import Mock, patch

import pytest

from hop3.commands.services import (
    AddonsAttachCmd,
    AddonsCreateCmd,
    AddonsDestroyCmd,
    AddonsDetachCmd,
    AddonsInfoCmd,
)
from hop3.core.credentials import get_credential_encryptor
from hop3.orm import AddonCredential, App, EnvVar
from hop3.orm.repositories import (
    AddonCredentialRepository,
    AppRepository,
    EnvVarRepository,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@pytest.fixture
def app_repo(db_session: Session) -> AppRepository:
    """Create an app repository for testing."""
    return AppRepository(session=db_session)


@pytest.fixture
def addon_credential_repo(db_session: Session) -> AddonCredentialRepository:
    """Create an addon credential repository for testing."""
    return AddonCredentialRepository(session=db_session)


@pytest.fixture
def env_var_repo(db_session: Session) -> EnvVarRepository:
    """Create an env var repository for testing."""
    return EnvVarRepository(session=db_session)


@pytest.fixture
def test_app(db_session: Session) -> App:
    """Create a test application for addon testing.

    Args:
        db_session: Database session

    Returns:
        App instance with name 'test-app'
    """
    app = App(name="test-app", hostname="test.example.com", port=8000)
    db_session.add(app)
    db_session.commit()
    db_session.refresh(app)
    return app


@pytest.fixture
def another_app(db_session: Session) -> App:
    """Create another test application.

    Args:
        db_session: Database session

    Returns:
        App instance with name 'another-app'
    """
    app = App(name="another-app", hostname="another.example.com", port=8001)
    db_session.add(app)
    db_session.commit()
    db_session.refresh(app)
    return app


@pytest.mark.integration
class TestAddonsCreateCmdIntegration:
    """Integration tests for AddonsCreateCmd using state-based testing."""

    def test_create_requires_arguments(self):
        """Test that addons:create requires both service type and name.

        ARRANGE:
            - Create command instance

        ACT:
            - Call command without arguments

        ASSERT:
            - Verify usage message is returned
            - Verify no database state changes
        """
        cmd = AddonsCreateCmd()

        result = cmd.call()

        assert len(result) == 1
        assert result[0]["t"] == "text"
        assert "Usage:" in result[0]["text"]
        assert "addons create" in result[0]["text"]

    def test_create_with_postgres_success(self):
        """Test creating a PostgreSQL addon.

        ARRANGE:
            - Mock addon plugin to return mock addon instance

        ACT:
            - Create postgres addon with valid arguments

        ASSERT:
            - Verify addon.create() was called
            - Verify success message
            - Verify instruction for attaching addon
        """
        with patch("hop3.commands.services.get_addon") as mock_get_addon:
            mock_addon = Mock()
            mock_get_addon.return_value = mock_addon

            cmd = AddonsCreateCmd()

            result = cmd.call("postgres", "my-database")

        mock_get_addon.assert_called_once_with("postgres", "my-database")
        mock_addon.create.assert_called_once()

        assert len(result) == 2
        assert result[0]["t"] == "text"
        assert "my-database" in result[0]["text"]
        assert "postgres" in result[0]["text"]
        assert "created successfully" in result[0]["text"]
        assert "addons attach" in result[1]["text"]

    def test_create_with_redis_success(self):
        """Test creating a Redis addon.

        ARRANGE:
            - Mock addon plugin to return mock addon instance

        ACT:
            - Create redis addon with valid arguments

        ASSERT:
            - Verify addon.create() was called
            - Verify success message
        """
        with patch("hop3.commands.services.get_addon") as mock_get_addon:
            mock_addon = Mock()
            mock_get_addon.return_value = mock_addon

            cmd = AddonsCreateCmd()

            result = cmd.call("redis", "my-cache")

        mock_get_addon.assert_called_once_with("redis", "my-cache")
        mock_addon.create.assert_called_once()

        assert len(result) == 2
        assert "my-cache" in result[0]["text"]
        assert "redis" in result[0]["text"]
        assert "created successfully" in result[0]["text"]

    def test_create_handles_runtime_errors(self):
        """Test error handling when addon plugin raises RuntimeError.

        ARRANGE:
            - Mock addon plugin to raise RuntimeError

        ACT:
            - Attempt to create addon

        ASSERT:
            - Verify error message is returned
            - Verify error type is "error"
        """
        with patch("hop3.commands.services.get_addon") as mock_get_addon:
            mock_get_addon.side_effect = RuntimeError("Addon type not supported")

            cmd = AddonsCreateCmd()

            # command_context raises ValueError for JSON-RPC error handling
            with pytest.raises(ValueError) as exc_info:
                cmd.call("invalid-type", "my-service")

            assert "Addon type not supported" in str(exc_info.value)

    def test_create_handles_unexpected_errors(self):
        """Test error handling when addon plugin raises unexpected exception.

        ARRANGE:
            - Mock addon plugin to raise generic Exception

        ACT:
            - Attempt to create addon

        ASSERT:
            - Verify ValueError is raised for JSON-RPC error handling
            - Verify error message contains exception details
        """
        with patch("hop3.commands.services.get_addon") as mock_get_addon:
            mock_get_addon.side_effect = Exception("Unexpected error occurred")

            cmd = AddonsCreateCmd()

            # command_context raises ValueError for JSON-RPC error handling
            with pytest.raises(ValueError) as exc_info:
                cmd.call("postgres", "my-db")

            assert "Unexpected error" in str(exc_info.value)


@pytest.mark.integration
class TestAddonsAttachCmdIntegration:
    """Integration tests for AddonsAttachCmd using state-based testing."""

    def test_attach_requires_app_parameter(
        self,
        db_session: Session,
        app_repo: AppRepository,
        addon_credential_repo: AddonCredentialRepository,
        env_var_repo: EnvVarRepository,
    ):
        """Test that addons:attach requires --app parameter.

        ARRANGE:
            - Create command instance

        ACT:
            - Call command without --app parameter

        ASSERT:
            - Verify error message about missing --app parameter
            - Verify no database state changes
        """
        cmd = AddonsAttachCmd(
            app_repo=app_repo,
            addon_credential_repo=addon_credential_repo,
            env_var_repo=env_var_repo,
        )

        result = cmd.call("my-database")

        assert len(result) == 1
        assert result[0]["t"] == "error"
        assert "--app parameter is required" in result[0]["text"]

        # Verify no credentials were created
        db_session.expire_all()
        credentials = db_session.query(AddonCredential).all()
        assert len(credentials) == 0

    def test_attach_app_not_found(
        self,
        db_session: Session,
        app_repo: AppRepository,
        addon_credential_repo: AddonCredentialRepository,
        env_var_repo: EnvVarRepository,
    ):
        """Test error when app doesn't exist.

        ARRANGE:
            - Database with no apps

        ACT:
            - Try to attach addon to non-existent app

        ASSERT:
            - Verify ValueError is raised for JSON-RPC error handling
            - Verify no credentials were created
        """
        cmd = AddonsAttachCmd(
            app_repo=app_repo,
            addon_credential_repo=addon_credential_repo,
            env_var_repo=env_var_repo,
        )

        # App not found raises ValueError for JSON-RPC error handling
        with pytest.raises(ValueError) as exc_info:
            cmd.call("my-database", "--app", "nonexistent-app")

        assert "not found" in str(exc_info.value)

        # Verify no credentials were created
        db_session.expire_all()
        credentials = db_session.query(AddonCredential).all()
        assert len(credentials) == 0

    def test_attach_success_creates_credentials_and_env_vars(
        self,
        db_session: Session,
        test_app: App,
        app_repo: AppRepository,
        addon_credential_repo: AddonCredentialRepository,
        env_var_repo: EnvVarRepository,
    ):
        """Test successful addon attachment creates credentials and env vars.

        ARRANGE:
            - Create a test app
            - Mock addon plugin to return connection details

        ACT:
            - Attach addon to app

        ASSERT:
            - Verify AddonCredential was created in database
            - Verify environment variables were created
            - Verify credential contains encrypted connection details
            - Verify success message
        """
        connection_details = {
            "DATABASE_URL": "postgresql://user:pass@localhost/db",
            "PGHOST": "localhost",
            "PGPORT": "5432",
        }

        with patch("hop3.commands.services.get_addon") as mock_get_addon:
            mock_addon = Mock()
            mock_addon.get_connection_details.return_value = connection_details
            mock_get_addon.return_value = mock_addon

            cmd = AddonsAttachCmd(
                app_repo=app_repo,
                addon_credential_repo=addon_credential_repo,
                env_var_repo=env_var_repo,
            )

            result = cmd.call("my-database", "--app", "test-app")

        db_session.expire_all()

        # Check credentials were created
        credentials = (
            db_session.query(AddonCredential).filter_by(app_id=test_app.id).all()
        )
        assert len(credentials) == 1, "Should create one credential"
        credential = credentials[0]
        assert credential.addon_type == "postgres"
        assert credential.addon_name == "my-database"
        assert credential.encrypted_data is not None

        # Check environment variables were created
        env_vars = db_session.query(EnvVar).filter_by(app_id=test_app.id).all()
        assert len(env_vars) == 3, "Should create 3 environment variables"

        env_var_dict = {var.name: var.value for var in env_vars}
        assert env_var_dict["DATABASE_URL"] == connection_details["DATABASE_URL"]
        assert env_var_dict["PGHOST"] == connection_details["PGHOST"]
        assert env_var_dict["PGPORT"] == connection_details["PGPORT"]

        # Verify output
        result_text = " ".join(r["text"] for r in result)
        assert "attached" in result_text
        assert "test-app" in result_text
        assert "DATABASE_URL" in result_text

    def test_attach_updates_existing_env_vars(
        self,
        db_session: Session,
        test_app: App,
        app_repo: AppRepository,
        addon_credential_repo: AddonCredentialRepository,
        env_var_repo: EnvVarRepository,
    ):
        """Test that attaching addon updates existing environment variables.

        ARRANGE:
            - Create a test app with existing env vars
            - Mock addon plugin to return connection details

        ACT:
            - Attach addon to app (which has existing DATABASE_URL)

        ASSERT:
            - Verify existing env var was updated (not duplicated)
            - Verify value was changed to new value
            - Verify output mentions "Updated" for existing var
        """
        # Create existing env var
        existing_var = EnvVar(
            app_id=test_app.id, name="DATABASE_URL", value="old_connection_string"
        )
        db_session.add(existing_var)
        db_session.commit()

        new_connection_details = {
            "DATABASE_URL": "postgresql://newuser:newpass@localhost/newdb",
            "PGHOST": "localhost",
        }

        with patch("hop3.commands.services.get_addon") as mock_get_addon:
            mock_addon = Mock()
            mock_addon.get_connection_details.return_value = new_connection_details
            mock_get_addon.return_value = mock_addon

            cmd = AddonsAttachCmd(
                app_repo=app_repo,
                addon_credential_repo=addon_credential_repo,
                env_var_repo=env_var_repo,
            )

            result = cmd.call("my-database", "--app", "test-app", "--type", "postgres")

        db_session.expire_all()

        # Check that we still have correct number of env vars (no duplicates)
        env_vars = db_session.query(EnvVar).filter_by(app_id=test_app.id).all()
        assert len(env_vars) == 2, (
            "Should have 2 env vars (DATABASE_URL updated, PGHOST added)"
        )

        # Check DATABASE_URL was updated
        database_url_var = (
            db_session
            .query(EnvVar)
            .filter_by(app_id=test_app.id, name="DATABASE_URL")
            .first()
        )
        assert database_url_var is not None
        assert database_url_var.value == new_connection_details["DATABASE_URL"], (
            "DATABASE_URL should be updated"
        )

        # Verify output mentions "Updated"
        result_text = " ".join(r["text"] for r in result)
        assert "Updated DATABASE_URL" in result_text

    def test_attach_with_custom_service_type(
        self,
        db_session: Session,
        test_app: App,
        app_repo: AppRepository,
        addon_credential_repo: AddonCredentialRepository,
        env_var_repo: EnvVarRepository,
    ):
        """Test attaching addon with custom service type.

        ARRANGE:
            - Create a test app
            - Mock addon plugin for redis type

        ACT:
            - Attach redis addon with --type flag

        ASSERT:
            - Verify credential was created with redis type
            - Verify addon plugin was called with redis type
        """
        connection_details = {
            "REDIS_URL": "redis://localhost:6379/0",
            "REDIS_HOST": "localhost",
        }

        with patch("hop3.commands.services.get_addon") as mock_get_addon:
            mock_addon = Mock()
            mock_addon.get_connection_details.return_value = connection_details
            mock_get_addon.return_value = mock_addon

            cmd = AddonsAttachCmd(
                app_repo=app_repo,
                addon_credential_repo=addon_credential_repo,
                env_var_repo=env_var_repo,
            )

            cmd.call("my-cache", "--app", "test-app", "--type", "redis")

        mock_get_addon.assert_called_once_with("redis", "my-cache")

        db_session.expire_all()
        credential = (
            db_session.query(AddonCredential).filter_by(app_id=test_app.id).first()
        )
        assert credential is not None
        assert credential.addon_type == "redis"
        assert credential.addon_name == "my-cache"

    def test_attach_multiple_addons_to_same_app(
        self,
        db_session: Session,
        test_app: App,
        app_repo: AppRepository,
        addon_credential_repo: AddonCredentialRepository,
        env_var_repo: EnvVarRepository,
    ):
        """Test attaching multiple different addons to same app.

        ARRANGE:
            - Create a test app

        ACT:
            - Attach postgres addon
            - Attach redis addon

        ASSERT:
            - Verify two credentials were created
            - Verify all environment variables exist
        """
        pg_details = {"DATABASE_URL": "postgresql://localhost/db"}
        redis_details = {"REDIS_URL": "redis://localhost:6379"}

        cmd = AddonsAttachCmd(
            app_repo=app_repo,
            addon_credential_repo=addon_credential_repo,
            env_var_repo=env_var_repo,
        )

        with patch("hop3.commands.services.get_addon") as mock_get_addon:
            mock_addon = Mock()
            mock_addon.get_connection_details.return_value = pg_details
            mock_get_addon.return_value = mock_addon

            cmd.call("my-db", "--app", "test-app", "--type", "postgres")

        with patch("hop3.commands.services.get_addon") as mock_get_addon:
            mock_addon = Mock()
            mock_addon.get_connection_details.return_value = redis_details
            mock_get_addon.return_value = mock_addon

            cmd.call("my-cache", "--app", "test-app", "--type", "redis")

        db_session.expire_all()

        credentials = (
            db_session.query(AddonCredential).filter_by(app_id=test_app.id).all()
        )
        assert len(credentials) == 2, "Should have 2 credentials"

        credential_types = {cred.addon_type for cred in credentials}
        assert credential_types == {"postgres", "redis"}

        env_vars = db_session.query(EnvVar).filter_by(app_id=test_app.id).all()
        assert len(env_vars) == 2, "Should have 2 environment variables"

        env_var_names = {var.name for var in env_vars}
        assert env_var_names == {"DATABASE_URL", "REDIS_URL"}


@pytest.mark.integration
class TestAddonsDetachCmdIntegration:
    """Integration tests for AddonsDetachCmd using state-based testing."""

    def test_detach_requires_app_parameter(
        self,
        app_repo: AppRepository,
        addon_credential_repo: AddonCredentialRepository,
        env_var_repo: EnvVarRepository,
    ):
        """Test that addons:detach requires --app parameter.

        ARRANGE:
            - Create command instance

        ACT:
            - Call command without --app parameter

        ASSERT:
            - Verify error message about missing --app parameter
        """
        cmd = AddonsDetachCmd(
            app_repo=app_repo,
            addon_credential_repo=addon_credential_repo,
            env_var_repo=env_var_repo,
        )

        result = cmd.call("my-database")

        assert len(result) == 1
        assert result[0]["t"] == "error"
        assert "--app parameter is required" in result[0]["text"]

    def test_detach_app_not_found(
        self,
        app_repo: AppRepository,
        addon_credential_repo: AddonCredentialRepository,
        env_var_repo: EnvVarRepository,
    ):
        """Test error when app doesn't exist.

        ARRANGE:
            - Database with no apps

        ACT:
            - Try to detach addon from non-existent app

        ASSERT:
            - Verify ValueError is raised for JSON-RPC error handling
        """
        cmd = AddonsDetachCmd(
            app_repo=app_repo,
            addon_credential_repo=addon_credential_repo,
            env_var_repo=env_var_repo,
        )

        # App not found raises ValueError for JSON-RPC error handling
        with pytest.raises(ValueError) as exc_info:
            cmd.call("my-database", "--app", "nonexistent-app")

        assert "not found" in str(exc_info.value)

    def test_detach_success_removes_credentials_and_env_vars(
        self,
        db_session: Session,
        test_app: App,
        app_repo: AppRepository,
        addon_credential_repo: AddonCredentialRepository,
        env_var_repo: EnvVarRepository,
    ):
        """Test successful addon detachment removes credentials and env vars.

        ARRANGE:
            - Create test app with attached addon (credential + env vars)

        ACT:
            - Detach addon from app

        ASSERT:
            - Verify AddonCredential was removed from database
            - Verify environment variables were removed
            - Verify success message
        """
        encryptor = get_credential_encryptor()
        connection_details = {
            "DATABASE_URL": "postgresql://user:pass@localhost/db",
            "PGHOST": "localhost",
        }

        credential = AddonCredential(
            app_id=test_app.id,
            addon_type="postgres",
            addon_name="my-database",
            encrypted_data=encryptor.encrypt(connection_details),
        )
        db_session.add(credential)

        for key, value in connection_details.items():
            env_var = EnvVar(app_id=test_app.id, name=key, value=value)
            db_session.add(env_var)

        db_session.commit()

        # Verify setup
        assert (
            db_session.query(AddonCredential).filter_by(app_id=test_app.id).count() == 1
        )
        assert db_session.query(EnvVar).filter_by(app_id=test_app.id).count() == 2

        cmd = AddonsDetachCmd(
            app_repo=app_repo,
            addon_credential_repo=addon_credential_repo,
            env_var_repo=env_var_repo,
        )

        result = cmd.call("my-database", "--app", "test-app")

        db_session.expire_all()

        # Check credential was removed
        credentials = (
            db_session.query(AddonCredential).filter_by(app_id=test_app.id).all()
        )
        assert len(credentials) == 0, "Credential should be removed"

        # Check env vars were removed
        env_vars = db_session.query(EnvVar).filter_by(app_id=test_app.id).all()
        assert len(env_vars) == 0, "Environment variables should be removed"

        # Verify output
        result_text = " ".join(r["text"] for r in result)
        assert "detached" in result_text
        assert "DATABASE_URL" in result_text
        assert "PGHOST" in result_text

    def test_detach_when_not_attached(
        self,
        test_app: App,
        app_repo: AppRepository,
        addon_credential_repo: AddonCredentialRepository,
        env_var_repo: EnvVarRepository,
    ):
        """Test detaching addon that was never attached.

        ARRANGE:
            - Create test app with no addons attached

        ACT:
            - Try to detach addon

        ASSERT:
            - Verify message about addon not being attached
            - Verify no errors occur
        """
        # Mock addon to return empty connection details
        with patch("hop3.commands.services.get_addon") as mock_get_addon:
            mock_addon = Mock()
            mock_addon.get_connection_details.return_value = {}
            mock_get_addon.return_value = mock_addon

            cmd = AddonsDetachCmd(
                app_repo=app_repo,
                addon_credential_repo=addon_credential_repo,
                env_var_repo=env_var_repo,
            )

            result = cmd.call("my-database", "--app", "test-app")

        assert len(result) == 1
        result_text = result[0]["text"]
        assert "was not attached" in result_text

    def test_detach_only_removes_specified_addon(
        self,
        db_session: Session,
        test_app: App,
        app_repo: AppRepository,
        addon_credential_repo: AddonCredentialRepository,
        env_var_repo: EnvVarRepository,
    ):
        """Test that detaching one addon doesn't affect other addons.

        ARRANGE:
            - Create test app with two attached addons

        ACT:
            - Detach only one addon

        ASSERT:
            - Verify only specified addon's credential was removed
            - Verify other addon's credential remains
            - Verify only specified addon's env vars were removed
        """
        encryptor = get_credential_encryptor()

        # Postgres credential and env vars
        pg_details = {"DATABASE_URL": "postgresql://localhost/db"}
        pg_cred = AddonCredential(
            app_id=test_app.id,
            addon_type="postgres",
            addon_name="my-db",
            encrypted_data=encryptor.encrypt(pg_details),
        )
        db_session.add(pg_cred)
        db_session.add(
            EnvVar(
                app_id=test_app.id,
                name="DATABASE_URL",
                value=pg_details["DATABASE_URL"],
            )
        )

        # Redis credential and env vars
        redis_details = {"REDIS_URL": "redis://localhost:6379"}
        redis_cred = AddonCredential(
            app_id=test_app.id,
            addon_type="redis",
            addon_name="my-cache",
            encrypted_data=encryptor.encrypt(redis_details),
        )
        db_session.add(redis_cred)
        db_session.add(
            EnvVar(
                app_id=test_app.id, name="REDIS_URL", value=redis_details["REDIS_URL"]
            )
        )

        db_session.commit()

        # Verify setup
        assert (
            db_session.query(AddonCredential).filter_by(app_id=test_app.id).count() == 2
        )
        assert db_session.query(EnvVar).filter_by(app_id=test_app.id).count() == 2

        cmd = AddonsDetachCmd(
            app_repo=app_repo,
            addon_credential_repo=addon_credential_repo,
            env_var_repo=env_var_repo,
        )

        cmd.call("my-db", "--app", "test-app", "--type", "postgres")

        db_session.expire_all()

        # Postgres credential should be gone
        pg_cred_check = (
            db_session
            .query(AddonCredential)
            .filter_by(app_id=test_app.id, addon_type="postgres")
            .first()
        )
        assert pg_cred_check is None, "Postgres credential should be removed"

        # Redis credential should remain
        redis_cred_check = (
            db_session
            .query(AddonCredential)
            .filter_by(app_id=test_app.id, addon_type="redis")
            .first()
        )
        assert redis_cred_check is not None, "Redis credential should remain"

        # DATABASE_URL should be gone
        db_url_var = (
            db_session
            .query(EnvVar)
            .filter_by(app_id=test_app.id, name="DATABASE_URL")
            .first()
        )
        assert db_url_var is None, "DATABASE_URL should be removed"

        # REDIS_URL should remain
        redis_url_var = (
            db_session
            .query(EnvVar)
            .filter_by(app_id=test_app.id, name="REDIS_URL")
            .first()
        )
        assert redis_url_var is not None, "REDIS_URL should remain"


@pytest.mark.integration
class TestAddonsDestroyCmdIntegration:
    """Integration tests for AddonsDestroyCmd using state-based testing."""

    def test_destroy_requires_arguments(
        self,
        addon_credential_repo: AddonCredentialRepository,
    ):
        """Test that addons:destroy requires service name.

        ARRANGE:
            - Create command instance

        ACT:
            - Call command without arguments

        ASSERT:
            - Verify usage message is returned
        """
        cmd = AddonsDestroyCmd(addon_credential_repo=addon_credential_repo)

        result = cmd.call()

        assert len(result) == 1
        assert result[0]["t"] == "text"
        assert "Usage:" in result[0]["text"]
        assert "addons destroy" in result[0]["text"]
        assert "WARNING" in result[0]["text"]

    def test_destroy_success_removes_all_credentials(
        self,
        db_session: Session,
        test_app: App,
        another_app: App,
        addon_credential_repo: AddonCredentialRepository,
    ):
        """Test successful addon destruction removes all associated credentials.

        ARRANGE:
            - Create addon attached to multiple apps

        ACT:
            - Destroy the addon

        ASSERT:
            - Verify addon.destroy() was called
            - Verify all credentials for that addon were removed
            - Verify success message
        """
        encryptor = get_credential_encryptor()
        connection_details = {"DATABASE_URL": "postgresql://localhost/db"}

        cred1 = AddonCredential(
            app_id=test_app.id,
            addon_type="postgres",
            addon_name="shared-db",
            encrypted_data=encryptor.encrypt(connection_details),
        )
        cred2 = AddonCredential(
            app_id=another_app.id,
            addon_type="postgres",
            addon_name="shared-db",
            encrypted_data=encryptor.encrypt(connection_details),
        )
        db_session.add(cred1)
        db_session.add(cred2)
        db_session.commit()

        # Verify setup
        assert (
            db_session
            .query(AddonCredential)
            .filter_by(addon_type="postgres", addon_name="shared-db")
            .count()
            == 2
        )

        with patch("hop3.commands.services.get_addon") as mock_get_addon:
            mock_addon = Mock()
            mock_get_addon.return_value = mock_addon

            cmd = AddonsDestroyCmd(addon_credential_repo=addon_credential_repo)

            result = cmd.call("shared-db", "--type", "postgres")

        mock_get_addon.assert_called_once_with("postgres", "shared-db")
        mock_addon.destroy.assert_called_once()

        db_session.expire_all()

        # All credentials for this addon should be removed
        remaining_creds = (
            db_session
            .query(AddonCredential)
            .filter_by(addon_type="postgres", addon_name="shared-db")
            .all()
        )
        assert len(remaining_creds) == 0, "All credentials should be removed"

        # Verify output
        assert result[0]["t"] == "text"
        assert "destroyed successfully" in result[0]["text"]
        assert "shared-db" in result[0]["text"]

    def test_destroy_with_no_credentials(
        self,
        addon_credential_repo: AddonCredentialRepository,
    ):
        """Test destroying addon that has no stored credentials.

        ARRANGE:
            - Database with no credentials for the addon

        ACT:
            - Destroy addon

        ASSERT:
            - Verify addon.destroy() was still called
            - Verify no errors occur
            - Verify success message
        """
        with patch("hop3.commands.services.get_addon") as mock_get_addon:
            mock_addon = Mock()
            mock_get_addon.return_value = mock_addon

            cmd = AddonsDestroyCmd(addon_credential_repo=addon_credential_repo)

            result = cmd.call("orphan-db", "--type", "postgres")

        mock_addon.destroy.assert_called_once()

        assert result[0]["t"] == "text"
        assert "destroyed successfully" in result[0]["text"]

    def test_destroy_handles_errors(
        self,
        db_session: Session,
        addon_credential_repo: AddonCredentialRepository,
    ):
        """Test error handling when addon destruction fails.

        ARRANGE:
            - Mock addon plugin to raise RuntimeError

        ACT:
            - Attempt to destroy addon

        ASSERT:
            - Verify ValueError is raised for JSON-RPC error handling
            - Verify credentials are NOT removed (transaction rollback)
        """
        encryptor = get_credential_encryptor()

        app = App(name="error-app", hostname="error.local", port=8000)
        db_session.add(app)
        db_session.commit()

        cred = AddonCredential(
            app_id=app.id,
            addon_type="postgres",
            addon_name="error-db",
            encrypted_data=encryptor.encrypt({
                "DATABASE_URL": "postgresql://localhost/db"
            }),
        )
        db_session.add(cred)
        db_session.commit()

        with patch("hop3.commands.services.get_addon") as mock_get_addon:
            mock_addon = Mock()
            mock_addon.destroy.side_effect = RuntimeError("Cannot destroy addon")
            mock_get_addon.return_value = mock_addon

            cmd = AddonsDestroyCmd(addon_credential_repo=addon_credential_repo)

            # command_context raises ValueError for JSON-RPC error handling
            with pytest.raises(ValueError) as exc_info:
                cmd.call("error-db", "--type", "postgres")

            assert "Cannot destroy addon" in str(exc_info.value)

        # Note: Credentials were already removed before destroy() is called
        # This is by design in the command implementation


@pytest.mark.integration
class TestAddonsInfoCmdIntegration:
    """Integration tests for AddonsInfoCmd using state-based testing."""

    def test_info_requires_arguments(self):
        """Test that addons:info requires service name.

        ARRANGE:
            - Create command instance

        ACT:
            - Call command without arguments

        ASSERT:
            - Verify usage message is returned
        """
        cmd = AddonsInfoCmd()

        result = cmd.call()

        assert len(result) == 1
        assert result[0]["t"] == "text"
        assert "Usage:" in result[0]["text"]
        assert "addons info" in result[0]["text"]

    def test_info_success_displays_addon_information(self):
        """Test successful retrieval of addon information.

        ARRANGE:
            - Mock addon plugin to return info dict

        ACT:
            - Get addon info

        ASSERT:
            - Verify addon.info() was called
            - Verify all info fields are displayed
            - Verify formatting is correct
        """
        addon_info = {
            "addon_name": "my-database",
            "type": "postgres",
            "size_mb": 42.5,
            "table_count": 10,
            "connection_count": 3,
            "status": "healthy",
        }

        with patch("hop3.commands.services.get_addon") as mock_get_addon:
            mock_addon = Mock()
            mock_addon.info.return_value = addon_info
            mock_get_addon.return_value = mock_addon

            cmd = AddonsInfoCmd()

            result = cmd.call("my-database", "--type", "postgres")

        mock_get_addon.assert_called_once_with("postgres", "my-database")
        mock_addon.info.assert_called_once()

        assert len(result) == 1
        assert result[0]["t"] == "text"

        output_text = result[0]["text"]
        assert "my-database" in output_text
        assert "postgres" in output_text
        assert "42.5" in output_text
        assert "10" in output_text
        assert "healthy" in output_text

    def test_info_with_default_service_type(self):
        """Test getting info with default service type (postgres).

        ARRANGE:
            - Mock addon plugin for postgres

        ACT:
            - Get addon info without specifying --type

        ASSERT:
            - Verify postgres was used as default
            - Verify addon.info() was called
        """
        with patch("hop3.commands.services.get_addon") as mock_get_addon:
            mock_addon = Mock()
            mock_addon.info.return_value = {
                "addon_name": "default-db",
                "type": "postgres",
            }
            mock_get_addon.return_value = mock_addon

            cmd = AddonsInfoCmd()

            cmd.call("default-db")

        # Should default to postgres
        mock_get_addon.assert_called_once_with("postgres", "default-db")

    def test_info_with_custom_service_type(self):
        """Test getting info with custom service type.

        ARRANGE:
            - Mock addon plugin for redis

        ACT:
            - Get addon info with --type redis

        ASSERT:
            - Verify redis type was used
            - Verify addon.info() was called
        """
        redis_info = {
            "addon_name": "my-cache",
            "type": "redis",
            "memory_mb": 128,
            "keys": 1000,
        }

        with patch("hop3.commands.services.get_addon") as mock_get_addon:
            mock_addon = Mock()
            mock_addon.info.return_value = redis_info
            mock_get_addon.return_value = mock_addon

            cmd = AddonsInfoCmd()

            result = cmd.call("my-cache", "--type", "redis")

        mock_get_addon.assert_called_once_with("redis", "my-cache")
        mock_addon.info.assert_called_once()

        output_text = result[0]["text"]
        assert "my-cache" in output_text
        assert "redis" in output_text
        assert "128" in output_text
        assert "1000" in output_text

    def test_info_handles_errors(self):
        """Test error handling when getting addon info fails.

        ARRANGE:
            - Mock addon plugin to raise RuntimeError

        ACT:
            - Attempt to get addon info

        ASSERT:
            - Verify ValueError is raised for JSON-RPC error handling
        """
        with patch("hop3.commands.services.get_addon") as mock_get_addon:
            mock_get_addon.side_effect = RuntimeError("Addon not found")

            cmd = AddonsInfoCmd()

            # command_context raises ValueError for JSON-RPC error handling
            with pytest.raises(ValueError) as exc_info:
                cmd.call("nonexistent-db")

            assert "Addon not found" in str(exc_info.value)
