# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tutorial test runner.

Runs tutorials via validoc or other tutorial runners.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

from .base import TestResult, ValidationResult

if TYPE_CHECKING:
    from ..catalog.models import TestDefinition
    from ..targets.base import DeploymentTarget


class TutorialTestRunner:
    """Runs tutorial tests via validoc.

    Tutorials are markdown files with executable code blocks that
    are validated using the validoc tool.
    """

    def __init__(
        self,
        target: DeploymentTarget,
        cleanup: bool = True,
        verbose: bool = False,
    ):
        """Initialize the runner.

        Args:
            target: The deployment target
            cleanup: Whether to cleanup after test
            verbose: Whether to print verbose output
        """
        self.target = target
        self.cleanup = cleanup
        self.verbose = verbose

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

            if self.verbose:
                print(f"  Running tutorial: {tutorial_path}")
                print(f"  Runner: {test.tutorial.runner}")

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
                from ..catalog.models import Validation, ValidationExpect

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
                        from .validations import run_validation

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

        return TestResult(
            test=test,
            passed=passed,
            validation_results=validation_results,
            deploy_logs=logs,
            total_duration=time.time() - start_time,
            error=error,
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
                timeout=10,
            )
            if result.returncode != 0:
                # Try as a command
                result = subprocess.run(
                    ["validoc", "--help"],
                    capture_output=True,
                    timeout=10,
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

        # Run validoc on the tutorial
        try:
            result = subprocess.run(
                [*validoc_cmd, "run", str(tutorial_path)],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minute timeout
                env={
                    **dict(subprocess.os.environ),
                    "HOP3_TEST_HOST": self.target.info.ssh_host,
                    "HOP3_TEST_PORT": str(self.target.info.ssh_port),
                    "HOP3_TEST_SSH_KEY": self.target.info.ssh_key or "",
                },
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

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Tutorial execution timed out",
                "logs": "",
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
