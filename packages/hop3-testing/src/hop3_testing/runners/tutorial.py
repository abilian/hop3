# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Tutorial test runner.

Runs tutorials via validoc or other tutorial runners.
"""

from __future__ import annotations

import re
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from hop3_testing.catalog.models import Validation, ValidationExpect
from hop3_testing.targets.admin import ADMIN_TOKEN_ENV, LOCAL_API_URL
from hop3_testing.util import build_test_env
from hop3_testing.util.console import PrintingConsole, Verbosity

from ._diagnostics import collect_failure_diagnostics
from .base import TestResult, ValidationResult
from .validations import run_validation

if TYPE_CHECKING:
    from pathlib import Path

    from hop3_testing.catalog.models import TestDefinition
    from hop3_testing.targets.base import DeploymentTarget, TargetInfo


#: curl's config for a tutorial run. A tutorial checks its app the way a reader
#: does, `curl https://<app>.<domain>/`, and a reader's server has a trusted
#: certificate; the test server's is self-signed. Set through CURL_HOME, so
#: the tutorials themselves never teach skipping the certificate check.
_TEST_CURLRC = "insecure\n"

#: Every subdomain resolves to 127.0.0.1.
LOOPBACK_TEST_DOMAIN = "127.0.0.1.sslip.io"

_VALIDOC_BLOCK_RE = re.compile(r"^```(?:bash\s+exec|output|file)\b", re.MULTILINE)


def _on_target_test_domain(info: TargetInfo) -> str:
    """
    The test domain as seen from the target, where validoc runs.

    A container's published address belongs to the Docker host, so from inside
    the container it reaches the host's port 443 and no nginx of ours.
    Loopback is the container's own nginx.
    """
    if info.is_container:
        return LOOPBACK_TEST_DOMAIN
    return build_test_env(info)["HOP3_TEST_DOMAIN"]


def _tutorial_app_name(test: TestDefinition) -> str | None:
    """
    The app a tutorial deploys, by convention ``hop3-tuto-<framework>``.

    Best-effort: a couple of tutorials deviate from the convention, so the
    per-app diagnostics may be empty for those. The always-collected ``hop3
    apps`` snapshot still surfaces the real app. ``None`` when framework unknown.
    """
    framework = (test.metadata.framework or "").strip()
    return f"hop3-tuto-{framework}" if framework else None


def _count_validoc_blocks(path: Path) -> int:
    """
    Count executable validoc fences (``bash exec`` / ``output`` / ``file``).

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
    """
    Runs tutorial tests via validoc.

    Tutorials are markdown files with executable code blocks that
    are validated using the validoc tool.
    """

    target: DeploymentTarget
    """The deployment target."""

    cleanup: bool = True
    """Whether to cleanup after test."""

    verbose: bool = False
    """Whether to print verbose output."""

    console: PrintingConsole = field(default_factory=PrintingConsole)
    """Console for output."""

    def __post_init__(self) -> None:
        """Set verbosity after initialization."""
        if self.verbose:
            self.console.set_verbosity(Verbosity.VERBOSE)

    def run(self, test: TestDefinition) -> TestResult:
        """
        Run a tutorial test.

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

            # A validoc tutorial with no executable blocks is a vacuous pass:
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
                result = self._run_validoc(tutorial_path)
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
        # failed or timed out isn't a black box. The target's app list is always
        # attached; it reveals an app stuck mid-build or a stranded one holding
        # a port. This app's runtime logs + diagnostic bundle follow. Never raises.
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

    def _run_validoc(self, tutorial_path: Path) -> dict:
        """
        Run a tutorial via validoc on the target, prepared by ``ensure_tutorial_host``.

        On the target, the scaffold and build steps use the toolchains the
        installer provisioned, and ``hop3 deploy`` reaches the target's own
        server. A Docker target used to run validoc on the developer's machine,
        which needed every toolchain there and sent the tutorial's ``curl``
        through the client's network to the Docker host's port 443.

        Returns:
            Dict with success, logs, error
        """
        if (problem := self.target.tutorial_host_problem) is not None:
            return {
                "success": False,
                "error": f"Tutorial host not prepared (validoc/token): {problem}",
                "logs": "",
            }
        return self._run_validoc_on_server(tutorial_path)

    def _run_validoc_on_server(self, tutorial_path: Path) -> dict:
        """
        Run validoc on the target server (see ``_run_validoc`` for why).

        Uploads the tutorial markdown to a scratch dir on the server, runs
        ``validoc run`` there with the env that points ``hop3`` at the local
        server, captures the combined output, and removes the scratch dir.
        validoc's own teardown destroys any app it deployed.
        """
        target = self.target
        name = re.sub(r"[^A-Za-z0-9._-]", "_", tutorial_path.stem)
        workdir = f"/tmp/hop3-tut/{name}"
        remote_md = f"{workdir}/{tutorial_path.name}"

        # The on-server `hop3` client deploys to the local server; the env mirrors
        # build_test_env but targets localhost with the minted admin token.
        env = " ".join([
            "HOP3_NO_INPUT=1",
            f"HOP3_TEST_DOMAIN={_on_target_test_domain(target.info)}",
            f"HOP3_API_URL={LOCAL_API_URL}",
            # Read from the server's token file, never written on this line:
            # any local user reads a command line from /proc/<pid>/cmdline.
            ADMIN_TOKEN_ENV,
            f"CURL_HOME={shlex.quote(workdir)}",
            # validoc runs as root here; composer refuses to run its plugins
            # as root unless this is set, which breaks e.g. symfony/flex
            # (`composer require webapp`). Allow it so root builds work.
            "COMPOSER_ALLOW_SUPERUSER=1",
            # Rust is installed (rustup) under the hop3 user. Share the
            # toolchain read-only via RUSTUP_HOME, but give cargo a SEPARATE,
            # root-owned registry/cache. The scaffold's `cargo build` runs as
            # root. If it wrote into /home/hop3/.cargo, the later
            # hop3-user deploy build couldn't read those root-owned registry
            # files ("Permission denied" reading e.g. fnv-*/lib.rs). The
            # rustup proxy (on PATH via /usr/local/bin) honours CARGO_HOME,
            # so cargo still resolves the shared toolchain.
            "CARGO_HOME=/tmp/hop3-tut-cargo",
            "RUSTUP_HOME=/home/hop3/.rustup",
            "PATH=/home/hop3/venv/bin:/usr/local/bin:/home/hop3/.cargo/bin:/usr/bin:/bin:$PATH",
        ])
        # Bound the run server-side (the SSH exec has no timeout of its own): a
        # hung tutorial would otherwise wedge the whole suite. `timeout` sends
        # SIGTERM at 900s, then SIGKILL 30s later. The env-var prefix applies to
        # `timeout`, which passes the environment through to validoc.
        run_cmd = (
            f"cd {shlex.quote(workdir)} && {env} "
            f"timeout -k 30 900 "
            f"/home/hop3/venv/bin/validoc run {shlex.quote(tutorial_path.name)}"
        )

        try:
            target.exec_run(["rm", "-rf", workdir])
            target.upload_file(tutorial_path, remote_md)
            target.exec_run(
                f"printf {shlex.quote(_TEST_CURLRC)} > {shlex.quote(workdir)}/.curlrc"
            )
            code, out, err = target.exec_run(run_cmd)
        except Exception as e:
            return {"success": False, "error": str(e), "logs": ""}
        finally:
            target.exec_run(["rm", "-rf", workdir])

        logs = (out or "") + (err or "")
        if code != 0:
            return {
                "success": False,
                "error": f"validoc failed with exit code {code}",
                "logs": logs,
            }
        return {"success": True, "logs": logs}

    def _run_generic(self, tutorial_path: Path, cwd: Path, runner: str) -> dict:
        """
        Run tutorial using a generic runner.

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
