# Copyright (c) 2025, Abilian SAS
# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Tests for API models."""

from __future__ import annotations

from datetime import datetime, timezone

from hop3_tui.api.models import Addon, App, AppState, Backup, EnvVar, SystemStatus


class TestAppState:
    """Tests for AppState enum."""

    def test_all_states_exist(self):
        """Verify all expected states exist."""
        assert AppState.STOPPED.value == "STOPPED"
        assert AppState.STARTING.value == "STARTING"
        assert AppState.RUNNING.value == "RUNNING"
        assert AppState.STOPPING.value == "STOPPING"
        assert AppState.FAILED.value == "FAILED"

    def test_state_from_string(self):
        """Test creating state from string."""
        assert AppState("RUNNING") == AppState.RUNNING
        assert AppState("STOPPED") == AppState.STOPPED


class TestEnvVar:
    """Tests for EnvVar model."""

    def test_basic_env_var(self):
        """Test creating a basic env var."""
        env = EnvVar(name="DEBUG", value="true")
        assert env.name == "DEBUG"
        assert env.value == "true"
        assert env.is_service_var is False

    def test_service_env_var(self):
        """Test service-generated env var."""
        env = EnvVar(name="DATABASE_URL", value="postgres://...", is_service_var=True)
        assert env.is_service_var is True


class TestApp:
    """Tests for App model."""

    def test_basic_app(self):
        """Test creating a basic app."""
        app = App(name="myapp")
        assert app.name == "myapp"
        assert app.runtime == "unknown"
        assert app.state == AppState.STOPPED
        assert app.port is None
        assert app.workers == 1

    def test_app_with_all_fields(self):
        """Test app with all fields populated."""
        now = datetime.now(timezone.utc)
        app = App(
            name="myapp",
            runtime="uwsgi",
            state=AppState.RUNNING,
            port=8000,
            hostname="myapp.example.com",
            workers=4,
            error_message=None,
            created_at=now,
            updated_at=now,
        )
        assert app.port == 8000
        assert app.hostname == "myapp.example.com"
        assert app.workers == 4

    def test_is_running_property(self):
        """Test is_running property."""
        running_app = App(name="app1", state=AppState.RUNNING)
        stopped_app = App(name="app2", state=AppState.STOPPED)

        assert running_app.is_running is True
        assert stopped_app.is_running is False

    def test_is_transitional_property(self):
        """Test is_transitional property."""
        starting_app = App(name="app1", state=AppState.STARTING)
        stopping_app = App(name="app2", state=AppState.STOPPING)
        running_app = App(name="app3", state=AppState.RUNNING)

        assert starting_app.is_transitional is True
        assert stopping_app.is_transitional is True
        assert running_app.is_transitional is False

    def test_failed_app_with_error(self):
        """Test failed app with error message."""
        app = App(
            name="broken",
            state=AppState.FAILED,
            error_message="Connection refused",
        )
        assert app.state == AppState.FAILED
        assert app.error_message == "Connection refused"


class TestSystemStatus:
    """Tests for SystemStatus model."""

    def test_default_values(self):
        """Test default values."""
        status = SystemStatus()
        assert status.cpu_percent == 0.0
        assert status.memory_percent == 0.0
        assert status.disk_percent == 0.0
        assert status.uptime_seconds == 0
        assert status.hostname == "unknown"

    def test_with_values(self):
        """Test with actual values."""
        status = SystemStatus(
            cpu_percent=45.5,
            memory_percent=62.3,
            disk_percent=80.0,
            uptime_seconds=86400,
            hostname="hop3.dev",
            hop3_version="0.5.0",
            apps_running=5,
            apps_stopped=2,
            apps_failed=1,
        )
        assert status.cpu_percent == 45.5
        assert status.apps_running == 5


class TestAddon:
    """Tests for Addon model."""

    def test_basic_addon(self):
        """Test creating a basic addon."""
        addon = Addon(name="mydb", addon_type="postgresql")
        assert addon.name == "mydb"
        assert addon.addon_type == "postgresql"
        assert addon.app_name is None

    def test_addon_attached_to_app(self):
        """Test addon attached to app."""
        addon = Addon(
            name="mydb",
            addon_type="postgresql",
            app_name="myapp",
        )
        assert addon.app_name == "myapp"


class TestBackup:
    """Tests for Backup model."""

    def test_basic_backup(self):
        """Test creating a basic backup."""
        now = datetime.now(timezone.utc)
        backup = Backup(
            id="20240315_120000",
            app_name="myapp",
            created_at=now,
        )
        assert backup.id == "20240315_120000"
        assert backup.app_name == "myapp"
        assert backup.size_bytes == 0
        assert backup.addons == []

    def test_backup_with_addons(self):
        """Test backup with addons."""
        now = datetime.now(timezone.utc)
        backup = Backup(
            id="20240315_120000",
            app_name="myapp",
            created_at=now,
            size_bytes=1024000,
            addons=["postgresql", "redis"],
        )
        assert backup.size_bytes == 1024000
        assert len(backup.addons) == 2
