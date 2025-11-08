# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""System tests for backup with PostgreSQL service.

These tests verify backup and restore functionality with real PostgreSQL
databases in a Docker environment.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason="System tests require Docker and PostgreSQL - run manually"
)


class TestBackupWithPostgreSQL:
    """Test backup and restore with PostgreSQL service."""

    def test_backup_includes_postgres_data(self):
        """Test that backup includes PostgreSQL database dump."""
        # This would require a full Docker setup with PostgreSQL
        # Marking as skip for now - will be implemented in E2E tests

    def test_restore_postgres_data(self):
        """Test that restore recreates PostgreSQL database."""
        # This would require a full Docker setup with PostgreSQL
        # Marking as skip for now - will be implemented in E2E tests

    def test_backup_restore_roundtrip(self):
        """Test full backup and restore cycle with PostgreSQL."""
        # This would require a full Docker setup with PostgreSQL
        # Marking as skip for now - will be implemented in E2E tests


# These tests are placeholders for now. Full system tests will be
# implemented as part of the E2E test suite in d_e2e/test_backup.py
# where we can use Docker containers to set up real PostgreSQL instances.
