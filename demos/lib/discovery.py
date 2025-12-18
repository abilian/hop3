# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Demo discovery and resolution."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from lib.context import DemoInfo
from lib.output import print_error

if TYPE_CHECKING:
    from collections.abc import Sequence

# Demos directory (parent of lib/)
DEMOS_DIR = Path(__file__).parent.parent


def discover_demos(
    demo_dirs: Sequence[Path] | None = None,
) -> dict[str, tuple[str, str, Path]]:
    """Discover available built-in demos.

    Args:
        demo_dirs: Additional directories to search for demos.

    Returns:
        Dict mapping demo name to (title, description, location) tuple.
    """
    demos: dict[str, tuple[str, str, Path]] = {}

    # Search in main demos directory
    search_dirs = [DEMOS_DIR]
    if demo_dirs:
        search_dirs.extend(demo_dirs)

    for search_dir in search_dirs:
        if not search_dir.is_dir():
            continue

        for path in sorted(search_dir.iterdir()):
            if path.is_dir() and path.name.startswith("demo"):
                script = path / "demo-script.py"
                if script.exists():
                    title, description = _extract_demo_metadata(script)
                    if not title:
                        title = path.name
                    demos[path.name] = (title, description, path)

    return demos


def _extract_demo_metadata(script: Path) -> tuple[str, str]:
    """Extract TITLE and DESCRIPTION from a demo script.

    Returns:
        Tuple of (title, description).
    """
    title = ""
    description = ""
    try:
        content = script.read_text()
        for line in content.split("\n"):
            if line.startswith("TITLE"):
                title = line.split("=", 1)[1].strip().strip("\"'")
            elif line.startswith("DESCRIPTION"):
                description = line.split("=", 1)[1].strip().strip("\"'")
                break
    except Exception:
        pass
    return title, description


def get_demo_info(demo_name: str, demo_path: Path) -> DemoInfo | None:
    """Get detailed information about a demo.

    Args:
        demo_name: Name of the demo
        demo_path: Path to the demo directory

    Returns:
        DemoInfo with full details, or None if unable to read.
    """
    script = demo_path / "demo-script.py"
    if not script.exists():
        return None

    # Default values
    title = demo_name
    description = ""
    app_name = ""
    app_type = "unknown"
    app_subdir = None

    # Parse demo script
    try:
        content = script.read_text()
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("TITLE"):
                title = line.split("=", 1)[1].strip().strip("\"'")
            elif line.startswith("DESCRIPTION"):
                description = line.split("=", 1)[1].strip().strip("\"'")
            elif line.startswith("APP_NAME"):
                app_name = line.split("=", 1)[1].strip().strip("\"'")
            elif line.startswith("APP_DIR") and "/" in line:
                # Extract subdirectory from APP_DIR = Path(...) / "subdir"
                match = re.search(r'/\s*["\']([^"\']+)["\']', line)
                if match:
                    app_subdir = match.group(1)
    except Exception:
        pass

    # Resolve actual app directory
    app_dir_resolved = demo_path
    if app_subdir:
        candidate = demo_path / app_subdir
        if candidate.exists():
            app_dir_resolved = (
                candidate.resolve() if candidate.is_symlink() else candidate
            )

    # List files in demo directory
    files = [
        f.name
        for f in demo_path.iterdir()
        if f.name not in {"__pycache__", ".git", ".gitignore"}
    ]

    # Detect app type
    app_type = _detect_app_type(app_dir_resolved)

    # Check for symlinks
    is_symlink, symlink_target = _check_symlink(demo_path, app_subdir)

    return DemoInfo(
        name=demo_name,
        title=title,
        description=description,
        app_name=app_name,
        app_dir=demo_path,
        app_type=app_type,
        files=sorted(files),
        location=demo_path,
        is_symlink=is_symlink,
        symlink_target=symlink_target,
    )


def _detect_app_type(app_dir: Path) -> str:
    """Detect application type from directory contents."""
    if (app_dir / "Dockerfile").exists():
        return "docker"
    if (app_dir / "requirements.txt").exists():
        return "python"
    if (app_dir / "pyproject.toml").exists():
        return "python-poetry"
    if (app_dir / "package.json").exists():
        return "nodejs"
    if (app_dir / "go.mod").exists() or any(
        f.name.endswith(".go") for f in app_dir.iterdir() if f.is_file()
    ):
        return "golang"
    if (app_dir / "Gemfile").exists():
        return "ruby"
    if (
        (app_dir / "index.html").exists()
        or (app_dir / "public").is_dir()
        or any(f.name.endswith(".html") for f in app_dir.iterdir() if f.is_file())
    ):
        return "static"
    return "unknown"


def _check_symlink(demo_path: Path, app_subdir: str | None) -> tuple[bool, str | None]:
    """Check if demo or app subdirectory is a symlink.

    Returns:
        Tuple of (is_symlink, symlink_target).
    """
    is_symlink = demo_path.is_symlink()
    symlink_target = None

    if is_symlink:
        try:
            symlink_target = str(demo_path.resolve().relative_to(DEMOS_DIR.parent))
        except ValueError:
            symlink_target = str(demo_path.resolve())
    elif app_subdir:
        candidate = demo_path / app_subdir
        if candidate.is_symlink():
            is_symlink = True
            try:
                symlink_target = str(candidate.resolve().relative_to(DEMOS_DIR.parent))
            except ValueError:
                symlink_target = str(candidate.resolve())

    return is_symlink, symlink_target


def resolve_demo(
    demo_arg: str,
    demo_dirs: Sequence[Path] | None = None,
) -> tuple[str, Path | None, bool]:
    """Resolve a demo argument to its details.

    Args:
        demo_arg: Demo name (e.g., "demo1") or path (e.g., "~/my-app")
        demo_dirs: Additional directories to search for demos

    Returns:
        Tuple of (display_name, demo_dir, is_generic)
        - display_name: Name to show in output
        - demo_dir: Path to the demo/app directory
        - is_generic: True if this needs the generic demo runner
    """
    # Check if it's a built-in demo name
    builtin_path = DEMOS_DIR / demo_arg
    if builtin_path.is_dir() and (builtin_path / "demo-script.py").exists():
        return (demo_arg, builtin_path, False)

    # Check in additional demo directories
    if demo_dirs:
        for demo_dir in demo_dirs:
            candidate = demo_dir / demo_arg
            if candidate.is_dir():
                if (candidate / "demo-script.py").exists():
                    return (demo_arg, candidate, False)
                return (demo_arg, candidate, True)

    # Check if it's an external path
    expanded_path = Path(demo_arg).expanduser().resolve()
    if expanded_path.is_dir():
        if (expanded_path / "demo-script.py").exists():
            return (expanded_path.name, expanded_path, False)
        return (expanded_path.name, expanded_path, True)

    return (demo_arg, None, False)


def load_demo_module(demo_path: Path):
    """Load a demo script module from a path.

    Args:
        demo_path: Path to the demo-script.py file

    Returns:
        The loaded module, or None on failure.
    """
    import sys

    # Ensure demos directory is in path for demo scripts to use `from lib import ...`
    # (should already be set by demo.py entry point, but just in case)
    demos_dir_str = str(DEMOS_DIR)
    if demos_dir_str not in sys.path:
        sys.path.insert(0, demos_dir_str)

    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location("demo_script", demo_path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception as e:
        print_error(f"Failed to load demo script: {e}")
        return None
