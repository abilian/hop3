# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tutorial test runner.

Runs tutorials via validoc or other tutorial runners.
"""

from __future__ import annotations

import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from hop3_testing.catalog.models import Validation, ValidationExpect
from hop3_testing.util import as_text, build_test_env, run_captured
from hop3_testing.util.console import Console, PrintingConsole, Verbosity

from ._diagnostics import collect_failure_diagnostics
from .base import TestResult, ValidationResult
from .validations import run_validation

if TYPE_CHECKING:
    from pathlib import Path

    from hop3_testing.catalog.models import TestDefinition
    from hop3_testing.targets.base import DeploymentTarget


_VALIDOC_BLOCK_RE = re.compile(r"^```(?:bash\s+exec|output|file)\b", re.MULTILINE)


def _tutorial_app_name(test: TestDefinition) -> str | None:
    """The app a tutorial deploys, by convention ``hop3-tuto-<framework>``.

    Best-effort: a couple of tutorials deviate from the convention, so the
    per-app diagnostics may be empty for those — the always-collected ``hop3
    apps`` snapshot still surfaces the real app. ``None`` when framework unknown.
    """
    framework = (test.metadata.framework or "").strip()
    return f"hop3-tuto-{framework}" if framework else None


def _count_validoc_blocks(path: Path) -> int:
    """Count executable validoc fences (``bash exec`` / ``output`` / ``file``).

    A tutorial with zero such blocks isn't being tested at all: validoc exits 0
    with "0 passed", which would otherwise be reported as a (vacuous) pass. The
    usual cause is scanning the *rendered* docs tree (docs/src/tutorials), where
    the markers are stripped, instead of the source (docs/tutorials).
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return 0
    return len(_VALIDOC_BLOCK_RE.findall(text))


