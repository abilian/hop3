# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for DockerBuilder."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from hop3.core.protocols import BuildContext
from hop3.lib import Abort
from hop3.plugins.docker.builder import (
    DockerBuilder,
    _extract_build_error,
    _is_transient_registry_error,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestDockerBuilderAccept:
    """Tests for DockerBuilder.accept() method."""

    def test_accept_with_dockerfile(self, tmp_path: Path):
        """Should accept when Dockerfile exists."""
        # Create Dockerfile
        (tmp_path / "Dockerfile").write_text(
            "FROM python:3.11@sha256:0000000000000000000000000000000000000000000000000000000000000000\n"
        )

        context = BuildContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
        )
        builder = DockerBuilder(context)

        assert builder.accept() is True

    def test_reject_without_dockerfile(self, tmp_path: Path):
        """Should reject when no Dockerfile exists."""
        context = BuildContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
        )
        builder = DockerBuilder(context)

        assert builder.accept() is False

    def test_reject_with_dockerfile_directory(self, tmp_path: Path):
        """Should reject when Dockerfile is a directory, not a file."""
        (tmp_path / "Dockerfile").mkdir()

        context = BuildContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
        )
        builder = DockerBuilder(context)

        assert builder.accept() is False


class TestDockerBuilderImageTag:
    """Tests for image tag generation."""

    def test_generate_image_tag_simple(self, tmp_path: Path):
        """Should generate correct image tag for simple app name."""
        context = BuildContext(
            app_name="myapp",
            source_path=tmp_path,
            app_config={},
        )
        builder = DockerBuilder(context)

        assert builder._generate_image_tag() == "hop3/myapp:latest"

    def test_generate_image_tag_with_underscores(self, tmp_path: Path):
        """Should convert underscores to hyphens in image tag."""
        context = BuildContext(
            app_name="my_app_name",
            source_path=tmp_path,
            app_config={},
        )
        builder = DockerBuilder(context)

        assert builder._generate_image_tag() == "hop3/my-app-name:latest"

    def test_generate_image_tag_lowercase(self, tmp_path: Path):
        """Should convert app name to lowercase."""
        context = BuildContext(
            app_name="MyApp",
            source_path=tmp_path,
            app_config={},
        )
        builder = DockerBuilder(context)

        assert builder._generate_image_tag() == "hop3/myapp:latest"


class TestDockerBuilderMetadataExtraction:
    """Tests for Dockerfile metadata extraction."""

    def test_extract_single_exposed_port(self, tmp_path: Path):
        """Should extract single EXPOSE port from Dockerfile."""
        dockerfile = tmp_path / "Dockerfile"
        dockerfile.write_text(
            "FROM python:3.11@sha256:0000000000000000000000000000000000000000000000000000000000000000\nEXPOSE 8080\nCMD python app.py\n"
        )

        context = BuildContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
        )
        builder = DockerBuilder(context)

        metadata = builder._extract_metadata()

        assert metadata["app_name"] == "test-app"
        assert metadata["builder"] == "docker"
        assert metadata["exposed_ports"] == [8080]

    def test_extract_multiple_exposed_ports(self, tmp_path: Path):
        """Should extract multiple EXPOSE ports from Dockerfile."""
        dockerfile = tmp_path / "Dockerfile"
        dockerfile.write_text("FROM nginx\nEXPOSE 80 443\n")

        context = BuildContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
        )
        builder = DockerBuilder(context)

        metadata = builder._extract_metadata()

        assert metadata["exposed_ports"] == [80, 443]

    def test_extract_port_with_protocol(self, tmp_path: Path):
        """Should extract port even with protocol suffix."""
        dockerfile = tmp_path / "Dockerfile"
        dockerfile.write_text("FROM nginx\nEXPOSE 8080/tcp\n")

        context = BuildContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
        )
        builder = DockerBuilder(context)

        metadata = builder._extract_metadata()

        assert metadata["exposed_ports"] == [8080]

    def test_no_exposed_ports(self, tmp_path: Path):
        """Should handle Dockerfile without EXPOSE."""
        dockerfile = tmp_path / "Dockerfile"
        dockerfile.write_text(
            "FROM python:3.11@sha256:0000000000000000000000000000000000000000000000000000000000000000\nCMD python app.py\n"
        )

        context = BuildContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
        )
        builder = DockerBuilder(context)

        metadata = builder._extract_metadata()

        assert "exposed_ports" not in metadata


