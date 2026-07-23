# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for `hop3 domains` CLI commands."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hop3.commands._helpers import check_hostname_conflict, parse_hostname_string
from hop3.commands.domains import (
    AddCmd,
    ClearCmd,
    ListCmd,
    RemoveCmd,
    SetCmd,
)
from hop3.orm import App, AppRepository, EnvVar

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _host_name(db_session: Session, app_name: str = "testapp") -> str | None:
    app = AppRepository(session=db_session).get_one(name=app_name)
    return app.get_runtime_env().get("HOST_NAME")


def _texts(result):
    return " ".join(r.get("text", "") for r in result)


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def test_list_empty(db_session: Session, test_app: App):
    result = ListCmd(db_session=db_session).call("--app", "testapp")
    assert "No domains set" in _texts(result)


def test_list_shows_hosts(db_session: Session, test_app: App):
    test_app.env_vars.append(
        EnvVar(name="HOST_NAME", value="a.com www.a.com", app=test_app)
    )
    db_session.commit()

    result = ListCmd(db_session=db_session).call("--app", "testapp")
    text = _texts(result)
    # Plain-text rendering of the table may not include host strings; check
    # the structured row payload instead.
    rows = next(r for r in result if r.get("t") == "table")["rows"]
    flat = [cell for row in rows for cell in row]
    assert "a.com" in flat
    assert "www.a.com" in flat
    assert "testapp" in text


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------


def test_add_to_empty(db_session: Session, test_app: App):
    AddCmd(db_session=db_session).call(
        "--app", "testapp", "example.com", "www.example.com"
    )
    assert parse_hostname_string(_host_name(db_session)) == [
        "example.com",
        "www.example.com",
    ]


def test_add_is_union(db_session: Session, test_app: App):
    test_app.env_vars.append(EnvVar(name="HOST_NAME", value="a.com", app=test_app))
    db_session.commit()

    AddCmd(db_session=db_session).call("--app", "testapp", "b.com", "a.com")
    # Order: existing first, then new not-already-present (a.com was a dup)
    assert parse_hostname_string(_host_name(db_session)) == ["a.com", "b.com"]


def test_add_rejects_invalid_atomic(db_session: Session, test_app: App):
    """One invalid host aborts the whole operation."""
    result = AddCmd(db_session=db_session).call(
        "--app", "testapp", "valid.com", "not valid host"
    )
    assert any(r.get("t") == "error" for r in result)
    # Nothing should have been written
    assert _host_name(db_session) is None


def test_add_rejects_catch_all_with_other(db_session: Session, test_app: App):
    test_app.env_vars.append(EnvVar(name="HOST_NAME", value="a.com", app=test_app))
    db_session.commit()

    result = AddCmd(db_session=db_session).call("--app", "testapp", "_")
    assert any(r.get("t") == "error" for r in result)
    assert _host_name(db_session) == "a.com"


def test_add_conflict_with_other_app(db_session: Session, test_app: App):
    # Set up a second app holding example.com
    other = App(name="otherapp")
    other.env_vars = [EnvVar(name="HOST_NAME", value="example.com", app=other)]
    AppRepository(session=db_session).add(other, auto_commit=True)

    result = AddCmd(db_session=db_session).call("--app", "testapp", "example.com")
    text = _texts(result)
    assert any(r.get("t") == "error" for r in result)
    assert "otherapp" in text
    assert "example.com" in text
    # testapp must remain unchanged (no HOST_NAME set)
    assert _host_name(db_session) is None


def test_add_noop_when_all_present(db_session: Session, test_app: App):
    test_app.env_vars.append(
        EnvVar(name="HOST_NAME", value="a.com b.com", app=test_app)
    )
    db_session.commit()

    result = AddCmd(db_session=db_session).call("--app", "testapp", "a.com", "b.com")
    assert "already set" in _texts(result)


# ---------------------------------------------------------------------------
# remove
# ---------------------------------------------------------------------------


def test_remove_existing(db_session: Session, test_app: App):
    test_app.env_vars.append(
        EnvVar(name="HOST_NAME", value="a.com b.com c.com", app=test_app)
    )
    db_session.commit()

    RemoveCmd(db_session=db_session).call("--app", "testapp", "b.com")
    assert parse_hostname_string(_host_name(db_session)) == ["a.com", "c.com"]


