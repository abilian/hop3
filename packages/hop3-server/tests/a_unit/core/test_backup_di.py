# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for BackupManager DI integration."""

from __future__ import annotations

from hop3.core.backup import BackupManager
from hop3.orm.repositories import (
    AddonCredentialRepository,
    AppRepository,
    BackupRepository,
)


def test_backup_manager_from_container(di_container):
    """Test that BackupManager can be retrieved from DI container."""
    with di_container() as request_container:
        manager = request_container.get(BackupManager)

        assert isinstance(manager, BackupManager)
        assert manager.backup_repo is not None
        assert manager.app_repo is not None
        assert manager.addon_credential_repo is not None


def test_backup_manager_has_real_repositories(di_container):
    """Test that BackupManager gets real repository instances."""
    with di_container() as request_container:
        manager = request_container.get(BackupManager)

        # Verify repositories are real instances
        assert isinstance(manager.backup_repo, BackupRepository)
        assert isinstance(manager.app_repo, AppRepository)
        assert isinstance(manager.addon_credential_repo, AddonCredentialRepository)


def test_backup_manager_repositories_are_fresh_per_request(di_container):
    """Test that each request scope gets fresh repositories."""
    # First request
    with di_container() as request_container1:
        manager1 = request_container1.get(BackupManager)
        repo1 = manager1.backup_repo

    # Second request
    with di_container() as request_container2:
        manager2 = request_container2.get(BackupManager)
        repo2 = manager2.backup_repo

    # Should be different repository instances
    assert repo1 is not repo2
