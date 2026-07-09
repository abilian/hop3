# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Common utilities shared between CLI and server installers.

This module contains:
- Terminal output utilities (colors, printing)
- Spinner for long-running operations
- Command execution helpers
- System detection utilities

All code uses only the Python standard library.
"""

from __future__ import annotations

import datetime
import itertools
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Self, TypedDict, overload

# Argv tokens we'll redact when stringifying a CommandError. Defense in
# depth: the right fix is to keep secrets off argv at the call site (we
# did that for mysqldump and the deployer), but if a future caller
# regresses, this prevents the password from landing in error output
# and any log that catches it.
_REDACT_TOKEN_RE = re.compile(
    r"^("
    r"-p[^\s]+"  # mysql/mariadb-style "-pSECRET"
    r"|--password=.+"  # generic --password=SECRET
    r"|--password-file=.+"
    r"|--token=.+"
    r"|--api-token=.+"
    r")$",
    re.IGNORECASE,
)


def _redact_argv(cmd: list[str]) -> list[str]:
    """Return a copy of ``cmd`` with secret-bearing tokens replaced.

    Conservative: only matches well-known password/token flag shapes
    so we don't redact innocuous flags that happen to look similar.
    """
    out: list[str] = []
    redact_next = False
    for token in cmd:
        if redact_next:
            out.append("***REDACTED***")
            redact_next = False
            continue
        if _REDACT_TOKEN_RE.match(token):
            # Single-token form like "-pSECRET" or "--password=SECRET"
            head, sep, _ = token.partition("=")
            if sep:
                out.append(f"{head}=***REDACTED***")
            else:
                out.append(f"{token[:2]}***REDACTED***")
            continue
        if token in {"--password", "--password-file", "--token", "--api-token"}:
            # Two-token form like "--password SECRET" — redact the next.
            out.append(token)
            redact_next = True
            continue
        out.append(token)
    return out


# =============================================================================
# Terminal Colors
# =============================================================================


class Colors:
    """ANSI color codes for terminal output."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[0;33m"
    BLUE = "\033[0;34m"
    CYAN = "\033[0;36m"

    @classmethod
    def disable(cls) -> None:
        """Disable all colors (for non-TTY output)."""
        for attr in ["RESET", "BOLD", "DIM", "RED", "GREEN", "YELLOW", "BLUE", "CYAN"]:
            setattr(cls, attr, "")


# Disable colors if not a TTY
if not sys.stdout.isatty():
    Colors.disable()


# =============================================================================
# Output Functions
# =============================================================================


def print_header(title: str) -> None:
    """Print a styled header."""
    print()
    print(f"{Colors.BOLD}{Colors.CYAN}{title}{Colors.RESET}")
    print(f"{Colors.DIM}{'=' * len(title)}{Colors.RESET}")
    print()


def print_step(step: int, total: int, message: str) -> None:
    """Print a step indicator."""
    print(f"\n{Colors.BOLD}[{step}/{total}]{Colors.RESET} {message}")


def print_success(message: str) -> None:
    """Print a success message."""
    print(f"      {Colors.GREEN}✓{Colors.RESET} {message}")


def print_info(message: str) -> None:
    """Print an info message."""
    print(f"      {Colors.BLUE}ℹ{Colors.RESET} {message}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    print(f"      {Colors.YELLOW}⚠{Colors.RESET} {message}")


def print_error(message: str) -> None:
    """Print an error message."""
    print(f"      {Colors.RED}✗{Colors.RESET} {message}", file=sys.stderr)


def print_detail(message: str) -> None:
    """Print a detail/sub-item."""
    print(f"        {Colors.DIM}{message}{Colors.RESET}")


# =============================================================================
# Spinner for Long Operations
# =============================================================================


class Spinner:
    """A simple terminal spinner for long-running operations.

    Usage:
        with Spinner("Installing packages..."):
            # long operation
            pass
    """

    CHARS = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, message: str):
        self.message = message
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> Self:
        if sys.stdout.isatty():
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._spin, daemon=True)
            self._thread.start()
        else:
            print(f"      ... {self.message}")
        return self

    def __exit__(self, *args) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=0.5)
        if sys.stdout.isatty():
            # Clear the spinner line
            print(f"\r{' ' * (len(self.message) + 12)}\r", end="")

    def _spin(self) -> None:
        for char in itertools.cycle(self.CHARS):
            if self._stop_event.is_set():
                break
            print(
                f"\r      {Colors.CYAN}{char}{Colors.RESET} {self.message}",
                end="",
                flush=True,
            )
            time.sleep(0.08)


