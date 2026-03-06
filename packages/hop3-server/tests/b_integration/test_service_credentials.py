# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for service credential persistence."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from advanced_alchemy.base import BigIntAuditBase
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from hop3.core.credentials import get_credential_encryptor
from hop3.orm import AddonCredential, App


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
def test_app(test_db):
    """Create a test application."""
    app = App(name="test-app", hostname="test.local", port=8000)
    test_db.add(app)
    test_db.commit()
    return app


class TestAddonCredentialModel:
    """Test AddonCredential ORM model."""

    def test_create_credential(self, test_db, test_app):
        """Test creating a service credential."""
        encryptor = get_credential_encryptor()

        credential_data = {
            "username": "test_user",
            "password": "secret123",
            "database": "test_db",
        }

        credential = AddonCredential(
            app_id=test_app.id,
            addon_type="postgresql",
            addon_name="test-db",
            encrypted_data=encryptor.encrypt(credential_data),
        )

        test_db.add(credential)
        test_db.commit()

        # Verify it was created
        assert credential.id is not None
        assert credential.app_id == test_app.id
        assert credential.addon_type == "postgresql"
        assert credential.addon_name == "test-db"

    def test_retrieve_and_decrypt_credential(self, test_db, test_app):
        """Test retrieving and decrypting stored credentials."""
        encryptor = get_credential_encryptor()

        original_data = {
            "username": "myuser",
            "password": "mypassword",
            "host": "localhost",
            "port": 5432,
        }

        # Store credential
        credential = AddonCredential(
            app_id=test_app.id,
            addon_type="postgresql",
            addon_name="my-db",
            encrypted_data=encryptor.encrypt(original_data),
        )
        test_db.add(credential)
        test_db.commit()

        # Retrieve credential
        retrieved = (
            test_db
            .query(AddonCredential)
            .filter_by(app_id=test_app.id, addon_type="postgresql", addon_name="my-db")
            .one()
        )

        # Decrypt and verify
        decrypted_data = encryptor.decrypt(retrieved.encrypted_data)
        assert decrypted_data == original_data

    def test_unique_constraint(self, test_db, test_app):
        """Test unique constraint on (app_id, service_type, addon_name)."""
        encryptor = get_credential_encryptor()

        data = {"password": "secret"}

        # Create first credential
        cred1 = AddonCredential(
            app_id=test_app.id,
            addon_type="postgresql",
            addon_name="db1",
            encrypted_data=encryptor.encrypt(data),
        )
        test_db.add(cred1)
        test_db.commit()

        # Try to create duplicate
        cred2 = AddonCredential(
            app_id=test_app.id,
            addon_type="postgresql",
            addon_name="db1",  # Same name
            encrypted_data=encryptor.encrypt(data),
        )
        test_db.add(cred2)

        # Should raise integrity error
        with pytest.raises(IntegrityError):
            test_db.commit()

        test_db.rollback()

    def test_cascade_delete_with_app(self, test_db, test_app):
        """Test that credentials are deleted when app is deleted."""
        encryptor = get_credential_encryptor()

        # Create multiple credentials for the app
        for i in range(3):
            cred = AddonCredential(
                app_id=test_app.id,
                addon_type="postgresql",
                addon_name=f"db{i}",
                encrypted_data=encryptor.encrypt({"password": f"pass{i}"}),
            )
            test_db.add(cred)
        test_db.commit()

        # Verify credentials exist
        count = test_db.query(AddonCredential).filter_by(app_id=test_app.id).count()
        assert count == 3

        # Delete the app
        test_db.delete(test_app)
        test_db.commit()

        # Verify credentials are gone (cascade delete)
        count = test_db.query(AddonCredential).filter_by(app_id=test_app.id).count()
        assert count == 0

    def test_multiple_services_per_app(self, test_db, test_app):
        """Test storing multiple service types for one app."""
        encryptor = get_credential_encryptor()

        # PostgreSQL credential
        postgres_cred = AddonCredential(
            app_id=test_app.id,
            addon_type="postgresql",
            addon_name="main-db",
            encrypted_data=encryptor.encrypt({
                "username": "pguser",
                "password": "pgpass",
            }),
        )

        # Redis credential
        redis_cred = AddonCredential(
            app_id=test_app.id,
            addon_type="redis",
            addon_name="cache",
            encrypted_data=encryptor.encrypt({"password": "redispass"}),
        )

        test_db.add(postgres_cred)
        test_db.add(redis_cred)
        test_db.commit()

        # Retrieve and verify both
        postgres_retrieved = (
            test_db
            .query(AddonCredential)
            .filter_by(app_id=test_app.id, addon_type="postgresql")
            .one()
        )
        redis_retrieved = (
            test_db
            .query(AddonCredential)
            .filter_by(app_id=test_app.id, addon_type="redis")
            .one()
        )

        assert (
            encryptor.decrypt(postgres_retrieved.encrypted_data)["username"] == "pguser"
        )
        assert (
            encryptor.decrypt(redis_retrieved.encrypted_data)["password"] == "redispass"
        )

    def test_app_relationship(self, test_db, test_app):
        """Test the relationship between App and AddonCredential."""
        encryptor = get_credential_encryptor()

        # Create credential
        cred = AddonCredential(
            app_id=test_app.id,
            addon_type="postgresql",
            addon_name="test-db",
            encrypted_data=encryptor.encrypt({"password": "test"}),
        )
        test_db.add(cred)
        test_db.commit()

        # Refresh app to load relationships
        test_db.refresh(test_app)

        # Access credentials through app relationship
        assert len(test_app.addon_credentials) == 1
        assert test_app.addon_credentials[0].addon_name == "test-db"

    def test_credential_persistence_across_sessions(self, test_app):
        """Test that credentials persist across database sessions."""
        # Use a real SQLite file for this test
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            engine = create_engine(f"sqlite:///{db_path}")
            BigIntAuditBase.metadata.create_all(engine)

            encryptor = get_credential_encryptor()
            credential_data = {"username": "user", "password": "pass"}

            # Session 1: Create app and credential
            Session1 = sessionmaker(bind=engine)
            session1 = Session1()

            app = App(name="persist-test", hostname="test.local", port=8000)
            session1.add(app)
            session1.commit()

            cred = AddonCredential(
                app_id=app.id,
                addon_type="postgresql",
                addon_name="persist-db",
                encrypted_data=encryptor.encrypt(credential_data),
            )
            session1.add(cred)
            session1.commit()

            app_id = app.id
            session1.close()

            # Session 2: Retrieve and verify
            Session2 = sessionmaker(bind=engine)
            session2 = Session2()

            retrieved_cred = (
                session2
                .query(AddonCredential)
                .filter_by(app_id=app_id, addon_name="persist-db")
                .one()
            )

            decrypted = encryptor.decrypt(retrieved_cred.encrypted_data)
            assert decrypted == credential_data

            session2.close()
            engine.dispose()

    def test_encrypted_data_not_readable_in_db(self, test_db, test_app):
        """Test that sensitive data is not readable in raw database."""
        encryptor = get_credential_encryptor()

        sensitive_password = "SuperSecretPassword123!"
        credential_data = {"password": sensitive_password}

        cred = AddonCredential(
            app_id=test_app.id,
            addon_type="postgresql",
            addon_name="secure-db",
            encrypted_data=encryptor.encrypt(credential_data),
        )
        test_db.add(cred)
        test_db.commit()

        # Verify password is not in plaintext in encrypted_data
        assert sensitive_password not in cred.encrypted_data
        assert "password" not in cred.encrypted_data

        # But can be decrypted correctly
        decrypted = encryptor.decrypt(cred.encrypted_data)
        assert decrypted["password"] == sensitive_password
