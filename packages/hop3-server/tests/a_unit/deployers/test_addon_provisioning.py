# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for addon provisioning during deployment."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from hop3.deployers.addon_provisioning import provision_addons
from hop3.deployers.env_provisioning import set_default_env_vars, set_env_vars


@pytest.fixture
def mock_app():
    """Create a mock app for testing."""
    app = MagicMock()
    app.id = 1
    app.name = "test-app"
    app.env_vars = []
    return app


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    session = MagicMock()
    session.scalars.return_value.first.return_value = None
    return session


class TestSetEnvVars:
    """Tests for set_env_vars function."""

    def test_set_new_env_vars(self, mock_app, mock_db_session):
        """Test setting new environment variables."""
        env_vars = {
            "DATABASE_URL": "postgres://localhost/db",
            "REDIS_URL": "redis://localhost:6379",
        }

        set_env_vars(mock_app, env_vars, mock_db_session)

        # Should have added 2 new env vars
        assert len(mock_app.env_vars) == 2
        assert mock_db_session.add.call_count == 2

    def test_set_updates_existing_env_var(self, mock_app, mock_db_session):
        """Test updating existing environment variable."""
        # Simulate existing env var
        existing_var = MagicMock()
        existing_var.name = "DATABASE_URL"
        existing_var.value = "old_value"
        mock_app.env_vars = [existing_var]

        env_vars = {"DATABASE_URL": "new_value"}

        set_env_vars(mock_app, env_vars, mock_db_session)

        # Should have updated the existing var
        assert existing_var.value == "new_value"
        # Should not have added new env vars
        assert mock_db_session.add.call_count == 0

    def test_set_empty_env_vars(self, mock_app, mock_db_session):
        """Test setting empty env vars dict does nothing."""
        set_env_vars(mock_app, {}, mock_db_session)

        assert mock_db_session.add.call_count == 0
        assert len(mock_app.env_vars) == 0

    def test_defaults_only_skips_existing(self, mock_app, mock_db_session):
        """Test that defaults_only=True skips existing variables."""
        existing_var = MagicMock()
        existing_var.name = "SECRET_KEY"
        existing_var.value = "user-set-value"
        mock_app.env_vars = [existing_var]

        env_vars = {"SECRET_KEY": "default-value"}

        count, skipped = set_env_vars(
            mock_app, env_vars, mock_db_session, defaults_only=True
        )

        # Should NOT have updated the existing var
        assert existing_var.value == "user-set-value"
        assert count == 0
        assert skipped == ["SECRET_KEY"]


class TestSetDefaultEnvVars:
    """Tests for set_default_env_vars function."""

    def test_set_default_env_vars(self, mock_app, mock_db_session):
        """Test setting default env vars from config."""
        env_config = {
            "DEBUG": "false",
            "SECRET_KEY": "mysecret",
        }

        set_default_env_vars(mock_app, env_config, mock_db_session)

        assert len(mock_app.env_vars) == 2

    def test_set_default_env_vars_empty(self, mock_app, mock_db_session):
        """Test that empty config does nothing."""
        set_default_env_vars(mock_app, {}, mock_db_session)

        assert len(mock_app.env_vars) == 0