# =============================================================================
# Command Execution
# =============================================================================


@dataclass
class CommandResult:
    """Result of a command execution."""

    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def success(self) -> bool:
        """Check if the command succeeded."""
        return self.returncode == 0

    @classmethod
    def from_subprocess(cls, result: subprocess.CompletedProcess) -> CommandResult:
        """Create CommandResult from subprocess.CompletedProcess.

        Args:
            result: Completed subprocess result

        Returns:
            CommandResult instance
        """
        return cls(
            returncode=result.returncode,
            stdout=result.stdout or "",
            stderr=result.stderr or "",
        )


@dataclass
class CommandError(Exception):
    """Raised when a command fails."""

    cmd: list[str]
    returncode: int
    stderr: str
    stdout: str = ""

    def __str__(self) -> str:
        return f"Command failed: {' '.join(_redact_argv(self.cmd))}"


class ServiceStartError(Exception):
    """Raised when a service fails to start."""


def run_cmd(
    cmd: list[str],
    *,
    capture: bool = True,
    check: bool = True,
    env: dict[str, str] | None = None,
    timeout: float | None = None,
) -> subprocess.CompletedProcess:
    """Run a command and return the result.

    Args:
        cmd: Command and arguments to run
        capture: Whether to capture stdout/stderr
        check: Whether to raise CommandError on non-zero exit
        env: Additional environment variables
        timeout: Timeout in seconds (None for no timeout)

    Returns:
        CompletedProcess with returncode, stdout, stderr

    Raises:
        CommandError: If check=True and command returns non-zero
    """
    run_env = os.environ.copy()
    if env:
        run_env.update(env)

    try:
        result = subprocess.run(
            cmd,
            check=False,
            capture_output=capture,
            text=True,
            env=run_env,
            timeout=timeout,
            # No inherited stdin: a command that tries to prompt (a dpkg
            # conffile question, an apt confirmation) gets EOF and fails fast
            # instead of blocking forever on a terminal the installer may not
            # have. (needrestart's whiptail reads /dev/tty, not stdin -- that
            # one is handled by NEEDRESTART_MODE=a in the apt environment.)
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        # Return a failed result on timeout
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=-1,
            stdout="",
            stderr="Command timed out",
        )
    except FileNotFoundError:
        # Missing executable is a normal command failure (exit 127, "command
        # not found"), not an uncaught crash — e.g. the installer's service
        # checks run `supervisorctl` on a host that has neither systemd nor
        # supervisor. Falls through so check=False callers read the returncode
        # and check=True callers still raise below.
        result = subprocess.CompletedProcess(
            args=cmd,
            returncode=127,
            stdout="",
            stderr=f"command not found: {cmd[0]}",
        )

    if check and result.returncode != 0:
        raise CommandError(
            cmd=cmd,
            returncode=result.returncode,
            stderr=result.stderr or "",
            stdout=result.stdout or "",
        )

    return result


def cmd_exists(cmd: str) -> bool:
    """Check if a command exists in PATH."""
    return shutil.which(cmd) is not None


def has_systemd() -> bool:
    """Return True if systemd is the init system (PID 1).

    Reads ``/proc/1/comm`` — unambiguous on Linux. The systemd
    *package* may install ``systemctl`` and create ``/run/systemd``
    even when systemd isn't actually running (e.g. Docker test
    containers using supervisord). Likewise, ``systemctl
    is-system-running`` returns "offline" with exit code 1 in that
    case, which is easy to mis-interpret as "alive".

    PID 1 is either ``systemd`` or it isn't, so this is the
    cheapest reliable check.
    """
    try:
        comm = Path("/proc/1/comm").read_text().strip()
    except OSError:
        return False
    return comm == "systemd"


# =============================================================================
# System Detection
# =============================================================================


@dataclass
class DistroInfo:
    """Detailed Linux distribution information.

    Attributes:
        family: Distribution family ("debian", "fedora", "arch", "unknown")
        distro: Specific distribution ID (e.g., "debian", "ubuntu", "fedora")
        version: Version number (e.g., "12", "24.04", "41")
        codename: Version codename (e.g., "bookworm", "noble", "trixie")
    """

    family: str
    distro: str
    version: str
    codename: str

    def __str__(self) -> str:
        """Return human-readable string."""
        if self.codename:
            return f"{self.distro} {self.version} ({self.codename})"
        return f"{self.distro} {self.version}"

    @property
    def is_debian(self) -> bool:
        """Check if this is Debian (not Ubuntu or other derivatives)."""
        return self.distro == "debian"

    @property
    def is_ubuntu(self) -> bool:
        """Check if this is Ubuntu."""
        return self.distro == "ubuntu"

    @property
    def version_major(self) -> int:
        """Get major version number (e.g., 12 for Debian 12, 24 for Ubuntu 24.04)."""
        try:
            return int(self.version.split(".")[0])
        except (ValueError, IndexError):
            return 0


