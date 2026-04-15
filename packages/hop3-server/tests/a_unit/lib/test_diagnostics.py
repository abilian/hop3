# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the structured diagnostics module."""

from __future__ import annotations

import pytest

from hop3.lib import Abort
from hop3.lib.diagnostics import (
    Diagnosis,
    abort_with_diagnosis,
    format_diagnosis,
    log_diagnosis,
)


def test_diagnosis_requires_component():
    with pytest.raises(ValueError, match="component is required"):
        Diagnosis(component="", action="do something", reason="it broke")


def test_diagnosis_requires_action():
    with pytest.raises(ValueError, match="action is required"):
        Diagnosis(component="Foo", action="", reason="it broke")


def test_diagnosis_requires_reason():
    with pytest.raises(ValueError, match="reason is required"):
        Diagnosis(component="Foo", action="do something", reason="")


def test_format_without_hint():
    diag = Diagnosis(
        component="Docker builder",
        action="build image",
        reason="Dockerfile not found in source directory",
    )
    out = format_diagnosis(diag)
    assert out == (
        "Docker builder can't build image: Dockerfile not found in source directory."
    )


def test_format_with_hint():
    diag = Diagnosis(
        component="Docker builder",
        action="build image",
        reason="Dockerfile not found",
        hint="Create a Dockerfile in the app root",
    )
    out = format_diagnosis(diag)
    assert out == (
        "Docker builder can't build image: Dockerfile not found. "
        "Create a Dockerfile in the app root."
    )


def test_format_with_hint_strips_trailing_period():
    """Trailing '.' in hint is stripped to avoid double-punctuation."""
    diag = Diagnosis(
        component="Nix builder",
        action="find hop3.nix",
        reason="no hop3.nix in source directory",
        hint="Run 'hop3 nix:eject' to generate one.",
    )
    out = format_diagnosis(diag)
    assert out.endswith("Run 'hop3 nix:eject' to generate one.")
    assert ".." not in out


def test_format_with_troubleshooting():
    diag = Diagnosis(
        component="MinIO backend",
        action="connect to MinIO",
        reason="connection refused on 127.0.0.1:9000",
        hint="Check that MinIO is running",
        troubleshooting=[
            "supervisorctl status minio",
            "curl http://127.0.0.1:9000/minio/health/live",
        ],
    )
    out = format_diagnosis(diag)
    assert "Troubleshooting:" in out
    assert "  - supervisorctl status minio" in out
    assert "  - curl http://127.0.0.1:9000/minio/health/live" in out


def test_abort_with_diagnosis_raises_abort():
    diag = Diagnosis(
        component="Test component",
        action="do the thing",
        reason="the thing didn't happen",
    )
    with pytest.raises(Abort) as exc_info:
        abort_with_diagnosis(diag)
    assert "Test component can't do the thing" in str(exc_info.value)
    assert "the thing didn't happen" in str(exc_info.value)


def test_log_diagnosis_does_not_raise():
    """log_diagnosis is non-fatal — useful for non-blocking warnings."""
    diag = Diagnosis(
        component="Health check",
        action="reach /health endpoint",
        reason="app returned 500",
        hint="Check app logs with hop3 app logs",
    )
    # Should not raise
    log_diagnosis(diag)


def test_diagnosis_is_immutable():
    """Frozen dataclass — can't modify after construction."""
    diag = Diagnosis(component="A", action="b", reason="c")
    with pytest.raises((AttributeError, Exception)):
        diag.component = "something else"  # type: ignore[misc]
