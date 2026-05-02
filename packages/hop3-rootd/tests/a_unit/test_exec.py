# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the exec wrapper."""

from __future__ import annotations

import shutil
import subprocess
from unittest.mock import patch

import pytest
from hop3_rootd import exec as rootd_exec
from hop3_rootd.exec import (
    CommandResult,
    CommandTimeoutError,
    InvalidBinaryError,
    run,
)

# --- Argv validation ------------------------------------------------------


def test_run_rejects_empty_argv():
    with pytest.raises(ValueError, match="non-empty"):
        run([])


def test_run_rejects_non_list_argv():
    with pytest.raises(TypeError, match="must be a list"):
        run("/usr/sbin/nft list")  # type: ignore[arg-type]


def test_run_rejects_argv_with_non_strings():
    with pytest.raises(TypeError, match="only strings"):
        run(["/usr/sbin/nft", 42])  # type: ignore[list-item]


def test_run_rejects_binary_not_on_allowlist():
    with pytest.raises(InvalidBinaryError) as e:
        run(["/bin/sh", "-c", "echo hi"])
    assert "/bin/sh" in str(e.value)


def test_run_rejects_relative_binary():
    """Relative paths (anything not in allow-list) are rejected."""
    with pytest.raises(InvalidBinaryError):
        run(["nft", "list", "ruleset"])


def test_run_rejects_binary_not_present():
    """Allow-list path that doesn't exist on this system."""
    # Patch ALLOWED_BINARIES to include a non-existent path
    fake_path = "/this/path/does/not/exist/for/sure"
    with patch.object(rootd_exec, "ALLOWED_BINARIES", frozenset({fake_path})):
        with pytest.raises(InvalidBinaryError, match="not present on filesystem"):
            run([fake_path, "--help"])


# --- Successful execution (using mocked subprocess) -----------------------


@pytest.fixture
def fake_allowlist(tmp_path):
    """Create a fake binary file and patch ALLOWED_BINARIES to include it."""
    fake = tmp_path / "fakebin"
    fake.write_text("#!/bin/sh\nexit 0\n")
    fake.chmod(0o755)
    with patch.object(rootd_exec, "ALLOWED_BINARIES", frozenset({str(fake)})):
        yield str(fake)


def test_run_returns_command_result(fake_allowlist):
    """Smoke test that the wrapper produces a CommandResult."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = b"hello"
        mock_run.return_value.stderr = b""
        result = run([fake_allowlist, "arg1"])

    assert isinstance(result, CommandResult)
    assert result.argv == [fake_allowlist, "arg1"]
    assert result.returncode == 0
    assert result.stdout == "hello"
    assert result.stderr == ""
    assert result.success


def test_run_captures_nonzero_exit_without_check(fake_allowlist):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 2
        mock_run.return_value.stdout = b""
        mock_run.return_value.stderr = b"oops"
        result = run([fake_allowlist])

    assert result.returncode == 2
    assert result.stderr == "oops"
    assert not result.success


def test_run_passes_no_shell(fake_allowlist):
    """`shell=True` must NEVER be set, regardless of caller intent."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = b""
        mock_run.return_value.stderr = b""
        run([fake_allowlist])

    # Inspect the actual subprocess.run kwargs
    _, kwargs = mock_run.call_args
    assert kwargs["shell"] is False


def test_run_passes_explicit_timeout(fake_allowlist):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = b""
        mock_run.return_value.stderr = b""
        run([fake_allowlist], timeout=5.0)

    _, kwargs = mock_run.call_args
    assert kwargs["timeout"] == 5.0


def test_run_passes_default_timeout(fake_allowlist):
    """Default timeout is 30s (DEFAULT_TIMEOUT_SECONDS)."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = b""
        mock_run.return_value.stderr = b""
        run([fake_allowlist])

    _, kwargs = mock_run.call_args
    assert kwargs["timeout"] == 30.0


def test_run_decodes_bytes_to_utf8(fake_allowlist):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "héllo".encode()
        mock_run.return_value.stderr = b""
        result = run([fake_allowlist])

    assert result.stdout == "héllo"


def test_run_handles_invalid_utf8_gracefully(fake_allowlist):
    """Replacement chars are inserted, no exception."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = b"\xff\xfe invalid"
        mock_run.return_value.stderr = b""
        result = run([fake_allowlist])

    # No raised exception; replacement char(s) present
    assert "invalid" in result.stdout


# --- Timeout behaviour ----------------------------------------------------


def test_run_raises_command_timeout_error(fake_allowlist):
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=[fake_allowlist], timeout=5.0
        )
        with pytest.raises(CommandTimeoutError) as e:
            run([fake_allowlist], timeout=5.0)
    assert e.value.timeout == 5.0
    assert e.value.argv == [fake_allowlist]


# --- check=True behaviour -------------------------------------------------


def test_run_check_true_propagates_calledprocesserror(fake_allowlist):
    """When check=True is set, CalledProcessError bubbles out."""
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1, cmd=[fake_allowlist]
        )
        with pytest.raises(subprocess.CalledProcessError):
            run([fake_allowlist], check=True)


# --- stdin and env passing ------------------------------------------------


def test_run_passes_stdin_data(fake_allowlist):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = b""
        mock_run.return_value.stderr = b""
        run([fake_allowlist], stdin_data=b"hello\n")

    _, kwargs = mock_run.call_args
    assert kwargs["input"] == b"hello\n"


def test_run_overlays_extra_env(fake_allowlist):
    """extra_env is merged on top of os.environ; doesn't replace it."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = b""
        mock_run.return_value.stderr = b""
        run([fake_allowlist], extra_env={"NFT_TEST_VAR": "1"})

    _, kwargs = mock_run.call_args
    env = kwargs["env"]
    assert env is not None
    assert env["NFT_TEST_VAR"] == "1"
    # Other env vars are preserved (e.g. PATH)
    assert "PATH" in env


def test_run_no_env_when_extra_env_not_set(fake_allowlist):
    """If extra_env=None (default), env=None is passed (subprocess uses parent)."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = b""
        mock_run.return_value.stderr = b""
        run([fake_allowlist])

    _, kwargs = mock_run.call_args
    assert kwargs["env"] is None


# --- Real-binary smoke test (uses /usr/bin/systemctl which is in allow-list)
# Only runs if systemctl is actually present (skipped on dev macs without it).


def test_real_binary_smoke():
    sysctl_path = shutil.which("systemctl")
    if sysctl_path is None:
        pytest.skip("systemctl not present on this system")
    # Use systemctl --version which is harmless and quick.
    if sysctl_path not in rootd_exec.ALLOWED_BINARIES:
        pytest.skip(f"systemctl path {sysctl_path} not in allowlist")
    result = run([sysctl_path, "--version"], timeout=5.0)
    assert result.success
    assert "systemd" in result.stdout.lower()