@dataclass(frozen=True)
class TutorialTestRunner:
    """Runs tutorial tests via validoc.

    Tutorials are markdown files with executable code blocks that
    are validated using the validoc tool.
    """

    target: DeploymentTarget
    """The deployment target."""

    cleanup: bool = True
    """Whether to cleanup after test."""

    verbose: bool = False
    """Whether to print verbose output."""

    console: Console = field(default_factory=PrintingConsole)
    """Console for output."""

    def __post_init__(self) -> None:
        """Set verbosity after initialization."""
        if self.verbose:
            self.console.set_verbosity(Verbosity.VERBOSE)

    def run(self, test: TestDefinition) -> TestResult:
        """Run a tutorial test.

        Args:
            test: The test definition

        Returns:
            TestResult
        """
        start_time = time.time()
        validation_results = []
        error = None
        logs = ""

        try:
            if test.tutorial is None:
                return TestResult(
                    test=test,
                    passed=False,
                    error="Test has no tutorial configuration",
                )

            if test.source_path is None:
                return TestResult(
                    test=test,
                    passed=False,
                    error="Test has no source path",
                )

            tutorial_dir = test.source_path.parent
            tutorial_path = tutorial_dir / test.tutorial.path

            if not tutorial_path.exists():
                return TestResult(
                    test=test,
                    passed=False,
                    error=f"Tutorial not found: {tutorial_path}",
                )

            self.console.info(f"Running tutorial: {tutorial_path}")
            self.console.debug(f"Runner: {test.tutorial.runner}")

            # A validoc tutorial with no executable blocks is a vacuous pass —
            # refuse it before running, so a stripped/rendered file can never be
            # reported as OK in 0.1s.
            if test.tutorial.runner == "validoc" and not _count_validoc_blocks(
                tutorial_path
            ):
                return TestResult(
                    test=test,
                    passed=False,
                    error=(
                        f"Tutorial has no executable validoc blocks: {tutorial_path}. "
                        "Nothing was tested. This usually means the rendered docs "
                        "tree (docs/src/tutorials, markers stripped) was scanned "
                        "instead of the source (docs/tutorials)."
                    ),
                    total_duration=time.time() - start_time,
                )

            # Run the tutorial using the specified runner
            if test.tutorial.runner == "validoc":
                result = self._run_validoc(tutorial_path, tutorial_dir)
            else:
                result = self._run_generic(
                    tutorial_path, tutorial_dir, test.tutorial.runner
                )

            logs = result.get("logs", "")

            if not result.get("success", False):
                error = result.get("error", "Tutorial execution failed")
            else:
                # Create a validation result for the tutorial
                val_result = ValidationResult(
                    validation=Validation(
                        type="validoc",
                        expect=ValidationExpect(all_blocks_pass=True),
                    ),
                    passed=True,
                    message="All tutorial blocks passed",
                    duration=time.time() - start_time,
                )
                validation_results.append(val_result)

                # Run additional validations if defined
                for validation in test.validations:
                    if validation.type != "validoc":
                        val_result = run_validation(
                            validation=validation,
                            target=self.target,
                            app_name=test.name,
                            app_url=self.target.info.http_base,
                        )
                        validation_results.append(val_result)

        except Exception as e:
            error = str(e)

        passed = error is None and all(v.passed for v in validation_results)

        # On failure, attach SUT-side diagnostics so a tutorial deploy that
        # failed or timed out isn't a black box: the target's app list (always
        # — reveals an app stuck mid-build, or a stranded one holding a port),
        # plus this app's runtime logs + diagnostic bundle. Never raises.
        runtime_logs = ""
        bundle = None
        app_name = _tutorial_app_name(test)
        if not passed:
            runtime_logs, bundle = collect_failure_diagnostics(
                self.target, app_name, deploy_logs=logs
            )

        return TestResult(
            test=test,
            passed=passed,
            validation_results=validation_results,
            deploy_logs=logs,
            total_duration=time.time() - start_time,
            error=error,
            deployed_app_name=app_name,
            runtime_logs=runtime_logs,
            bundle=bundle,
        )

    def _run_validoc(self, tutorial_path: Path, cwd: Path) -> dict:
        """Run tutorial using validoc.

        Args:
            tutorial_path: Path to the tutorial markdown
            cwd: Working directory

        Returns:
            Dict with success, logs, error
        """
        try:
            # Check if validoc is available
            result = subprocess.run(
                [sys.executable, "-m", "validoc", "--help"],
                capture_output=True,
                text=True,  # str, so `result` stays CompletedProcess[str] below
                timeout=10,
                check=False,
            )
            if result.returncode != 0:
                # Try as a command
                result = subprocess.run(
                    ["validoc", "--help"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                if result.returncode != 0:
                    return {
                        "success": False,
                        "error": "validoc not found",
                        "logs": "",
                    }
                validoc_cmd = ["validoc"]
            else:
                validoc_cmd = [sys.executable, "-m", "validoc"]
        except FileNotFoundError:
            return {
                "success": False,
                "error": "validoc not found",
                "logs": "",
            }

        # Run validoc on the tutorial. run_captured kills the whole process
        # group on timeout so validoc's `hop3`/`ssh` grandchildren can't wedge
        # output capture (see its docstring).
        try:
            result = run_captured(
                [*validoc_cmd, "run", str(tutorial_path)],
                cwd=cwd,
                timeout=600,  # 10 minute timeout
                env=build_test_env(self.target.info),
            )

            logs = result.stdout + result.stderr

            if result.returncode != 0:
                return {
                    "success": False,
                    "error": f"validoc failed with exit code {result.returncode}",
                    "logs": logs,
                }

            return {
                "success": True,
                "logs": logs,
            }

        except subprocess.TimeoutExpired as e:
            # Keep the partial output so a hung tutorial still has diagnostics.
            return {
                "success": False,
                "error": "Tutorial execution timed out after 600s",
                "logs": as_text(e.stdout) + as_text(e.stderr),
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "logs": "",
            }

    def _run_generic(self, tutorial_path: Path, cwd: Path, runner: str) -> dict:
        """Run tutorial using a generic runner.

        Args:
            tutorial_path: Path to the tutorial
            cwd: Working directory
            runner: Runner command

        Returns:
            Dict with success, logs, error
        """
        try:
            result = subprocess.run(
                [runner, str(tutorial_path)],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )

            logs = result.stdout + result.stderr

            return {
                "success": result.returncode == 0,
                "error": f"{runner} failed" if result.returncode != 0 else None,
                "logs": logs,
            }

        except FileNotFoundError:
            return {
                "success": False,
                "error": f"Runner not found: {runner}",
                "logs": "",
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "logs": "",
            }