def test_remove_errors_when_absent_atomic(db_session: Session, test_app: App):
    test_app.env_vars.append(EnvVar(name="HOST_NAME", value="a.com", app=test_app))
    db_session.commit()

    result = RemoveCmd(db_session=db_session).call(
        "--app", "testapp", "a.com", "missing.com"
    )
    assert any(r.get("t") == "error" for r in result)
    # Nothing removed — the present host must remain
    assert parse_hostname_string(_host_name(db_session)) == ["a.com"]


# ---------------------------------------------------------------------------
# set
# ---------------------------------------------------------------------------


def test_set_replaces_full_list(db_session: Session, test_app: App):
    test_app.env_vars.append(EnvVar(name="HOST_NAME", value="old.com", app=test_app))
    db_session.commit()

    SetCmd(db_session=db_session).call("--app", "testapp", "new.com", "www.new.com")
    assert parse_hostname_string(_host_name(db_session)) == [
        "new.com",
        "www.new.com",
    ]


def test_set_rejects_invalid_atomic(db_session: Session, test_app: App):
    test_app.env_vars.append(EnvVar(name="HOST_NAME", value="old.com", app=test_app))
    db_session.commit()

    result = SetCmd(db_session=db_session).call(
        "--app", "testapp", "ok.com", "not valid"
    )
    assert any(r.get("t") == "error" for r in result)
    # Old value untouched
    assert _host_name(db_session) == "old.com"


def test_set_conflict_with_other_app(db_session: Session, test_app: App):
    other = App(name="otherapp")
    other.env_vars = [EnvVar(name="HOST_NAME", value="taken.com", app=other)]
    AppRepository(session=db_session).add(other, auto_commit=True)

    result = SetCmd(db_session=db_session).call("--app", "testapp", "taken.com")
    assert any(r.get("t") == "error" for r in result)
    assert _host_name(db_session) is None


# ---------------------------------------------------------------------------
# clear
# ---------------------------------------------------------------------------


def test_clear_unsets(db_session: Session, test_app: App):
    test_app.env_vars.append(
        EnvVar(name="HOST_NAME", value="a.com b.com", app=test_app)
    )
    db_session.commit()

    ClearCmd(db_session=db_session).call("--app", "testapp")
    assert _host_name(db_session) is None


def test_clear_noop_when_empty(db_session: Session, test_app: App):
    result = ClearCmd(db_session=db_session).call("--app", "testapp")
    assert "No domains set" in _texts(result)


# ---------------------------------------------------------------------------
# regression: _check_hostname_conflict fix
# ---------------------------------------------------------------------------


def test_conflict_detection_handles_space_separated_storage(
    db_session: Session, test_app: App
):
    """
    Regression: the canonical on-disk form is space-separated. The old
    implementation only split on commas, so conflicts against deployed apps
    (where proxies normalize to spaces) were silently missed.
    """
    other = App(name="otherapp")
    other.env_vars = [
        EnvVar(name="HOST_NAME", value="one.com two.com three.com", app=other)
    ]
    AppRepository(session=db_session).add(other, auto_commit=True)

    conflict = check_hostname_conflict(db_session, "testapp", ["two.com"])
    assert conflict == ("otherapp", "two.com")


def test_conflict_detection_handles_comma_separated_storage(
    db_session: Session, test_app: App
):
    """Mixed/legacy comma-separated values must also be detected."""
    other = App(name="otherapp")
    other.env_vars = [
        EnvVar(name="HOST_NAME", value="one.com,two.com,three.com", app=other)
    ]
    AppRepository(session=db_session).add(other, auto_commit=True)

    conflict = check_hostname_conflict(db_session, "testapp", ["three.com"])
    assert conflict == ("otherapp", "three.com")


def test_conflict_detection_skips_self(db_session: Session, test_app: App):
    """An app does not conflict with itself."""
    test_app.env_vars.append(EnvVar(name="HOST_NAME", value="mine.com", app=test_app))
    db_session.commit()

    conflict = check_hostname_conflict(db_session, "testapp", ["mine.com"])
    assert conflict is None


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        ("a.com b.com", ["a.com", "b.com"]),
        ("a.com,b.com", ["a.com", "b.com"]),
        ("a.com, b.com  c.com", ["a.com", "b.com", "c.com"]),
        ("", []),
        (None, []),
    ],
)
def test_parse_hostname_string(stored, expected):
    assert parse_hostname_string(stored) == expected