class TestDockerBuilderBuild:
    """Tests for DockerBuilder.build() method."""

    def test_build_success(self, tmp_path: Path):
        """Should return BuildArtifact on successful build."""
        dockerfile = tmp_path / "Dockerfile"
        dockerfile.write_text(
            "FROM python:3.11@sha256:0000000000000000000000000000000000000000000000000000000000000000\nEXPOSE 8080\n"
        )

        context = BuildContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
        )
        builder = DockerBuilder(context)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Successfully built abc123\n",
            )

            artifact = builder.build()

            assert artifact.kind == "docker-image"
            assert artifact.location == "hop3/test-app:latest"
            assert artifact.metadata["app_name"] == "test-app"
            assert artifact.metadata["exposed_ports"] == [8080]

    def test_build_docker_not_found(self, tmp_path: Path):
        """Should raise Abort when Docker is not installed."""
        dockerfile = tmp_path / "Dockerfile"
        dockerfile.write_text(
            "FROM python:3.11@sha256:0000000000000000000000000000000000000000000000000000000000000000\n"
        )

        context = BuildContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
        )
        builder = DockerBuilder(context)

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()

            with pytest.raises(Abort, match="'docker' binary was not found"):
                builder.build()

    def test_build_failure(self, tmp_path: Path):
        """Should raise Abort when docker build fails."""
        dockerfile = tmp_path / "Dockerfile"
        dockerfile.write_text(
            "FROM nonexistent:image@sha256:0000000000000000000000000000000000000000000000000000000000000000\n"
        )

        context = BuildContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
        )
        builder = DockerBuilder(context)

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                1, "docker build", stderr="Error: image not found"
            )

            with pytest.raises(Abort, match="Docker build failed"):
                builder.build()

    def test_build_timeout(self, tmp_path: Path):
        """Should raise Abort when build times out (fixed 30-minute budget)."""
        (tmp_path / "Dockerfile").write_text(
            "FROM python:3.11@sha256:0000000000000000000000000000000000000000000000000000000000000000\n"
        )

        context = BuildContext(
            app_name="test-app",
            source_path=tmp_path,
            app_config={},
        )
        builder = DockerBuilder(context)

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("docker build", 30 * 60)
            with pytest.raises(Abort, match="exceeded the 30-minute timeout"):
                builder.build()

            # subprocess.run was invoked with the fixed timeout.
            assert mock_run.call_args.kwargs["timeout"] == 30 * 60


# --- build-failure reporting: one concise root cause, not a 3x backtrace dump --


def test_extract_build_error_prefers_exception_line():
    # The real discourse failure: root cause is an exception line buried under a
    # "Couldn't connect" notice, a git warning, and (below) a huge backtrace.
    out = (
        "#12 5.195 Couldn't connect to Redis\n"
        "#12 5.207 fatal: not a git repository\n"
        "#12 5.383 rake aborted!\n"
        "#12 5.383 Redis::CannotConnectError: Error connecting to Redis on "
        "localhost:6379 (Errno::ECONNREFUSED)\n"
        "#12 5.384 .../redis/client.rb:398:in `establish_connection'\n"
    )
    assert _extract_build_error(out) == (
        "Redis::CannotConnectError: Error connecting to Redis on "
        "localhost:6379 (Errno::ECONNREFUSED)"
    )


def test_extract_build_error_marker_fallback():
    out = "Step 3/9 : RUN make\nmake: *** No rule to make target. Stop.\nerror: build failed\n"
    # no exception class → first strong marker line
    assert _extract_build_error(out) == "error: build failed"


def test_extract_build_error_empty():
    assert _extract_build_error("") == "(no build output)"


def test_extract_build_error_ignores_benign_lines_from_earlier_steps():
    """
    Regression: a benign line in an EARLIER step must not out-rank the real
    error in the step that actually failed.

    Ruby's ./configure prints `configuring -test-/fatal` (a directory name) in an
    early step. The bare "fatal" marker matched that substring, so a discourse
    build that really died ~100 lines later on a missing `brotli` binary was
    reported as "configuring -test-/fatal" — actively misleading. BuildKit names
    the failing step (`#12 ERROR:`), so extraction is scoped to that step.
    """
    out = (
        "#7 83.9 configuring -test-/fatal\n"
        "#7 84.0 configuring -test-/file\n"
        "#12 124.4 Compressing Javascript and Generating Source Maps\n"
        "#12 124.5 rake aborted!\n"
        "#12 124.5 Errno::ENOENT: No such file or directory - brotli (Errno::ENOENT)\n"
        "#12 124.5 /home/discourse/app/lib/tasks/assets.rake:211:in `brotli'\n"
        '#12 ERROR: process "/bin/sh -c rake assets:precompile" did not complete'
        " successfully: exit code: 1\n"
    )
    # The Ruby `Errno::ENOENT:` shape has no Error/Exception suffix, so it must be
    # matched too — and it must beat both the earlier "fatal" and "rake aborted!".
    assert _extract_build_error(out) == (
        "Errno::ENOENT: No such file or directory - brotli (Errno::ENOENT)"
    )


