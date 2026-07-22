# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

# ruff:file-ignore[global-statement]
# `_current_logger` is per-deployment state. A scoped Dishka provider
# could express it, but the existing deploy() flow doesn't carry a
# container — passing the logger through DeploymentContext is simpler
# than introducing one for this single dependency.

"""Decision logging for deployment transparency.

This module provides structured logging for implicit decisions made during
deployment. When Hop3 auto-detects builders, toolchains, or configuration
sources, these decisions are logged clearly so users can understand what
happened and debug issues more easily.

Example output:
    [builder] Using 'local': explicitly set in hop3.toml [build].builder
    [toolchain] Using 'python': detected requirements.txt and pyproject.toml
    [config] Using hop3.toml for 'web' worker: overrides Procfile definition
    [config] Using Procfile for 'worker' process: not defined in hop3.toml
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from hop3.lib import log

if TYPE_CHECKING:
    from collections.abc import Sequence


class DecisionType(Enum):
    """Types of decisions that can be logged."""

    BUILDER = "builder"
    TOOLCHAIN = "toolchain"
    DEPLOYER = "deployer"
    CONFIG_SOURCE = "config"
    WORKER_SOURCE = "worker"
    ADDON = "addon"
    PROXY = "proxy"


class DecisionReason(Enum):
    """Reason categories for decisions."""

    EXPLICIT = "explicit"  # User specified in config
    AUTO_DETECTED = "auto-detected"  # Auto-detected from files
    DEFAULT = "default"  # Using default value
    FALLBACK = "fallback"  # Fell back from preferred option
    OVERRIDE = "override"  # One source overrode another


@dataclass
class Decision:
    """Represents a single decision made during deployment."""

    type: DecisionType
    chosen: str
    reason: str
    reason_category: DecisionReason = DecisionReason.AUTO_DETECTED
    alternatives: list[str] | None = None
    details: dict | None = None

    def format(self) -> str:
        """Format the decision as a log message."""
        base = f"[{self.type.value}] Using '{self.chosen}': {self.reason}"
        if self.alternatives:
            base += f" (alternatives: {', '.join(self.alternatives)})"
        return base


@dataclass
class DecisionLogger:
    """Collects and logs deployment decisions.

    Usage:
        logger = DecisionLogger()
        logger.log_builder_decision("local", "explicitly set in hop3.toml")
        logger.log_toolchain_decision("python", "detected requirements.txt")
        logger.flush()  # Outputs all decisions
    """

    decisions: list[Decision] = field(default_factory=list)
    _flushed: bool = field(default=False, repr=False)

    def log_decision(self, decision: Decision) -> None:
        """Add a decision to the log."""
        self.decisions.append(decision)
        # Also output immediately at verbose level
        log(decision.format(), level=1, fg="cyan")

    def log_builder_decision(
        self,
        builder: str,
        reason: str,
        *,
        explicit: bool = False,
        alternatives: Sequence[str] | None = None,
    ) -> None:
        """Log a builder selection decision."""
        self.log_decision(
            Decision(
                type=DecisionType.BUILDER,
                chosen=builder,
                reason=reason,
                reason_category=DecisionReason.EXPLICIT
                if explicit
                else DecisionReason.AUTO_DETECTED,
                alternatives=list(alternatives) if alternatives else None,
            )
        )

    def log_toolchain_decision(
        self,
        toolchain: str,
        reason: str,
        *,
        explicit: bool = False,
        detected_files: Sequence[str] | None = None,
    ) -> None:
        """Log a toolchain selection decision."""
        details = {"detected_files": list(detected_files)} if detected_files else None
        self.log_decision(
            Decision(
                type=DecisionType.TOOLCHAIN,
                chosen=toolchain,
                reason=reason,
                reason_category=DecisionReason.EXPLICIT
                if explicit
                else DecisionReason.AUTO_DETECTED,
                details=details,
            )
        )

    def log_deployer_decision(
        self,
        deployer: str,
        reason: str,
        *,
        artifact_kind: str | None = None,
    ) -> None:
        """Log a deployer selection decision."""
        details = {"artifact_kind": artifact_kind} if artifact_kind else None
        self.log_decision(
            Decision(
                type=DecisionType.DEPLOYER,
                chosen=deployer,
                reason=reason,
                reason_category=DecisionReason.AUTO_DETECTED,
                details=details,
            )
        )

    def flush(self) -> None:
        """Output all decisions as a summary (for end of deployment)."""
        if self._flushed or not self.decisions:
            return

        log("--- Deployment Decisions Summary ---", level=2, fg="cyan")
        for decision in self.decisions:
            log(f"  {decision.format()}", level=2, fg="cyan")

        self._flushed = True


# Global decision logger instance for current deployment
_current_logger: DecisionLogger | None = None


def get_decision_logger() -> DecisionLogger:
    """Get the current deployment's decision logger.

    Creates a new one if none exists.
    """
    global _current_logger
    if _current_logger is None:
        _current_logger = DecisionLogger()
    return _current_logger


def reset_decision_logger() -> None:
    """Reset the decision logger (called at start of deployment)."""
    global _current_logger
    _current_logger = DecisionLogger()


def flush_decision_logger() -> None:
    """Flush and reset the decision logger (called at end of deployment)."""
    global _current_logger
    if _current_logger:
        _current_logger.flush()
    _current_logger = None