def _parse_os_release() -> dict[str, str]:
    """Parse /etc/os-release file into a dictionary."""
    result: dict[str, str] = {}
    os_release = Path("/etc/os-release")
    if not os_release.exists():
        return result

    for line in os_release.read_text().splitlines():
        line = line.strip()
        if "=" in line:
            key, value = line.split("=", 1)
            result[key] = value.strip('"').lower()
    return result


def _parse_lsb_release() -> dict[str, str]:
    """Parse lsb_release command output as fallback."""
    result: dict[str, str] = {}
    try:
        proc = subprocess.run(
            ["lsb_release", "-a"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            return result
        for line in proc.stdout.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                result[key.strip()] = value.strip().lower()
    except FileNotFoundError:
        pass
    return result


def _determine_family(distro: str, id_like: str) -> str:
    """Determine distribution family from distro ID and ID_LIKE."""
    debian_distros = {"debian", "ubuntu", "mint", "pop", "linuxmint"}
    fedora_distros = {"fedora", "rhel", "centos", "rocky", "almalinux"}

    if distro in debian_distros or "debian" in id_like or "ubuntu" in id_like:
        return "debian"
    if distro in fedora_distros or "fedora" in id_like or "rhel" in id_like:
        return "fedora"
    if distro == "arch" or "arch" in id_like:
        return "arch"
    return "unknown"


def detect_distro_info() -> DistroInfo:
    """Detect detailed Linux distribution information.

    Parses /etc/os-release to get distribution ID, version, and codename.
    Falls back to lsb_release command if /etc/os-release is incomplete.

    Returns:
        DistroInfo with family, distro, version, and codename.
    """
    # Parse /etc/os-release (standard on modern Linux)
    os_info = _parse_os_release()
    distro = os_info.get("ID", "")
    version = os_info.get("VERSION_ID", "")
    codename = os_info.get("VERSION_CODENAME", "")
    id_like = os_info.get("ID_LIKE", "")

    # Fallback to lsb_release if needed
    if not distro or not version:
        lsb_info = _parse_lsb_release()
        distro = distro or lsb_info.get("Distributor ID", "")
        version = version or lsb_info.get("Release", "")
        codename = codename or lsb_info.get("Codename", "")

    family = _determine_family(distro, id_like)

    return DistroInfo(
        family=family,
        distro=distro,
        version=version,
        codename=codename,
    )


def detect_distro() -> str:
    """Detect the Linux distribution family.

    Returns:
        'debian' for Debian-based distros (Ubuntu, Mint, Pop!_OS)
        'fedora' for Red Hat-based distros (Fedora, RHEL, CentOS, Rocky, Alma)
        'arch' for Arch Linux
        'unknown' for unrecognized distributions

    Note:
        For detailed information, use detect_distro_info() instead.
    """
    return detect_distro_info().family


def get_current_shell() -> str | None:
    """Detect the current shell.

    Returns:
        'bash', 'zsh', 'fish', or None if unrecognized
    """
    shell = os.environ.get("SHELL", "")
    if "zsh" in shell:
        return "zsh"
    if "fish" in shell:
        return "fish"
    if "bash" in shell:
        return "bash"
    return None


# =============================================================================
# Version Check Helper
# =============================================================================


MIN_PYTHON = (3, 10)


def find_project_root(start_path: Path | None = None) -> Path:
    """Find the project root directory.

    Walks up from the starting path looking for pyproject.toml and packages/ directory.

    Args:
        start_path: Path to start searching from. If None, uses current working directory.

    Returns:
        Path to project root, or current working directory if not found.
    """
    current = start_path or Path.cwd()

    for parent in [current, *current.parents]:
        if (parent / "pyproject.toml").exists() and (parent / "packages").exists():
            return parent
        if (parent / ".git").exists() and (parent / "packages").exists():
            return parent

    return Path.cwd()


def check_python_version() -> None:
    """Check that Python version meets minimum requirements.

    Exits with error message if Python version is too old.
    """
    if sys.version_info < MIN_PYTHON:
        print(f"Error: Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ required")
        print(f"Found: Python {sys.version_info.major}.{sys.version_info.minor}")
        print()
        print("Please install a newer Python version:")
        print("  Ubuntu/Debian: sudo apt install python3.11")
        print("  Fedora:        sudo dnf install python3.11")
        print("  macOS:         brew install python@3.11")
        sys.exit(1)


# =============================================================================
# Environment Variable Helpers
# =============================================================================


@overload
def env_str(name: str) -> str | None: ...


@overload
def env_str(name: str, default: str) -> str: ...


def env_str(name: str, default: str | None = None) -> str | None:
    """Get a string environment variable.

    Args:
        name: Environment variable name.
        default: Default value if not set.

    Returns:
        The environment variable value, or default if not set.
        When default is a str, return type is str.
        When default is None (or omitted), return type is str | None.
    """
    return os.environ.get(name, default)


def env_bool(name: str) -> bool:
    """Get a boolean environment variable.

    Recognizes "1" and "true" (case-insensitive) as True.

    Args:
        name: Environment variable name.

    Returns:
        True if set to "1" or "true", False otherwise.
    """
    return os.environ.get(name, "").lower() in {"1", "true"}


def env_path(name: str, default: Path) -> Path:
    """Get a Path environment variable.

    Args:
        name: Environment variable name.
        default: Default Path if not set.

    Returns:
        Path from environment variable, or default.
    """
    value = os.environ.get(name)
    return Path(value) if value else default


def env_list(name: str, separator: str = ",") -> list[str]:
    """Get a list from a separated environment variable.

    Args:
        name: Environment variable name.
        separator: Separator character (default: comma).

    Returns:
        List of stripped, non-empty values.
    """
    value = os.environ.get(name, "")
    return [item.strip() for item in value.split(separator) if item.strip()]


# =============================================================================
# File System Helpers
# =============================================================================


def create_symlink(source: Path, target: Path) -> bool:
    """Create a symlink from target to source, replacing existing.

    Args:
        source: Path that the symlink should point to
        target: Path where the symlink will be created

    Returns:
        True if symlink created successfully, False otherwise
    """
    if not source.exists():
        return False

    # Remove existing symlink or file
    if target.exists() or target.is_symlink():
        target.unlink()

    try:
        target.symlink_to(source)
        return True
    except OSError:
        return False


# =============================================================================
# Build provenance (deploy-time manifest)
# =============================================================================


class GitProvenance(TypedDict):
    """Git provenance for a working tree. Any value may be None."""

    git_commit: str | None
    git_branch: str | None
    git_dirty: bool | None


def collect_git_provenance(repo_dir: Path) -> GitProvenance:
    """Collect git commit / branch / dirty state for a working tree.

    Runs git inside ``repo_dir`` (git searches upward for the repo root, so a
    package subdirectory works). Returns a dict with keys ``git_commit``,
    ``git_branch`` and ``git_dirty`` — any of which may be None when git is
    unavailable or the directory isn't a checkout.
    """

    def _git(*args: str) -> tuple[int, str]:
        try:
            result = subprocess.run(
                ["git", "-C", str(repo_dir), *args],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return 1, ""
        return result.returncode, result.stdout.strip()

    commit_rc, commit = _git("rev-parse", "HEAD")
    _, branch = _git("rev-parse", "--abbrev-ref", "HEAD")

    dirty: bool | None = None
    if commit_rc == 0:
        status_rc, status = _git("status", "--porcelain")
        if status_rc == 0:
            # Empty output == clean; any line == dirty.
            dirty = bool(status)

    return {
        "git_commit": commit or None if commit_rc == 0 else None,
        "git_branch": branch or None,
        "git_dirty": dirty,
    }


def make_build_info(
    *,
    deploy_method: str,
    version: str | None,
    deployed_by: str,
    git_commit: str | None = None,
    git_branch: str | None = None,
    git_dirty: bool | None = None,
) -> dict:
    """Build the deploy-provenance manifest written to ``BUILD_INFO_PATH``.

    A single schema so the installer and the deployer agree on keys and
    ``hop3 system info`` can read either's output. ``deployed_by`` records
    which tool wrote it (``hop3-deploy`` / ``hop3-install``).
    """
    return {
        "version": version,
        "deploy_method": deploy_method,
        "git_commit": git_commit,
        "git_branch": git_branch,
        "git_dirty": git_dirty,
        "deployed_by": deployed_by,
        # Module-qualified: the single-file bundler rewrites
        # ``from datetime import datetime`` to ``import datetime``, so the bare
        # name would resolve to the module in the bundled installer.
        "deployed_at": datetime.datetime.now(datetime.UTC).isoformat(
            timespec="seconds"
        ),
    }
