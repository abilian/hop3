# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for deployment decision logging."""

from __future__ import annotations

import pytest

from hop3.lib import decision_log
from hop3.lib.decision_log import (
    Decision,
    DecisionLogger,
    DecisionReason,
    DecisionType,
    flush_decision_logger,
    get_decision_logger,
    reset_decision_logger,
)


@pytest.fixture
def captured_logs(monkeypatch):
    """Replace the module-level ``log`` with an in-memory recorder.

    Each entry is a ``(msg, level, fg)`` tuple. This avoids real console
    output and lets tests assert on what would have been emitted.
    """
    records: list[tuple[str, int, str]] = []

    def fake_log(msg, level=0, fg="green"):
        records.append((msg, level, fg))

    monkeypatch.setattr(decision_log, "log", fake_log)
    return records


@pytest.fixture(autouse=True)
def restore_global_logger():
    """Restore the module-level singleton after each test.

    The global ``_current_logger`` is shared state; tests that touch it
    must not leak into the rest of the suite.
    """
    saved = decision_log._current_logger
    yield
    decision_log._current_logger = saved


class TestDecisionFormat:
    """Tests for Decision.format()."""

    def test_format_without_alternatives(self):
        """A decision with no alternatives renders the base message."""
        decision = Decision(
            type=DecisionType.BUILDER,
            chosen="local",
            reason="explicitly set in hop3.toml",
        )

        assert decision.format() == (
            "[builder] Using 'local': explicitly set in hop3.toml"
        )

    def test_format_with_alternatives(self):
        """Alternatives are appended in a parenthesised, comma-joined list."""
        decision = Decision(
            type=DecisionType.TOOLCHAIN,
            chosen="python",
            reason="detected requirements.txt",
            alternatives=["node", "ruby"],
        )

        assert decision.format() == (
            "[toolchain] Using 'python': detected requirements.txt"
            " (alternatives: node, ruby)"
        )

    def test_format_with_single_alternative(self):
        """A single alternative still renders the alternatives clause."""
        decision = Decision(
            type=DecisionType.PROXY,
            chosen="nginx",
            reason="default proxy",
            alternatives=["caddy"],
        )

        assert decision.format() == (
            "[proxy] Using 'nginx': default proxy (alternatives: caddy)"
        )

    def test_format_with_empty_alternatives_omits_clause(self):
        """An empty alternatives list is falsy and the clause is omitted."""
        decision = Decision(
            type=DecisionType.DEPLOYER,
            chosen="uwsgi",
            reason="python web app",
            alternatives=[],
        )

        assert decision.format() == "[deployer] Using 'uwsgi': python web app"

    def test_format_uses_type_enum_value(self):
        """The prefix comes from the DecisionType enum value, not its name."""
        decision = Decision(
            type=DecisionType.CONFIG_SOURCE,
            chosen="web from hop3.toml",
            reason="overrides Procfile",
        )

        assert decision.format().startswith("[config] ")


class TestDecisionDefaults:
    """Tests for Decision dataclass defaults."""

    def test_default_reason_category_is_auto_detected(self):
        """A bare Decision defaults to AUTO_DETECTED."""
        decision = Decision(type=DecisionType.ADDON, chosen="redis", reason="x")

        assert decision.reason_category is DecisionReason.AUTO_DETECTED
        assert decision.alternatives is None
        assert decision.details is None


class TestLogDecision:
    """Tests for DecisionLogger.log_decision()."""

    def test_log_decision_appends_to_list(self, captured_logs):
        """log_decision stores the decision in order."""
        logger = DecisionLogger()
        decision = Decision(type=DecisionType.BUILDER, chosen="local", reason="r")

        logger.log_decision(decision)

        assert logger.decisions == [decision]

    def test_log_decision_emits_at_verbose_level(self, captured_logs):
        """log_decision emits the formatted message at level 1 in cyan."""
        logger = DecisionLogger()
        decision = Decision(type=DecisionType.BUILDER, chosen="local", reason="r")

        logger.log_decision(decision)

        assert captured_logs == [("[builder] Using 'local': r", 1, "cyan")]

    def test_log_decision_preserves_insertion_order(self, captured_logs):
        """Multiple decisions are kept in the order they were logged."""
        logger = DecisionLogger()
        first = Decision(type=DecisionType.BUILDER, chosen="a", reason="r1")
        second = Decision(type=DecisionType.TOOLCHAIN, chosen="b", reason="r2")

        logger.log_decision(first)
        logger.log_decision(second)

        assert logger.decisions == [first, second]


class TestLogBuilderDecision:
    """Tests for DecisionLogger.log_builder_decision()."""

    def test_explicit_flag_sets_explicit_category(self, captured_logs):
        """explicit=True maps to the EXPLICIT reason category."""
        logger = DecisionLogger()

        logger.log_builder_decision("local", "set in toml", explicit=True)

        decision = logger.decisions[0]
        assert decision.type is DecisionType.BUILDER
        assert decision.chosen == "local"
        assert decision.reason_category is DecisionReason.EXPLICIT

    def test_default_is_auto_detected(self, captured_logs):
        """Without explicit, the builder decision is AUTO_DETECTED."""
        logger = DecisionLogger()

        logger.log_builder_decision("docker", "detected Dockerfile")

        assert logger.decisions[0].reason_category is DecisionReason.AUTO_DETECTED

    def test_alternatives_are_copied_into_a_list(self, captured_logs):
        """A tuple of alternatives is normalised to a list."""
        logger = DecisionLogger()
        alts = ("docker", "nix")

        logger.log_builder_decision("local", "r", alternatives=alts)

        decision = logger.decisions[0]
        assert decision.alternatives == ["docker", "nix"]
        assert isinstance(decision.alternatives, list)

    def test_no_alternatives_leaves_field_none(self, captured_logs):
        """Omitting alternatives keeps the field as None."""
        logger = DecisionLogger()

        logger.log_builder_decision("local", "r")

        assert logger.decisions[0].alternatives is None


