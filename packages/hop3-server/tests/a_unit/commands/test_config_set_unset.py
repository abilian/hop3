# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for config:set and config:unset commands."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hop3.commands.config import SetCmd, UnsetCmd
from hop3.orm import App, AppRepository

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def test_config_set_new_variable(db_session: Session, test_app: App):
    """Test setting a new environment variable."""
    cmd = SetCmd(db_session=db_session)
    result = cmd.call("--app", "testapp", "NEW_VAR=new_value")

    # Check result message
    assert any("Updated configuration" in r.get("text", "") for r in result)
    assert any("Set NEW_VAR=new_value" in r.get("text", "") for r in result)

    # Verify it was saved to database
    app_repo = AppRepository(session=db_session)
    app = app_repo.get_one(name="testapp")
    env = app.get_runtime_env()
    assert "NEW_VAR" in env
    assert env["NEW_VAR"] == "new_value"


def test_config_set_update_existing_variable(db_session: Session, test_app: App):
    """Test updating an existing environment variable."""
    cmd = SetCmd(db_session=db_session)
    result = cmd.call("--app", "testapp", "EXISTING_VAR=updated_value")

    # Check result message
    result_text = " ".join(r.get("text", "") for r in result)
    assert "Updated EXISTING_VAR=updated_value" in result_text
    assert "was: old_value" in result_text

    # Verify it was updated in database
    app_repo = AppRepository(session=db_session)
    app = app_repo.get_one(name="testapp")
    env = app.get_runtime_env()
    assert env["EXISTING_VAR"] == "updated_value"


def test_config_set_multiple_variables(db_session: Session, test_app: App):
    """Test setting multiple environment variables at once."""
    cmd = SetCmd(db_session=db_session)
    result = cmd.call("--app", "testapp", "VAR1=value1", "VAR2=value2", "VAR3=value3")

    # Check result messages
    result_text = " ".join(r.get("text", "") for r in result)
    assert "Set VAR1=value1" in result_text
    assert "Set VAR2=value2" in result_text
    assert "Set VAR3=value3" in result_text

    # Verify all were saved to database
    app_repo = AppRepository(session=db_session)
    app = app_repo.get_one(name="testapp")
    env = app.get_runtime_env()
    assert env["VAR1"] == "value1"
    assert env["VAR2"] == "value2"
    assert env["VAR3"] == "value3"


def test_config_set_value_with_equals(db_session: Session, test_app: App):
    """Test setting a variable with an equals sign in the value."""
    cmd = SetCmd(db_session=db_session)
    cmd.call(
        "--app", "testapp", "DATABASE_URL=postgres://user:pass@host/db?param=value"
    )

    # Verify it was saved with the full value including the equals sign
    app_repo = AppRepository(session=db_session)
    app = app_repo.get_one(name="testapp")
    env = app.get_runtime_env()
    assert env["DATABASE_URL"] == "postgres://user:pass@host/db?param=value"


def test_config_set_empty_value(db_session: Session, test_app: App):
    """Test setting a variable to an empty value."""
    cmd = SetCmd(db_session=db_session)
    cmd.call("--app", "testapp", "EMPTY_VAR=")

    # Verify it was saved with empty string value
    app_repo = AppRepository(session=db_session)
    app = app_repo.get_one(name="testapp")
    env = app.get_runtime_env()
    assert "EMPTY_VAR" in env
    assert env["EMPTY_VAR"] == ""


def test_config_set_invalid_format(db_session: Session, test_app: App):
    """Test error handling for invalid setting format."""
    cmd = SetCmd(db_session=db_session)
    result = cmd.call("--app", "testapp", "INVALID_FORMAT")

    # Should return error
    assert any(r.get("t") == "error" for r in result)
    assert any("Invalid setting format" in r.get("text", "") for r in result)


def test_config_set_mixed_valid_invalid(db_session: Session, test_app: App):
    """Test setting with mix of valid and invalid formats."""
    cmd = SetCmd(db_session=db_session)
    result = cmd.call("--app", "testapp", "VALID=value", "INVALID", "VALID2=value2")

    # Should return error for invalid format
    assert any(r.get("t") == "error" for r in result)


def test_config_set_no_arguments(db_session: Session, test_app: App):
    """Test config:set with no arguments."""
    cmd = SetCmd(db_session=db_session)
    result = cmd.call("--app", "testapp")

    # Should return usage message
    assert any("Usage:" in r.get("text", "") for r in result)


def test_config_set_nonexistent_app(db_session: Session):
    """Test config:set for non-existent app."""
    cmd = SetCmd(db_session=db_session)

    with pytest.raises(ValueError, match="App 'nonexistent' not found"):
        cmd.call("--app", "nonexistent", "VAR=value")


