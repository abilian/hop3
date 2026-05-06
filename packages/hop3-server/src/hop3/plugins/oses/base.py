# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Base implementation for OS setup strategies."""

from __future__ import annotations

import re
import subprocess
from io import StringIO
from pathlib import Path

# Allowed shape for distro package names. Covers everything the PACKAGES
# lists in this package use today (alphanumerics plus ``.``, ``_``, ``+``,
# ``@`` for Homebrew like ``python@3.11``, and ``-`` *only* in non-leading
# position) while rejecting every shell metacharacter.
#
# The first-character restriction is the load-bearing part: leaving ``-``
# in leading position would let a regression sneak in an argument-injection
# string like ``"--reinstall"`` (apt and friends happily accept it).
_PACKAGE_NAME_RE = re.compile(r"^[A-Za-z0-9_+.@][A-Za-z0-9._+@-]*$")


class BaseOSStrategy:
    """Base class providing common functionality for OS setup strategies.

    This provides default implementations for common operations like
    creating users, putting files, and creating symbolic links.
    """

    name: str = "base"

    @property
    def display_name(self) -> str:
        """Human-readable name for this OS.

        Subclasses should override this property to provide a specific display name.
        """
        return "Base OS"

    @property
    def packages(self) -> list[str]:
        """List of system packages required for hop3.

        Subclasses should override this property to provide OS-specific packages.
        """
        return []

    HOP3_USER = "hop3"
    HOME_DIR = f"/home/{HOP3_USER}"
    VENV = f"{HOME_DIR}/venv"
    HOP_SCRIPT = f"{VENV}/bin/hop3-server"

    def detect(self) -> bool:
        """Default implementation returns False.

        Subclasses should override this to detect their specific OS.
        """
        return False

    def setup_server(self) -> None:
        """Default setup implementation.

        Subclasses can override or call super() and add OS-specific setup.
        """
        msg = "Subclasses must implement setup_server()"
        raise NotImplementedError(msg)

    def ensure_packages(self, packages: list[str], *, update: bool = True) -> None:
        """Install packages - must be overridden by subclasses."""
        msg = "Subclasses must implement ensure_packages()"
        raise NotImplementedError(msg)

    @staticmethod
    def _validate_package_names(packages: list[str]) -> None:
        """Reject any package name that contains shell metacharacters.

        Today every concrete OS strategy passes a static module-level
        ``PACKAGES`` list to ``ensure_packages``. That contract is *not*
        enforced by the type system — and one regression that piped a
        user-controlled string through here would turn this module into
        a remote-code-execution sink (``subprocess.run([pkg_mgr,
        "install", "-y", *packages])`` happily executes whatever the
        package manager interprets, and many accept ``--`` and similar
        argument-injection escapes).

        Validate eagerly. The check is cheap and the assertion gives
        future maintainers a loud failure rather than a silent injection.
        """
        for pkg in packages:
            if not _PACKAGE_NAME_RE.fullmatch(pkg):
                msg = f"Refusing unsafe package name: {pkg!r}"
                raise ValueError(msg)

    def ensure_user(self, user: str, home: str, shell: str, group: str) -> None:
        """Create a system user if it doesn't exist.

        This provides a default implementation using useradd that works
        on most Linux systems.
        """
        # Check if user exists
        try:
            subprocess.run(
                ["id", user],
                check=True,
                capture_output=True,
                text=True,
            )
            # User exists, nothing to do
            return
        except subprocess.CalledProcessError:
            # User doesn't exist, create it
            pass

        # Create user with home directory
        subprocess.run(
            [
                "useradd",
                "-m",  # Create home directory
                "-d",
                home,  # Home directory path
                "-s",
                shell,  # Default shell
                "-g",
                group,  # Primary group
                user,  # Username
            ],
            check=True,
            capture_output=True,
            text=True,
        )

    def put_file(
        self,
        name: str,
        src: Path | str | StringIO,
        dest: str,
        *,
        mode: int | None = None,
        owner: str | None = None,
        group: str | None = None,
    ) -> None:
        """Copy content from source to destination file.

        Args:
            name: Description of the operation (for logging)
            src: Source - can be Path, string path, or StringIO
            dest: Destination file path
            mode: Optional file mode (permissions)
            owner: Optional file owner
            group: Optional file group
        """
        match src:
            case Path():
                Path(dest).write_text(src.read_text())
            case str():
                Path(dest).write_text(Path(src).read_text())
            case StringIO():
                Path(dest).write_text(src.getvalue())
            case _:
                msg = f"Invalid src type: {type(src)}"
                raise ValueError(msg)

        # TODO: Implement mode, owner, group setting

    def ensure_link(self, name: str, path: str, target: str) -> None:
        """Create a symbolic link.

        Args:
            name: Description of the operation (for logging)
            path: Destination path for the symlink
            target: File or directory the symlink points to
        """
        # Remove existing symlink or file
        if Path(path).exists() or Path(path).is_symlink():
            Path(path).unlink()

        # Create new symlink
        Path(path).symlink_to(target)

    def read_os_release(self) -> dict[str, str]:
        """Parse /etc/os-release and return as dictionary.

        Returns:
            Dictionary with keys like 'ID', 'VERSION_ID', 'NAME', etc.
        """
        os_info = {}
        try:
            with Path("/etc/os-release").open() as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    # Remove quotes
                    value = value.strip('"').strip("'")
                    os_info[key] = value
        except FileNotFoundError:
            pass
        return os_info
