# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for BackupManager DI integration."""

from __future__ import annotations

from unittest.mock import Mock

from dishka import Provider, Scope, make_container, provide
from sqlalchemy.orm import Session

from hop3.core.backup import BackupManager


def test_backup_manager_provided_by_di():
    """Test that BackupManager can be provided by DI container with REQUEST scope."""
    # This test demonstrates how BackupManager would work when DatabaseProvider is available
    # Note: BackupManager provider is currently commented out in HopServicesProvider

    class MockDatabaseProvider(Provider):
        scope = Scope.REQUEST

        @provide
        def get_session(self) -> Session:
            return Mock(spec=Session)

        @provide
        def get_backup_manager(self, db_session: Session) -> BackupManager:
            return BackupManager(db_session)

    container = make_container(MockDatabaseProvider())

    try:
        # Use () context manager to get REQUEST scope
        with container() as request_container:
            backup_manager = request_container.get(BackupManager)

            assert backup_manager is not None
            assert isinstance(backup_manager, BackupManager)
            assert backup_manager.db_session is not None
    finally:
        container.close()


def test_backup_manager_uses_injected_session():
    """Test that BackupManager uses the injected session."""

    class MockDatabaseProvider(Provider):
        scope = Scope.REQUEST

        @provide
        def get_session(self) -> Session:
            mock_session = Mock(spec=Session)
            mock_session.test_marker = "injected"
            return mock_session

        @provide
        def get_backup_manager(self, db_session: Session) -> BackupManager:
            return BackupManager(db_session)

    container = make_container(MockDatabaseProvider())

    try:
        with container() as request_container:
            manager = request_container.get(BackupManager)

            # Verify it uses the injected session
            assert manager.db_session is not None
            assert hasattr(manager.db_session, "test_marker")
            assert manager.db_session.test_marker == "injected"
    finally:
        container.close()


def test_backup_manager_with_mock_session():
    """Test BackupManager creation with mock session."""
    mock_session = Mock(spec=Session)
    manager = BackupManager(mock_session)

    assert manager.db_session is mock_session


def test_backup_manager_mock_provider():
    """Test BackupManager with fully mocked provider."""

    class MockBackupProvider(Provider):
        scope = Scope.REQUEST

        @provide
        def get_session(self) -> Session:
            return Mock(spec=Session)

        @provide
        def get_backup_manager(self, db_session: Session) -> BackupManager:
            mock_manager = Mock(spec=BackupManager)
            mock_manager.db_session = db_session
            return mock_manager

    container = make_container(MockBackupProvider())

    try:
        with container() as request_container:
            manager = request_container.get(BackupManager)

            assert manager is not None
            assert hasattr(manager, "db_session")
            assert manager.db_session is not None
    finally:
        container.close()