def test_config_unset_existing_variable(db_session: Session, test_app: App):
    """Test unsetting an existing environment variable."""
    cmd = UnsetCmd(db_session=db_session)
    result = cmd.call("--app", "testapp", "EXISTING_VAR")

    # Check result message
    assert any("Removed configuration" in r.get("text", "") for r in result)
    assert any("EXISTING_VAR" in r.get("text", "") for r in result)

    # Verify removed from database
    app = db_session.query(App).filter_by(name="testapp").first()
    assert app is not None
    env = app.get_runtime_env()
    assert "EXISTING_VAR" not in env


def test_config_unset_multiple_variables(db_session: Session, test_app: App):
    """Test unsetting multiple environment variables."""
    cmd = UnsetCmd(db_session=db_session)
    result = cmd.call("--app", "testapp", "EXISTING_VAR", "DEBUG")

    # Check result messages
    result_text = " ".join(r.get("text", "") for r in result)
    assert "EXISTING_VAR" in result_text
    assert "DEBUG" in result_text

    # Verify removed from database
    app = db_session.query(App).filter_by(name="testapp").first()
    assert app is not None
    env = app.get_runtime_env()
    assert "EXISTING_VAR" not in env
    assert "DEBUG" not in env


def test_config_unset_nonexistent_variable(db_session: Session, test_app: App):
    """Test unsetting a non-existent variable."""
    cmd = UnsetCmd(db_session=db_session)
    result = cmd.call("--app", "testapp", "NONEXISTENT_VAR")

    # Should report not found
    result_text = " ".join(r.get("text", "") for r in result)
    assert "Not found" in result_text
    assert "NONEXISTENT_VAR" in result_text


def test_config_unset_mixed_existing_nonexistent(db_session: Session, test_app: App):
    """Test unsetting mix of existing and non-existent variables."""
    cmd = UnsetCmd(db_session=db_session)
    result = cmd.call("--app", "testapp", "EXISTING_VAR", "NONEXISTENT", "DEBUG")

    result_text = " ".join(r.get("text", "") for r in result)

    # Should show removed variables
    assert "Removed configuration" in result_text
    assert "EXISTING_VAR" in result_text
    assert "DEBUG" in result_text

    # Should also show not found
    assert "Not found" in result_text
    assert "NONEXISTENT" in result_text

    # Verify database state
    app = db_session.query(App).filter_by(name="testapp").first()
    assert app is not None
    env = app.get_runtime_env()
    assert "EXISTING_VAR" not in env
    assert "DEBUG" not in env


def test_config_unset_no_arguments(db_session: Session, test_app: App):
    """Test config:unset with no arguments."""
    cmd = UnsetCmd(db_session=db_session)
    result = cmd.call("--app", "testapp")

    # Should return usage message
    assert any("Usage:" in r.get("text", "") for r in result)


def test_config_unset_nonexistent_app(db_session: Session):
    """Test config:unset for non-existent app."""
    cmd = UnsetCmd(db_session=db_session)

    with pytest.raises(ValueError, match="App 'nonexistent' not found"):
        cmd.call("--app", "nonexistent", "VAR")


def test_config_set_then_unset(db_session: Session, test_app: App):
    """Test setting and then unsetting a variable."""
    # Set a new variable
    set_cmd = SetCmd(db_session=db_session)
    set_cmd.call("--app", "testapp", "TEMP_VAR=temp_value")

    # Verify it was set
    app = db_session.query(App).filter_by(name="testapp").first()
    assert app is not None
    env = app.get_runtime_env()
    assert "TEMP_VAR" in env
    assert env["TEMP_VAR"] == "temp_value"

    # Unset it
    unset_cmd = UnsetCmd(db_session=db_session)
    unset_cmd.call("--app", "testapp", "TEMP_VAR")

    # Verify it was removed
    app = db_session.query(App).filter_by(name="testapp").first()
    assert app is not None
    env = app.get_runtime_env()
    assert "TEMP_VAR" not in env


def test_config_set_restart_reminder(db_session: Session, test_app: App):
    """Test that config:set reminds user to restart app."""
    cmd = SetCmd(db_session=db_session)
    result = cmd.call("--app", "testapp", "VAR=value")

    # The restart reminder is a `hint` item (rendered client-side with the
    # user's own --context/--app): "restart" rides its `command`, "apply
    # changes" its `message`.
    result_text = " ".join(
        f"{r.get('text', '')} {r.get('message', '')} {r.get('command', '')}"
        for r in result
    ).lower()
    assert "restart" in result_text
    assert "apply changes" in result_text


def test_config_unset_restart_reminder(db_session: Session, test_app: App):
    """Test that config:unset reminds user to restart app."""
    cmd = UnsetCmd(db_session=db_session)
    result = cmd.call("--app", "testapp", "EXISTING_VAR")

    # The restart reminder is a `hint` item (rendered client-side with the
    # user's own --context/--app): "restart" rides its `command`, "apply
    # changes" its `message`.
    result_text = " ".join(
        f"{r.get('text', '')} {r.get('message', '')} {r.get('command', '')}"
        for r in result
    ).lower()
    assert "restart" in result_text
    assert "apply changes" in result_text
