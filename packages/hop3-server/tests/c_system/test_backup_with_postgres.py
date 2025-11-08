# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""System tests for backup with PostgreSQL service.

Note: These tests have been implemented as E2E tests in
packages/hop3-server/tests/d_e2e/test_backup.py instead.

The E2E test infrastructure provides better isolation and more comprehensive
testing capabilities for backup/restore scenarios with real services.

See:
- test_backup_simple_app: Basic backup/restore without services
- test_backup_includes_env_vars: Verify environment variables are backed up
- test_restore_simple_app: Test restore functionality
- test_restore_to_different_app_name: Test cloning via restore
- test_list_and_filter_backups: Test backup listing and filtering
- test_delete_backup: Test backup deletion
- test_backup_app_with_postgres: Backup with PostgreSQL (pending PostgreSQL support in E2E)
- test_restore_app_with_postgres: Restore with PostgreSQL (pending PostgreSQL support in E2E)
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason="Backup tests have been implemented as E2E tests in d_e2e/test_backup.py. "
    "System tests are not needed as the E2E infrastructure provides better coverage."
)


class TestBackupWithPostgreSQL:
    """Test backup and restore with PostgreSQL service.

    These tests are no longer implemented here - see d_e2e/test_backup.py instead.
    """

    def test_backup_includes_postgres_data(self):
        """Test that backup includes PostgreSQL database dump."""
        # Implemented in d_e2e/test_backup.py::TestBackupRestoreE2E::test_backup_app_with_postgres

    def test_restore_postgres_data(self):
        """Test that restore recreates PostgreSQL database."""
        # Implemented in d_e2e/test_backup.py::TestBackupRestoreE2E::test_restore_app_with_postgres

    def test_backup_restore_roundtrip(self):
        """Test full backup and restore cycle with PostgreSQL."""
        # Implemented in d_e2e/test_backup.py::TestBackupRestoreE2E::test_restore_app_with_postgres