def test_extract_build_error_uses_buildkit_message_when_step_has_no_output():
    """
    A base-image / metadata failure produces no step output of its own — the
    `#N ERROR:` line carries the only message there is.

    Regression: five apps died on a Docker Hub 500 and every one of them reported
    its cause as "[internal] load metadata for docker.io/library/debian:trixie-slim"
    — the step's NAME, not the error.
    """
    out = (
        "#1 [internal] load build definition from Dockerfile\n"
        "#1 DONE 0.0s\n"
        "#2 [internal] load metadata for docker.io/library/debian:trixie-slim\n"
        "#2 ERROR: unexpected status from HEAD request to "
        "https://registry-1.docker.io/v2/library/debian/manifests/trixie-slim: "
        "500 Internal Server Error\n"
    )
    error = _extract_build_error(out)
    assert "500 Internal Server Error" in error
    assert "load metadata" not in error


def test_transient_registry_error_is_retryable():
    """A 5xx from the registry is an upstream outage — retry, don't fail the app."""
    out = (
        "#2 [internal] load metadata for docker.io/library/debian:trixie-slim\n"
        "#2 ERROR: unexpected status from HEAD request to "
        "https://registry-1.docker.io/v2/library/debian/manifests/trixie-slim: "
        "500 Internal Server Error\n"
        "ERROR: failed to solve: failed to resolve source metadata for "
        "docker.io/library/debian:trixie-slim\n"
    )
    assert _is_transient_registry_error(out) is True


def test_app_emitted_5xx_is_not_mistaken_for_a_registry_outage():
    """
    A 5xx printed by the app's OWN build must not be silently retried: the
    symptom alone is not enough, a registry context must be present too.
    """
    out = (
        "#7 12.3 curl: warning: server replied 503 Service Unavailable\n"
        "#7 12.4 test failed: expected 200, got 500 Internal Server Error\n"
        '#7 ERROR: process "/bin/sh -c ./run-tests.sh" did not complete '
        "successfully: exit code: 1\n"
    )
    assert _is_transient_registry_error(out) is False


def test_app_download_eof_not_mistaken_for_registry_outage():
    """
    Regression (mediawiki): an app RUN step whose ``curl | tar`` download is
    truncated prints "Unexpected EOF in archive". The log ALSO carries the
    ambient "load metadata for docker.io/..." line that every build has — so the
    whole-log check wrongly saw registry context + a transient EOF and retried
    the build 3x uselessly. The classification must scope to the FAILING step.
    """
    out = (
        "#2 [internal] load metadata for docker.io/library/debian:trixie-slim\n"
        "#2 DONE 0.0s\n"
        "#9 [5/9] RUN curl -fsSL .../mediawiki-1.41.2.tar.gz | tar xz\n"
        "#9 75.20 curl: (92) HTTP/2 stream 1 was not closed cleanly: CANCEL\n"
        "#9 75.21 gzip: stdin: unexpected end of file\n"
        "#9 75.21 tar: Unexpected EOF in archive\n"
        "#9 75.21 tar: Error is not recoverable: exiting now\n"
        '#9 ERROR: process "/bin/sh -c curl ... | tar xz" did not complete '
        "successfully: exit code: 2\n"
    )
    assert _is_transient_registry_error(out) is False


def test_extract_build_error_reports_doctor_check_not_trailing_boilerplate():
    """
    A CLI doctor-style "[failed]" line is the root cause — not the trailing
    "refer to the docs" boilerplate that used to win as the last line.
    """
    out = (
        "#10 1.9 [08:41:26] Checking system Node.js version - found v20.20.2 [failed]\n"
        "#10 1.9 The version of Node.js you are using is not supported.\n"
        "#10 2.0 You can always refer to https://ghost.org/docs/ for troubleshooting.\n"
        '#10 ERROR: process "/bin/sh -c ghost install" did not complete'
        " successfully: exit code: 1\n"
    )
    error = _extract_build_error(out)
    assert "[failed]" in error
    assert "refer to" not in error


def test_build_failure_message_is_concise_with_pointer(tmp_path, monkeypatch):
    """
    The raised Abort carries the root-cause line + a `--build` pointer, NOT the
    full backtrace (which now lives once in build.log).
    """
    monkeypatch.setattr("hop3.plugins.docker.builder.APP_ROOT", tmp_path)
    builder = MagicMock()
    builder.app_name = "myapp"
    # Use the REAL _save_build_log so we can assert the full output is persisted.
    builder._save_build_log = DockerBuilder._save_build_log.__get__(builder)

    huge = "\n".join(f"trace line {i}" for i in range(500))
    err = subprocess.CalledProcessError(1, "docker build")
    err.stderr = (
        "Redis::CannotConnectError: Error connecting to Redis on localhost:6379\n"
        + huge
    )
    err.stdout = ""

    with pytest.raises(Abort) as exc:
        DockerBuilder._handle_build_failure(builder, err, "img:tag", 0.0)

    msg = str(exc.value)
    assert "Redis::CannotConnectError" in msg
    assert "hop3 app logs --app myapp --build" in msg
    assert "trace line 400" not in msg  # backtrace is NOT re-dumped in the error
    # the full output IS persisted once, to build.log
    build_log = (tmp_path / "myapp" / "log" / "build.log").read_text()
    assert "trace line 499" in build_log
