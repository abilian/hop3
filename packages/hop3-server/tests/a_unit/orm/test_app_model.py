# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for the pure / hermetic surface of the App ORM model.

These tests exercise the parts of ``hop3.orm.app`` that need no DB session,
no subprocess, and no Docker: the IntEnum TypeDecorator, the state machine
(``_transition_state``), the path properties, log parsing/reading, and the
runtime-env accessors.

I/O-heavy and Docker/subprocess methods (create, deploy, destroy, start,
stop, restart and friends) are deliberately left to the e2e layer.

``app_path``'s unsafe-name guard (a defense-in-depth path-traversal check) is
covered by the sibling ``test_app_path_traversal.py``; here we test the
happy-path resolution and the derived paths.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from hop3.config import HopConfig
from hop3.core.env import Env
from hop3.orm import App
from hop3.orm.app import (
    AppStateEnum,
    IntEnum,
    StateTransitionError,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture
def app_root(tmp_path: Path) -> Iterator[Path]:
    """
    Point the HopConfig singleton's APP_ROOT at a tmp dir and restore it.

    ``app_path`` resolves via ``HopConfig.get_instance().APP_ROOT``, so paths
    are made deterministic by overriding HOP3_ROOT (APP_ROOT == HOP3_ROOT/apps).
    The original singleton is restored afterwards so other tests are unaffected.
    """
    original = HopConfig.get_instance()
    HopConfig.set_instance(HopConfig(hop3_root=tmp_path))
    try:
        yield tmp_path / "apps"
    finally:
        HopConfig.set_instance(original)


# ---------------------------------------------------------------------------
# IntEnum TypeDecorator
# ---------------------------------------------------------------------------


class TestIntEnumTypeDecorator:
    @pytest.mark.parametrize(
        ("state", "expected_int"),
        [
            (AppStateEnum.STOPPED, 1),
            (AppStateEnum.STARTING, 2),
            (AppStateEnum.RUNNING, 3),
            (AppStateEnum.STOPPING, 4),
            (AppStateEnum.FAILED, 5),
        ],
    )
    def test_bind_param_converts_enum_to_int(
        self, state: AppStateEnum, expected_int: int
    ) -> None:
        decorator = IntEnum(AppStateEnum)
        assert decorator.process_bind_param(state, dialect=None) == expected_int

    def test_bind_param_passes_none_through(self) -> None:
        decorator = IntEnum(AppStateEnum)
        assert decorator.process_bind_param(None, dialect=None) is None

    def test_bind_param_passes_raw_int_through(self) -> None:
        # Non-enum values are returned unchanged (defensive passthrough).
        decorator = IntEnum(AppStateEnum)
        assert decorator.process_bind_param(3, dialect=None) == 3

    @pytest.mark.parametrize(
        ("stored_int", "expected_state"),
        [
            (1, AppStateEnum.STOPPED),
            (2, AppStateEnum.STARTING),
            (3, AppStateEnum.RUNNING),
            (4, AppStateEnum.STOPPING),
            (5, AppStateEnum.FAILED),
        ],
    )
    def test_result_value_converts_int_to_enum(
        self, stored_int: int, expected_state: AppStateEnum
    ) -> None:
        decorator = IntEnum(AppStateEnum)
        assert (
            decorator.process_result_value(stored_int, dialect=None) is expected_state
        )

    def test_result_value_converts_string_to_enum(self) -> None:
        # SQLite may hand back strings; the decorator coerces to int first.
        decorator = IntEnum(AppStateEnum)
        assert decorator.process_result_value("3", dialect=None) is AppStateEnum.RUNNING

    def test_result_value_passes_none_through(self) -> None:
        decorator = IntEnum(AppStateEnum)
        assert decorator.process_result_value(None, dialect=None) is None

    def test_roundtrip_enum_through_decorator(self) -> None:
        decorator = IntEnum(AppStateEnum)
        for state in AppStateEnum:
            stored = decorator.process_bind_param(state, dialect=None)
            assert decorator.process_result_value(stored, dialect=None) is state


# ---------------------------------------------------------------------------
# is_running property
# ---------------------------------------------------------------------------


class TestIsRunning:
    def test_is_running_true_only_when_running(self) -> None:
        app = App(name="demo", run_state=AppStateEnum.RUNNING)
        assert app.is_running is True

    @pytest.mark.parametrize(
        "state",
        [
            AppStateEnum.STOPPED,
            AppStateEnum.STARTING,
            AppStateEnum.STOPPING,
            AppStateEnum.FAILED,
        ],
    )
    def test_is_running_false_for_non_running_states(self, state: AppStateEnum) -> None:
        app = App(name="demo", run_state=state)
        assert app.is_running is False


# ---------------------------------------------------------------------------
# Path properties (happy path)
# ---------------------------------------------------------------------------


class TestPathProperties:
    def test_app_path_is_app_root_slash_name(self, app_root: Path) -> None:
        app = App(name="myapp")
        assert app.app_path == app_root / "myapp"

    def test_derived_paths_hang_off_app_path(self, app_root: Path) -> None:
        app = App(name="myapp")
        base = app_root / "myapp"
        assert app.repo_path == base / "git"
        assert app.src_path == base / "src"
        assert app.data_path == base / "data"
        assert app.log_path == base / "log"
        assert app.virtualenv_path == base / "venv"

    def test_app_path_accepts_safe_dotted_name(self, app_root: Path) -> None:
        # A dot inside the name (not leading) is fine; pins the guard's exact
        # predicate so it can't silently over-reject. The reject branches are
        # covered by the sibling test_app_path_traversal.py — not duplicated.
        app = App(name="my.app")
        assert app.app_path == app_root / "my.app"


# ---------------------------------------------------------------------------
# _transition_state (state machine)
# ---------------------------------------------------------------------------


VALID_TRANSITIONS = [
    (AppStateEnum.STOPPED, AppStateEnum.STARTING),
    (AppStateEnum.STOPPED, AppStateEnum.FAILED),
    (AppStateEnum.STARTING, AppStateEnum.RUNNING),
    (AppStateEnum.STARTING, AppStateEnum.FAILED),
    (AppStateEnum.RUNNING, AppStateEnum.STOPPING),
    (AppStateEnum.RUNNING, AppStateEnum.FAILED),
    (AppStateEnum.STOPPING, AppStateEnum.STOPPED),
    (AppStateEnum.STOPPING, AppStateEnum.FAILED),
    (AppStateEnum.FAILED, AppStateEnum.STOPPED),
    (AppStateEnum.FAILED, AppStateEnum.STARTING),
]

INVALID_TRANSITIONS = [
    (AppStateEnum.STOPPED, AppStateEnum.RUNNING),
    (AppStateEnum.STOPPED, AppStateEnum.STOPPING),
    (AppStateEnum.STOPPED, AppStateEnum.STOPPED),  # already stopped
    (AppStateEnum.STARTING, AppStateEnum.STOPPED),
    (AppStateEnum.STARTING, AppStateEnum.STOPPING),
    (AppStateEnum.RUNNING, AppStateEnum.STARTING),
    (AppStateEnum.RUNNING, AppStateEnum.RUNNING),  # already running
    (AppStateEnum.STOPPING, AppStateEnum.RUNNING),
    (AppStateEnum.STOPPING, AppStateEnum.STARTING),
    (AppStateEnum.FAILED, AppStateEnum.RUNNING),
    (AppStateEnum.FAILED, AppStateEnum.STOPPING),
    (AppStateEnum.FAILED, AppStateEnum.FAILED),
]


class TestTransitionState:
    @pytest.mark.parametrize(("from_state", "to_state"), VALID_TRANSITIONS)
    def test_valid_transition_mutates_run_state(
        self, from_state: AppStateEnum, to_state: AppStateEnum
    ) -> None:
        app = App(name="demo", run_state=from_state)

        app._transition_state(to_state)

        assert app.run_state is to_state

    @pytest.mark.parametrize(("from_state", "to_state"), VALID_TRANSITIONS)
    def test_valid_transition_stamps_state_changed_at(
        self, from_state: AppStateEnum, to_state: AppStateEnum
    ) -> None:
        app = App(name="demo", run_state=from_state)
        before = datetime.now(UTC)

        app._transition_state(to_state)

        assert app.state_changed_at is not None
        assert app.state_changed_at >= before

    @pytest.mark.parametrize(("from_state", "to_state"), INVALID_TRANSITIONS)
    def test_invalid_transition_raises_and_leaves_state(
        self, from_state: AppStateEnum, to_state: AppStateEnum
    ) -> None:
        app = App(name="demo", run_state=from_state)

        with pytest.raises(StateTransitionError):
            app._transition_state(to_state)

        assert app.run_state is from_state

    def test_same_state_transition_error_says_already(self) -> None:
        app = App(name="demo", run_state=AppStateEnum.RUNNING)

        with pytest.raises(StateTransitionError, match="already running"):
            app._transition_state(AppStateEnum.RUNNING)

    def test_cross_state_invalid_transition_message(self) -> None:
        app = App(name="demo", run_state=AppStateEnum.STOPPED)

        with pytest.raises(StateTransitionError, match="from STOPPED to RUNNING"):
            app._transition_state(AppStateEnum.RUNNING)

    def test_transition_to_failed_records_error_message(self) -> None:
        app = App(name="demo", run_state=AppStateEnum.RUNNING, error_message="")

        app._transition_state(AppStateEnum.FAILED, error_msg="boom")

        assert app.run_state is AppStateEnum.FAILED
        assert app.error_message == "boom"

    def test_successful_transition_clears_error_message(self) -> None:
        # FAILED -> STARTING is a valid recovery transition; it must clear the
        # stale error message.
        app = App(
            name="demo",
            run_state=AppStateEnum.FAILED,
            error_message="previous failure",
        )

        app._transition_state(AppStateEnum.STARTING)

        assert app.run_state is AppStateEnum.STARTING
        assert app.error_message == ""


# ---------------------------------------------------------------------------
# _extract_timestamp_from_log
# ---------------------------------------------------------------------------


class TestExtractTimestampFromLog:
    def test_iso_format_is_parsed(self) -> None:
        app = App(name="demo")
        line = "2025-01-15T10:30:00 worker started"

        ts = app._extract_timestamp_from_log(line)

        # The source builds a naive datetime via fromisoformat; mirror that.
        assert ts == datetime.fromisoformat("2025-01-15T10:30:00")

    def test_iso_with_zone_suffix_drops_zone(self) -> None:
        # The regex only captures the naive YYYY-MM-DDTHH:MM:SS prefix, so a
        # trailing 'Z' or offset is ignored and the result is naive. This pins
        # a real (and slightly surprising) behaviour: timezone info is dropped.
        app = App(name="demo")

        ts = app._extract_timestamp_from_log("2025-01-15T10:30:00Z worker started")

        assert ts == datetime.fromisoformat("2025-01-15T10:30:00")
        assert ts is not None
        assert ts.tzinfo is None

    def test_simple_datetime_format_is_parsed(self) -> None:
        app = App(name="demo")
        line = "2025-01-15 10:30:00 [info] something happened"

        ts = app._extract_timestamp_from_log(line)

        assert ts == datetime.fromisoformat("2025-01-15T10:30:00")

    @pytest.mark.parametrize(
        "line",
        [
            "",
            "no timestamp here at all",
            "[15/Jan/2025:10:30:00 +0000] common log format",  # not supported
            "2025-01-15 plain date only, no time",
        ],
    )
    def test_unparseable_lines_return_none(self, line: str) -> None:
        app = App(name="demo")
        assert app._extract_timestamp_from_log(line) is None

    @pytest.mark.parametrize(
        "line",
        [
            "2025-13-99T99:99:99 iso shape but invalid date",
            "2025-13-99 99:99:99 simple shape but invalid date",
        ],
    )
    def test_regex_match_with_invalid_date_returns_none(self, line: str) -> None:
        # The prefix matches the timestamp regex but fromisoformat rejects it;
        # the method swallows ValueError and returns None.
        app = App(name="demo")
        assert app._extract_timestamp_from_log(line) is None


# ---------------------------------------------------------------------------
# _find_compose_file
# ---------------------------------------------------------------------------


class TestFindComposeFile:
    @pytest.mark.parametrize(
        "filename",
        [
            "docker-compose.yml",
            "docker-compose.yaml",
            "compose.yml",
            "compose.yaml",
        ],
    )
    def test_finds_user_supplied_compose_file(
        self, app_root: Path, filename: str
    ) -> None:
        app = App(name="myapp")
        app.src_path.mkdir(parents=True)
        compose = app.src_path / filename
        compose.write_text("services: {}\n")

        assert app._find_compose_file() == compose

    def test_user_file_preferred_over_generated(self, app_root: Path) -> None:
        app = App(name="myapp")
        app.src_path.mkdir(parents=True)
        user = app.src_path / "docker-compose.yml"
        user.write_text("services: {}\n")
        (app.src_path / ".hop3-compose.yml").write_text("services: {}\n")

        assert app._find_compose_file() == user

    def test_falls_back_to_generated_file_when_present(self, app_root: Path) -> None:
        app = App(name="myapp")
        app.src_path.mkdir(parents=True)
        generated = app.src_path / ".hop3-compose.yml"
        generated.write_text("services: {}\n")

        assert app._find_compose_file() == generated

    def test_returns_generated_path_when_no_compose_file(self, app_root: Path) -> None:
        # When nothing exists, the generated path is returned anyway so that
        # docker compose surfaces a clear error.
        app = App(name="myapp")
        app.src_path.mkdir(parents=True)

        assert app._find_compose_file() == app.src_path / ".hop3-compose.yml"


# ---------------------------------------------------------------------------
# _read_single_log_file
# ---------------------------------------------------------------------------


class TestReadSingleLogFile:
    def test_reads_all_lines_with_worker_header(self, app_root: Path) -> None:
        app = App(name="myapp")
        app.log_path.mkdir(parents=True)
        log_file = app.log_path / "web.1.log"
        log_file.write_text("line one\nline two\n")

        result = app._read_single_log_file(log_file, since_dt=None)

        assert result[0] == "==> web.1 <=="
        assert "line one" in result
        assert "line two" in result
        assert result[-1] == ""  # trailing blank separator

    def test_since_filter_drops_older_timestamped_lines(self, app_root: Path) -> None:
        app = App(name="myapp")
        app.log_path.mkdir(parents=True)
        log_file = app.log_path / "web.1.log"
        log_file.write_text(
            "2025-01-15T09:00:00 old entry\n2025-01-15T11:00:00 new entry\n"
        )
        since = datetime.fromisoformat("2025-01-15T10:00:00")

        result = app._read_single_log_file(log_file, since_dt=since)

        assert "2025-01-15T09:00:00 old entry" not in result
        assert "2025-01-15T11:00:00 new entry" in result

    def test_unreadable_file_yields_error_line(self, app_root: Path) -> None:
        # If a log "file" can't be opened (here: it's actually a directory),
        # the method must not raise; it records an "Error reading ..." line.
        app = App(name="myapp")
        app.log_path.mkdir(parents=True)
        not_a_file = app.log_path / "web.1.log"
        not_a_file.mkdir()  # opening a directory as a file raises

        result = app._read_single_log_file(not_a_file, since_dt=None)

        assert any(line.startswith("Error reading") for line in result)

    def test_since_filter_keeps_untimestamped_lines(self, app_root: Path) -> None:
        # Lines with no parseable timestamp are not filtered out.
        app = App(name="myapp")
        app.log_path.mkdir(parents=True)
        log_file = app.log_path / "web.1.log"
        log_file.write_text("plain unstamped line\n")
        since = datetime.fromisoformat("2099-01-01T00:00:00")

        result = app._read_single_log_file(log_file, since_dt=since)

        assert "plain unstamped line" in result


# ---------------------------------------------------------------------------
# _get_file_logs
# ---------------------------------------------------------------------------


class TestGetFileLogs:
    def test_no_log_directory_message(self, app_root: Path) -> None:
        app = App(name="myapp")  # log_path does not exist yet

        result = app._get_file_logs()

        assert result == [f"No log directory found for app '{app.name}'"]

    def test_empty_log_directory_message(self, app_root: Path) -> None:
        app = App(name="myapp")
        app.log_path.mkdir(parents=True)

        result = app._get_file_logs()

        assert result == [f"No log files found for app '{app.name}'"]

    def test_returns_last_n_lines_across_files(self, app_root: Path) -> None:
        app = App(name="myapp")
        app.log_path.mkdir(parents=True)
        (app.log_path / "web.1.log").write_text("a1\na2\na3\n")

        result = app._get_file_logs(lines=2)

        # Only the last 2 collected lines are returned.
        assert len(result) == 2
        # The most recent content line must survive the tail.
        assert "a3" in result

    def test_since_filter_applied_across_file_logs(self, app_root: Path) -> None:
        app = App(name="myapp")
        app.log_path.mkdir(parents=True)
        (app.log_path / "web.1.log").write_text(
            "2025-01-15T09:00:00 before\n2025-01-15T12:00:00 after\n"
        )

        result = app._get_file_logs(lines=100, since="2025-01-15T10:00:00")

        joined = "\n".join(result)
        assert "before" not in joined
        assert "after" in joined

    def test_invalid_since_timestamp_is_ignored(self, app_root: Path) -> None:
        # A bad 'since' value must not raise; the filter is simply skipped.
        app = App(name="myapp")
        app.log_path.mkdir(parents=True)
        (app.log_path / "web.1.log").write_text("2025-01-15T09:00:00 entry\n")

        result = app._get_file_logs(lines=100, since="not-a-timestamp")

        assert any("entry" in line for line in result)


# ---------------------------------------------------------------------------
# get_logs dispatch (non-Docker runtime -> file logs; pure routing)
# ---------------------------------------------------------------------------


class TestGetLogsDispatch:
    def test_uwsgi_runtime_reads_file_logs(self, app_root: Path) -> None:
        # For non-Docker runtimes, get_logs() must route to the (hermetic)
        # file-log reader rather than the Docker path. We verify by observing
        # the real file content surface, not by spying on the call.
        app = App(name="myapp", runtime="uwsgi")
        app.log_path.mkdir(parents=True)
        (app.log_path / "web.1.log").write_text("hello from file\n")

        result = app.get_logs(lines=100)

        assert any("hello from file" in line for line in result)

    def test_uwsgi_runtime_no_dir_uses_file_log_message(self, app_root: Path) -> None:
        # The "no log directory" sentinel is the file-log path's message, which
        # confirms get_logs() dispatched to _get_file_logs (not _get_docker_logs,
        # which would emit a different, Docker-flavoured message).
        app = App(name="myapp", runtime="uwsgi")

        result = app.get_logs()

        assert result == [f"No log directory found for app '{app.name}'"]


# ---------------------------------------------------------------------------
# get_runtime_env / update_runtime_env
# ---------------------------------------------------------------------------


class TestRuntimeEnv:
    def test_get_runtime_env_empty_for_new_app(self) -> None:
        app = App(name="demo")
        env = app.get_runtime_env()

        assert isinstance(env, Env)
        assert dict(env) == {}

    def test_get_runtime_env_reflects_attached_env_vars(self) -> None:
        # Drive get_runtime_env in isolation by populating the in-memory
        # env_vars relationship directly (no DB session needed).
        from hop3.orm import EnvVar  # ruff:ignore[import-outside-top-level]

        app = App(name="demo")
        app.env_vars.append(EnvVar(name="FOO", value="bar"))
        app.env_vars.append(EnvVar(name="PORT", value="8080"))

        env = app.get_runtime_env()

        assert env["FOO"] == "bar"
        assert env["PORT"] == "8080"

    def test_update_runtime_env_sets_env_vars(self) -> None:
        app = App(name="demo")
        app.update_runtime_env(Env({"A": "1", "B": "2"}))
        assert dict(app.get_runtime_env()) == {"A": "1", "B": "2"}

    def test_update_runtime_env_replaces_rather_than_merges(self) -> None:
        # update_runtime_env clears existing vars first — a second call replaces.
        app = App(name="demo")
        app.update_runtime_env(Env({"A": "1", "B": "2"}))
        app.update_runtime_env(Env({"C": "3"}))
        assert dict(app.get_runtime_env()) == {"C": "3"}


# start() refuses an app that never built (regression)


def test_start_refuses_an_app_that_never_deployed():
    """
    Starting a never-built app must fail loud with the real reason.

    Regression: a catalog install whose build failed ("unpinned requirements")
    could still be started; the empty venv then produced `gunicorn: not found`
    and a generic "Failed to start within 60s", burying the build failure that
    was the actual cause.
    """
    app = App(name="never-built")
    assert app.last_deployed_at is None

    with pytest.raises(StateTransitionError, match="never deployed successfully"):
        app.start()

    # The doomed spawn must not have happened, so no state change either.
    assert app.run_state != AppStateEnum.STARTING


def test_start_error_points_at_the_build_log():
    """The message must name the command that shows why the build failed."""
    app = App(name="never-built-2")

    with pytest.raises(StateTransitionError) as exc_info:
        app.start()

    assert "build-logs" in str(exc_info.value)
    assert "never-built-2" in str(exc_info.value)
