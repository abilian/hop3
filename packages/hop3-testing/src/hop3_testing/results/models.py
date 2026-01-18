# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""SQLAlchemy models for test result storage."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Base class for all models."""


class TestRun(Base):
    """A collection of test executions.

    Represents a single invocation of hop3-test, which may run
    multiple tests.
    """

    __tablename__ = "test_runs"

    id = Column(Integer, primary_key=True)
    started_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(tz=timezone.utc)
    )
    finished_at = Column(DateTime, nullable=True)

    mode = Column(String(20))
    """Execution mode (dev, ci, nightly, release, package)."""

    target_type = Column(String(20))
    """Target type (docker, remote)."""

    target_name = Column(String(100))
    """Target identifier (e.g., container ID, hostname)."""

    hop3_version = Column(String(50), nullable=True)
    """Hop3 version being tested."""

    total_tests = Column(Integer, default=0)
    """Total number of tests run."""

    passed_tests = Column(Integer, default=0)
    """Number of passing tests."""

    failed_tests = Column(Integer, default=0)
    """Number of failing tests."""

    # Relationships
    results = relationship(
        "TestResultRecord", back_populates="run", cascade="all, delete-orphan"
    )

    @property
    def duration(self) -> float | None:
        """Get run duration in seconds."""
        if self.finished_at and self.started_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None

    @property
    def success_rate(self) -> float:
        """Get success rate as percentage."""
        if self.total_tests == 0:
            return 0.0
        return (self.passed_tests / self.total_tests) * 100


class TestResultRecord(Base):
    """Individual test result."""

    __tablename__ = "test_results"

    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("test_runs.id"))

    test_name = Column(String(100))
    """Test identifier."""

    category = Column(String(20))
    """Test category (deployment, demo, tutorial)."""

    tier = Column(String(20))
    """Test tier (fast, medium, slow, very-slow)."""

    priority = Column(String(5))
    """Test priority (P0, P1, P2)."""

    passed = Column(Boolean)
    """Whether the test passed."""

    duration = Column(Float)
    """Execution time in seconds."""

    error = Column(Text, nullable=True)
    """Error message if test failed."""

    logs = Column(Text, nullable=True)
    """Deployment/execution logs."""

    executed_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(tz=timezone.utc)
    )
    """When the test was executed."""

    # Relationships
    run = relationship("TestRun", back_populates="results")
    validations = relationship(
        "ValidationRecord", back_populates="test_result", cascade="all, delete-orphan"
    )


class ValidationRecord(Base):
    """Individual validation result within a test."""

    __tablename__ = "validation_results"

    id = Column(Integer, primary_key=True)
    test_result_id = Column(Integer, ForeignKey("test_results.id"))

    validation_type = Column(String(20))
    """Validation type (http, command, script, etc.)."""

    passed = Column(Boolean)
    """Whether the validation passed."""

    message = Column(Text)
    """Result message."""

    duration = Column(Float)
    """Validation duration in seconds."""

    # Relationships
    test_result = relationship("TestResultRecord", back_populates="validations")
