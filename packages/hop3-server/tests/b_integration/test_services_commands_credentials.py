# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for services commands with credential persistence."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from advanced_alchemy.base import BigIntAuditBase
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from hop3.commands.services import (
    AddonsAttachCmd,
    AddonsDestroyCmd,
    AddonsDetachCmd,
)
from hop3.core.credentials import get_credential_encryptor
from hop3.orm import AddonCredential, App, EnvVar
from hop3.orm.repositories import (
    AddonCredentialRepository,
    AppRepository,
    EnvVarRepository,
)


@pytest.fixture
def test_db():
    """Create in-memory test database with all tables."""
    engine = create_engine("sqlite:///:memory:")

    # Create all tables
    BigIntAuditBase.metadata.create_all(engine)

    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    yield session

    session.close()
    engine.dispose()


@pytest.fixture
def app_repo(test_db: Session) -> AppRepository:
    """Create an app repository for testing."""
    return AppRepository(session=test_db)


@pytest.fixture
def addon_credential_repo(test_db: Session) -> AddonCredentialRepository:
    """Create an addon credential repository for testing."""
    return AddonCredentialRepository(session=test_db)


@pytest.fixture
def env_var_repo(test_db: Session) -> EnvVarRepository:
    """Create an env var repository for testing."""
    return EnvVarRepository(session=test_db)


@pytest.fixture
def test_app(test_db):
    """Create a test application."""
    app = App(name="test-app", hostname="test.local", port=8000)
    test_db.add(app)
    test_db.commit()
    return app


@pytest.fixture
def mock_service():
    """Mock service strategy that returns connection details."""
    service = MagicMock()
    service.get_connection_details.return_value = {
        "DATABASE_URL": "postgresql://user:pass@localhost:5432/testdb",
        "DB_USER": "user",
        "DB_PASSWORD": "pass",
        "DB_NAME": "testdb",
    }
    return service


class TestServicesAttachWithCredentials:
    """Test services:attach command stores credentials."""

    def test_attach_stores_credential(
        self,
        test_db,
        test_app,
        mock_service,
        app_repo: AppRepository,
        addon_credential_repo: AddonCredentialRepository,
        env_var_repo: EnvVarRepository,
    ):
        """Test that attaching a service stores encrypted credentials."""
        with patch("hop3.commands.services.get_addon", return_value=mock_service):
            cmd = AddonsAttachCmd(
                app_repo=app_repo,
                addon_credential_repo=addon_credential_repo,
                env_var_repo=env_var_repo,
            )
            result = cmd.call("test-db", "--app", "test-app", "--type", "postgres")

            # Command should succeed
            assert result[0]["t"] == "text"
            assert "attached" in result[0]["text"]

            # Credential should be stored
            credential = (
                test_db
                .query(AddonCredential)
                .filter_by(
                    app_id=test_app.id, addon_type="postgres", addon_name="test-db"
                )
                .one()
            )

            # Should be encrypted
            assert credential.encrypted_data is not None
            assert "pass" not in credential.encrypted_data

            # Should decrypt correctly
            encryptor = get_credential_encryptor()
            decrypted = encryptor.decrypt(credential.encrypted_data)
            assert decrypted["DB_PASSWORD"] == "pass"

    def test_attach_creates_env_vars(
        self,
        test_db,
        test_app,
        mock_service,
        app_repo: AppRepository,
        addon_credential_repo: AddonCredentialRepository,
        env_var_repo: EnvVarRepository,
    ):
        """Test that attaching a service creates environment variables."""
        with patch("hop3.commands.services.get_addon", return_value=mock_service):
            cmd = AddonsAttachCmd(
                app_repo=app_repo,
                addon_credential_repo=addon_credential_repo,
                env_var_repo=env_var_repo,
            )
            cmd.call("test-db", "--app", "test-app", "--type", "postgres")

            # Environment variables should be created
            env_vars = test_db.query(EnvVar).filter_by(app_id=test_app.id).all()
            assert len(env_vars) == 4

            env_var_dict = {var.name: var.value for var in env_vars}
            assert env_var_dict["DB_PASSWORD"] == "pass"
            assert env_var_dict["DB_NAME"] == "testdb"

    def test_attach_twice_updates_credential(
        self,
        test_db,
        test_app,
        mock_service,
        app_repo: AppRepository,
        addon_credential_repo: AddonCredentialRepository,
        env_var_repo: EnvVarRepository,
    ):
        """Test that attaching the same service twice updates the credential."""
        with patch("hop3.commands.services.get_addon", return_value=mock_service):
            cmd = AddonsAttachCmd(
                app_repo=app_repo,
                addon_credential_repo=addon_credential_repo,
                env_var_repo=env_var_repo,
            )

            # First attach
            cmd.call("test-db", "--app", "test-app", "--type", "postgres")

            # Change the password
            mock_service.get_connection_details.return_value["DB_PASSWORD"] = "newpass"

            # Second attach
            cmd.call("test-db", "--app", "test-app", "--type", "postgres")

            # Should still have only one credential
            credentials = (
                test_db
                .query(AddonCredential)
                .filter_by(
                    app_id=test_app.id, addon_type="postgres", addon_name="test-db"
                )
                .all()
            )
            assert len(credentials) == 1

            # Credential should have new password
            encryptor = get_credential_encryptor()
            decrypted = encryptor.decrypt(credentials[0].encrypted_data)
            assert decrypted["DB_PASSWORD"] == "newpass"