class TestProvisionAddons:
    """Tests for provision_addons function."""

    def test_provision_addons_empty_list(self, mock_app, mock_db_session):
        """Test that empty addon list does nothing."""
        provision_addons(mock_app, [], mock_db_session)

        # No addon calls should be made
        mock_db_session.add.assert_not_called()

    def test_provision_addons_aborts_when_no_type_and_no_name(
        self, mock_app, mock_db_session
    ):
        """A declared addon with neither 'type' nor 'name' must fail loudly.

        Silently skipping it would let the app deploy without its backing
        service and then fail confusingly downstream (e.g. a migration with no
        database).
        """
        from hop3.lib import Abort  # noqa: PLC0415

        with pytest.raises(Abort):
            provision_addons(mock_app, [{"plan": "standard"}], mock_db_session)

    @patch("hop3.deployers.addon_provisioning.get_addon")
    @patch("hop3.deployers.addon_provisioning.get_credential_encryptor")
    def test_provision_treats_legacy_name_as_type(
        self, mock_encryptor, mock_get_addon, mock_app, mock_db_session
    ):
        """The deprecated [[provider]] / legacy [[addons]] form put the type in
        'name' with no separate instance name. Honor it instead of dropping it.
        """
        mock_addon = MagicMock()
        mock_addon.get_connection_details.return_value = {"DATABASE_URL": "x"}
        mock_get_addon.return_value = mock_addon
        mock_encryptor.return_value.encrypt.return_value = b"encrypted"

        # `name = "postgres"` with no `type` (e.g. [[provider]] name = "postgres")
        provision_addons(mock_app, [{"name": "postgres"}], mock_db_session)

        # 'postgres' is used as the type; the instance name is auto-generated.
        mock_get_addon.assert_called_with("postgres", "test-app-postgres")

    @patch("hop3.deployers.addon_provisioning.get_addon")
    @patch("hop3.deployers.addon_provisioning.get_credential_encryptor")
    def test_provision_creates_addon(
        self, mock_encryptor, mock_get_addon, mock_app, mock_db_session
    ):
        """Test that addon is created and attached."""
        # Setup mocks
        mock_addon = MagicMock()
        mock_addon.get_connection_details.return_value = {
            "DATABASE_URL": "postgres://localhost/db"
        }
        mock_get_addon.return_value = mock_addon
        mock_encryptor.return_value.encrypt.return_value = b"encrypted"

        addon_configs = [{"type": "postgres"}]

        provision_addons(mock_app, addon_configs, mock_db_session)

        # Should have called create (it's idempotent)
        mock_addon.create.assert_called_once()
        # Should have stored credential
        assert mock_db_session.add.call_count >= 1

    @patch("hop3.deployers.addon_provisioning.AddonCredentialRepository")
    @patch("hop3.deployers.addon_provisioning.get_addon")
    @patch("hop3.deployers.addon_provisioning.get_credential_encryptor")
    def test_provision_updates_existing_credential(
        self, mock_encryptor, mock_get_addon, mock_repo_class, mock_app, mock_db_session
    ):
        """Test that existing credential is updated with new connection details."""
        # Setup mocks
        mock_addon = MagicMock()
        mock_addon.get_connection_details.return_value = {
            "DATABASE_URL": "postgres://localhost/db"
        }
        mock_get_addon.return_value = mock_addon
        mock_encryptor.return_value.encrypt.return_value = b"encrypted"

        # Simulate addon already attached - mock the repository
        existing_credential = MagicMock()
        mock_repo = MagicMock()
        mock_repo.get_by_app_addon.return_value = existing_credential
        mock_repo_class.return_value = mock_repo

        addon_configs = [{"type": "postgres"}]

        provision_addons(mock_app, addon_configs, mock_db_session)

        # Should still call create (it's idempotent)
        mock_addon.create.assert_called_once()
        # Should update existing credential, not add new one
        assert existing_credential.encrypted_data == b"encrypted"

    @patch("hop3.deployers.addon_provisioning.get_addon")
    def test_provision_handles_unknown_addon_type(
        self, mock_get_addon, mock_app, mock_db_session
    ):
        """Test that unknown addon types are handled gracefully."""
        mock_get_addon.side_effect = RuntimeError("Unknown addon type: foobar")

        addon_configs = [{"type": "foobar"}]

        # Should not raise, just log warning
        provision_addons(mock_app, addon_configs, mock_db_session)

    @patch("hop3.deployers.addon_provisioning.get_addon")
    @patch("hop3.deployers.addon_provisioning.get_credential_encryptor")
    def test_provision_uses_custom_addon_name(
        self, mock_encryptor, mock_get_addon, mock_app, mock_db_session
    ):
        """Test that custom addon name is used when specified."""
        mock_addon = MagicMock()
        mock_addon.info.side_effect = Exception("Not found")
        mock_addon.get_connection_details.return_value = {"DATABASE_URL": "test"}
        mock_get_addon.return_value = mock_addon
        mock_encryptor.return_value.encrypt.return_value = b"encrypted"

        addon_configs = [{"type": "postgres", "name": "shared-db"}]

        provision_addons(mock_app, addon_configs, mock_db_session)

        # Should have called get_addon with custom name
        mock_get_addon.assert_called_with("postgres", "shared-db")

    @patch("hop3.deployers.addon_provisioning.get_addon")
    @patch("hop3.deployers.addon_provisioning.get_credential_encryptor")
    def test_provision_uses_default_addon_name(
        self, mock_encryptor, mock_get_addon, mock_app, mock_db_session
    ):
        """Test that default addon name is app_name-addon_type."""
        mock_addon = MagicMock()
        mock_addon.info.side_effect = Exception("Not found")
        mock_addon.get_connection_details.return_value = {"DATABASE_URL": "test"}
        mock_get_addon.return_value = mock_addon
        mock_encryptor.return_value.encrypt.return_value = b"encrypted"

        addon_configs = [{"type": "postgres"}]  # No custom name

        provision_addons(mock_app, addon_configs, mock_db_session)

        # Should have called get_addon with default name: app_name-addon_type
        mock_get_addon.assert_called_with("postgres", "test-app-postgres")