class TestLogToolchainDecision:
    """Tests for DecisionLogger.log_toolchain_decision()."""

    def test_detected_files_stored_in_details(self, captured_logs):
        """detected_files is wrapped in the details dict."""
        logger = DecisionLogger()

        logger.log_toolchain_decision(
            "python", "r", detected_files=["requirements.txt"]
        )

        decision = logger.decisions[0]
        assert decision.type is DecisionType.TOOLCHAIN
        assert decision.details == {"detected_files": ["requirements.txt"]}

    def test_no_detected_files_leaves_details_none(self, captured_logs):
        """Omitting detected_files keeps details as None."""
        logger = DecisionLogger()

        logger.log_toolchain_decision("python", "r")

        assert logger.decisions[0].details is None

    def test_explicit_flag_sets_explicit_category(self, captured_logs):
        """explicit=True maps to the EXPLICIT reason category."""
        logger = DecisionLogger()

        logger.log_toolchain_decision("python", "r", explicit=True)

        assert logger.decisions[0].reason_category is DecisionReason.EXPLICIT


class TestLogDeployerDecision:
    """Tests for DecisionLogger.log_deployer_decision()."""

    def test_artifact_kind_stored_in_details(self, captured_logs):
        """artifact_kind is wrapped in the details dict."""
        logger = DecisionLogger()

        logger.log_deployer_decision("static", "r", artifact_kind="html")

        decision = logger.decisions[0]
        assert decision.type is DecisionType.DEPLOYER
        assert decision.details == {"artifact_kind": "html"}
        assert decision.reason_category is DecisionReason.AUTO_DETECTED

    def test_no_artifact_kind_leaves_details_none(self, captured_logs):
        """Omitting artifact_kind keeps details as None."""
        logger = DecisionLogger()

        logger.log_deployer_decision("uwsgi", "r")

        assert logger.decisions[0].details is None


class TestFlush:
    """Tests for DecisionLogger.flush()."""

    def test_flush_empty_emits_nothing(self, captured_logs):
        """Flushing an empty logger produces no output and stays unflushed."""
        logger = DecisionLogger()

        logger.flush()

        assert captured_logs == []
        assert logger._flushed is False

    def test_flush_emits_header_and_each_decision(self, captured_logs):
        """Flush emits a header then every decision at verbose level 2."""
        logger = DecisionLogger()
        logger.log_builder_decision("local", "r1")
        logger.log_toolchain_decision("python", "r2")
        captured_logs.clear()  # drop the per-decision level-1 emissions

        logger.flush()

        assert captured_logs == [
            ("--- Deployment Decisions Summary ---", 2, "cyan"),
            ("  [builder] Using 'local': r1", 2, "cyan"),
            ("  [toolchain] Using 'python': r2", 2, "cyan"),
        ]
        assert logger._flushed is True

    def test_flush_is_idempotent(self, captured_logs):
        """A second flush is a no-op once already flushed."""
        logger = DecisionLogger()
        logger.log_builder_decision("local", "r1")
        logger.flush()
        captured_logs.clear()

        logger.flush()

        assert captured_logs == []


class TestGlobalLogger:
    """Tests for the module-level singleton helpers."""

    def test_get_creates_logger_when_none(self):
        """get_decision_logger lazily creates a logger."""
        decision_log._current_logger = None

        logger = get_decision_logger()

        assert isinstance(logger, DecisionLogger)

    def test_get_returns_same_instance(self):
        """Repeated calls return the cached singleton."""
        decision_log._current_logger = None

        first = get_decision_logger()
        second = get_decision_logger()

        assert first is second

    def test_reset_replaces_with_fresh_logger(self, captured_logs):
        """reset_decision_logger swaps in an empty logger."""
        existing = get_decision_logger()
        existing.log_builder_decision("local", "r")

        reset_decision_logger()

        new_logger = get_decision_logger()
        assert new_logger is not existing
        assert new_logger.decisions == []

    def test_flush_global_flushes_and_clears(self, captured_logs):
        """flush_decision_logger flushes the current logger then clears it."""
        logger = get_decision_logger()
        logger.log_builder_decision("local", "r")
        captured_logs.clear()

        flush_decision_logger()

        # The summary header was emitted by the flush.
        assert ("--- Deployment Decisions Summary ---", 2, "cyan") in captured_logs
        assert decision_log._current_logger is None

    def test_flush_global_with_no_logger_is_safe(self, captured_logs):
        """flush_decision_logger is a no-op when no logger exists."""
        decision_log._current_logger = None

        flush_decision_logger()

        assert captured_logs == []
        assert decision_log._current_logger is None