class TestServicesDetachWithCredentials:
    """Test services:detach command removes credentials."""

    def test_detach_removes_credential(
        self,
        test_db,
        test_app,
        mock_service,
        app_repo: AppRepository,
        addon_credential_repo: AddonCredentialRepository,
        env_var_repo: EnvVarRepository,
    ):
        """Test that detaching a service removes the stored credential."""
        with patch("hop3.commands.services.get_addon", return_value=mock_service):
            # First attach
            attach_cmd = AddonsAttachCmd(
                app_repo=app_repo,
                addon_credential_repo=addon_credential_repo,
                env_var_repo=env_var_repo,
            )
            attach_cmd.call("test-db", "--app", "test-app", "--type", "postgres")

            # Verify credential exists
            assert test_db.query(AddonCredential).count() == 1

            # Detach
            detach_cmd = AddonsDetachCmd(
                app_repo=app_repo,
                addon_credential_repo=addon_credential_repo,
                env_var_repo=env_var_repo,
            )
            result = detach_cmd.call(
                "test-db", "--app", "test-app", "--type", "postgres"
            )

            # Command should succeed
            assert result[0]["t"] == "text"
            assert "detached" in result[0]["text"]

            # Credential should be removed
            assert test_db.query(AddonCredential).count() == 0

    def test_detach_removes_env_vars(
        self,
        test_db,
        test_app,
        mock_service,
        app_repo: AppRepository,
        addon_credential_repo: AddonCredentialRepository,
        env_var_repo: EnvVarRepository,
    ):
        """Test that detaching a service removes environment variables."""
        with patch("hop3.commands.services.get_addon", return_value=mock_service):
            # First attach
            attach_cmd = AddonsAttachCmd(
                app_repo=app_repo,
                addon_credential_repo=addon_credential_repo,
                env_var_repo=env_var_repo,
            )
            attach_cmd.call("test-db", "--app", "test-app", "--type", "postgres")

            # Verify env vars exist
            assert test_db.query(EnvVar).filter_by(app_id=test_app.id).count() == 4

            # Detach
            detach_cmd = AddonsDetachCmd(
                app_repo=app_repo,
                addon_credential_repo=addon_credential_repo,
                env_var_repo=env_var_repo,
            )
            detach_cmd.call("test-db", "--app", "test-app", "--type", "postgres")

            # Env vars should be removed
            assert test_db.query(EnvVar).filter_by(app_id=test_app.id).count() == 0


class TestServicesDestroyWithCredentials:
    """Test services:destroy command cleans up credentials."""

    def test_destroy_removes_all_credentials(
        self,
        test_db,
        mock_service,
        app_repo: AppRepository,
        addon_credential_repo: AddonCredentialRepository,
        env_var_repo: EnvVarRepository,
    ):
        """Test that destroying a service removes credentials from all apps."""
        with patch("hop3.commands.services.get_addon", return_value=mock_service):
            # Create two apps
            app1 = App(name="app1", hostname="app1.local", port=8001)
            app2 = App(name="app2", hostname="app2.local", port=8002)
            test_db.add(app1)
            test_db.add(app2)
            test_db.commit()

            # Attach service to both apps
            attach_cmd = AddonsAttachCmd(
                app_repo=app_repo,
                addon_credential_repo=addon_credential_repo,
                env_var_repo=env_var_repo,
            )
            attach_cmd.call("shared-db", "--app", "app1", "--type", "postgres")
            attach_cmd.call("shared-db", "--app", "app2", "--type", "postgres")

            # Verify credentials exist
            credentials = (
                test_db
                .query(AddonCredential)
                .filter_by(addon_type="postgres", addon_name="shared-db")
                .all()
            )
            assert len(credentials) == 2

            # Destroy the service
            destroy_cmd = AddonsDestroyCmd(addon_credential_repo=addon_credential_repo)
            result = destroy_cmd.call("shared-db", "--type", "postgres")

            # Command should succeed
            assert result[0]["t"] == "text"
            assert "destroyed" in result[0]["text"]

            # All credentials should be removed
            credentials = (
                test_db
                .query(AddonCredential)
                .filter_by(addon_type="postgres", addon_name="shared-db")
                .all()
            )
            assert len(credentials) == 0


class TestCredentialPersistence:
    """Test that credentials persist across sessions."""

    def test_credentials_survive_session_close(self, test_app, mock_service):
        """Test that credentials persist when database session is closed and reopened."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            engine = create_engine(f"sqlite:///{db_path}")
            BigIntAuditBase.metadata.create_all(engine)

            # Session 1: Create app and attach service
            Session1 = sessionmaker(bind=engine)
            session1 = Session1()

            app = App(name="persist-app", hostname="persist.local", port=8000)
            session1.add(app)
            session1.commit()

            # Create repositories for session1
            app_repo1 = AppRepository(session=session1)
            addon_credential_repo1 = AddonCredentialRepository(session=session1)
            env_var_repo1 = EnvVarRepository(session=session1)

            with patch("hop3.commands.services.get_addon", return_value=mock_service):
                cmd = AddonsAttachCmd(
                    app_repo=app_repo1,
                    addon_credential_repo=addon_credential_repo1,
                    env_var_repo=env_var_repo1,
                )
                cmd.call("persist-db", "--app", "persist-app", "--type", "postgres")

            app_id = app.id
            session1.close()

            # Session 2: Verify credential still exists
            Session2 = sessionmaker(bind=engine)
            session2 = Session2()

            credential = (
                session2
                .query(AddonCredential)
                .filter_by(
                    app_id=app_id, addon_type="postgres", addon_name="persist-db"
                )
                .one()
            )

            # Should still decrypt correctly
            encryptor = get_credential_encryptor()
            decrypted = encryptor.decrypt(credential.encrypted_data)
            assert decrypted["DB_PASSWORD"] == "pass"

            session2.close()
            engine.dispose()
