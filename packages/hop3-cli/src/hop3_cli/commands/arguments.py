# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Argument generation for CLI commands."""

from __future__ import annotations

import base64
import io
import sys
import tarfile
from operator import itemgetter
from pathlib import Path
from typing import TYPE_CHECKING

import pathspec

from hop3_cli.core.hop3_toml import read_hop3_toml

if TYPE_CHECKING:
    from hop3_cli.types import JsonDict

__all__ = ["generate_archive", "get_extra_args", "pack_repository"]

# Archive size limits (in bytes)
# Soft limit: warn the user but proceed
# Hard limit: refuse to upload (can be overridden on server)
SOFT_SIZE_LIMIT = 100 * 1024 * 1024  # 100 MB
HARD_SIZE_LIMIT = 1024 * 1024 * 1024  # 1 GB
# The server's documented default upload limit (Litestar request_max_body_size
# and nginx client_max_body_size). The real limit is server-configured, but at
# this size a deploy is likely to be rejected with HTTP 413 — warn loudly and
# show what's big, before wasting the upload. ponytail: hardcoded default; a
# future /rpc capability handshake could report the server's actual limit.
DEFAULT_SERVER_UPLOAD_LIMIT = 200 * 1024 * 1024  # 200 MB

# What the `hop3 deploy` upload always excludes, regardless of deployment
# method: VCS metadata, OS/IDE cruft, and dependency/build caches the server
# regenerates (the toolchain runs npm/pip install; the venv is built
# server-side). Per-app additions go in hop3.toml [build].ignore (ADR 046 §5).
#
# Deliberately NOT consulted for this upload:
#   - .gitignore     governs the git-push deploy path only, not this upload.
#   - .dockerignore  scopes the server-side `docker build` context (Docker
#                    applies it there); e.g. Quarkus ships `*` + a target/
#                    allowlist, which would gut the upload if honored here.
_DEFAULT_IGNORE_PATTERNS = [
    ".git/",
    ".hg/",
    ".svn/",
    ".DS_Store",
    ".idea/",
    "__pycache__/",
    "*.py[cod]",
    "*.egg-info/",
    ".venv/",
    "venv/",
    "node_modules/",
    # Compiled-language build output, rebuilt server-side and never deployed.
    # `target/` is both Rust's (cargo) and Java/Maven's output dir; cargo
    # hardlinks the release binary into target/release/deps/, which the
    # server's safe-extract refuses — and it is hundreds of MB. Same rationale
    # as node_modules/.venv above.
    "target/",
    ".mypy_cache/",
    ".pytest_cache/",
    ".ruff_cache/",
]

# Deprecated Hop3-specific sidecar, superseded by hop3.toml [build].ignore.
# Honored for one transition release with a loud warning, then removed (ADR 046).
_DEPRECATED_IGNORE_FILE = ".hop3ignore"


def get_extra_args(args: list[str], verbosity: int = 1) -> JsonDict:
    """Generate a dictionary of extra arguments for RPC commands.

    Args:
        args: Command-line arguments
        verbosity: Verbosity level (0=quiet, 1=normal, 2=verbose, 3=debug)

    Returns:
        Dictionary with extra arguments. Verbosity is always included as it's
        used by the server to set the logging context for all commands.
    """
    # Always include verbosity - server extracts it and uses it as context
    extra_args: JsonDict = {"verbosity": verbosity}

    if not args:
        return extra_args

    # ADR 036 G3: read password from --password-file/--stdin and rewrite argv
    # in place so the secret never appears in the user's shell history or
    # `ps` output. The positional form still works but is discouraged.
    _resolve_password_inputs(args)
    # ADR 036 G3: `--input -` reads from stdin; `--input @<path>` reads from
    # a file. Mirrors the password-file pattern so `hop run myapp foo --input -`
    # behaves predictably in pipelines.
    _resolve_run_input(args)

    command = args[0]

    match command:
        case "deploy":
            # Parse deploy-specific flags
            # args[0]="deploy", args[1]=app_name, remaining args may include --env and directory
            env_vars, remaining_args, streaming = _parse_deploy_args(args[1:])

            # Skip expensive archive generation if no app name provided
            # Let the server return a proper usage error instead
            if not remaining_args:
                return extra_args

            # Directory is the last non-flag argument (if any)
            directory = Path(remaining_args[-1]) if len(remaining_args) > 1 else Path()
            extra_args["repository"] = pack_repository(directory, verbosity=verbosity)

            # Include env vars if any were specified
            if env_vars:
                extra_args["env_vars"] = env_vars  # type: ignore[assignment]  # pyrefly: ignore

            # Enable streaming by default for real-time log output
            extra_args["streaming"] = streaming

        case "addon":
            # `addon <type> import <name> < dump.sql`: ship the piped dump to
            # the server as a base64 blob (same approach as deploy's upload).
            if len(args) >= 3 and args[2] == "import":
                import_data = _read_import_data()
                if import_data is not None:
                    extra_args["import_data"] = import_data

    return extra_args


def _read_import_data() -> str | None:
    """Read a dump piped on stdin and base64-encode it for transport.

    Returns None when stdin is a terminal (no dump piped) or empty, so the
    server can emit a clear "pipe a dump" error instead of the CLI hanging on
    a read from an interactive terminal.
    """
    if sys.stdin.isatty():
        return None
    raw = sys.stdin.buffer.read()
    if not raw:
        return None
    return base64.b64encode(raw).decode("ascii")


def _resolve_run_input(args: list[str]) -> None:
    """Resolve --input -/@path on `hop run` so the server gets literal bytes.

    Per ADR 036 G3, dash means stdin and ``@<path>`` means "read from file".
    Bare strings are passed through unchanged. Only applies to ``hop run``.
    """
    if not args or args[0] != "run":
        return
    i = 0
    while i < len(args):
        if args[i] != "--input":
            i += 1
            continue
        if i + 1 >= len(args):
            return  # let server emit "--input requires a value"
        value = args[i + 1]
        if value == "-":
            if sys.stdin.isatty():
                msg = "Refusing to read --input from a terminal stdin; pipe data in or use --input @<path>."
                raise ValueError(msg)
            args[i + 1] = sys.stdin.read().rstrip("\n")
        elif value.startswith("@"):
            path = value[1:]
            try:
                args[i + 1] = Path(path).read_text(encoding="utf-8").rstrip("\n")
            except OSError as e:
                msg = f"Could not read --input file {path!r}: {e}"
                raise ValueError(msg) from e
        i += 2


def _resolve_password_inputs(args: list[str]) -> None:
    """Replace --password-file/--stdin on user-management commands with positional.

    Per ADR 036 G3, password input flows are:
      --password-file <path>   read password from a file
      --password-file -        read password from stdin (G3 dash convention)
      --stdin                  read password from stdin (alias for the above)

    Mutates ``args`` in place: removes the flag(s) and inserts the password as
    the next positional after the command tokens. Server-side commands keep
    their existing positional contract — the CLI is the security boundary.

    Applies to the three commands that take a password:
      hop3 user add <username> <email> <password>
      hop3 user set-password <username> <password>
      hop3 auth login <username> <password>
    """
    insert_at = _password_insert_index(args)
    if insert_at is None:
        return

    password = _extract_password_flag(args)
    if password is None:
        return

    insert_at = min(insert_at, len(args))
    args.insert(insert_at, password)


def _password_insert_index(args: list[str]) -> int | None:
    """Return the positional index where the resolved password should land.

    Returns None if the current ``args`` does not target a command that
    accepts a password.
    """
    if len(args) < 2:
        return None
    if args[0] == "user" and args[1] == "add":
        # user add <username> <email> <password>
        return 4
    if args[0] == "user" and args[1] == "set-password":
        # user set-password <username> <password>
        return 3
    if args[0] == "auth" and args[1] == "login":
        # auth login <username> <password>
        return 3
    return None


def _extract_password_flag(args: list[str]) -> str | None:
    """Pop --password-file / --stdin from args and return the resolved password.

    Returns None if no password flag is present. Raises ValueError if the
    flag is malformed (missing path, file unreadable, empty result).
    """
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--password-file":
            if i + 1 >= len(args):
                msg = "--password-file requires a path (use '-' for stdin)"
                raise ValueError(msg)
            path = args[i + 1]
            del args[i : i + 2]
            return _read_password_source(path)
        if arg.startswith("--password-file="):
            path = arg.split("=", 1)[1]
            del args[i]
            return _read_password_source(path)
        if arg == "--stdin":
            del args[i]
            return _read_password_source("-")
        i += 1
    return None


def _read_password_source(path: str) -> str:
    """Read a password from a file path; ``-`` means stdin (ADR 036 G3)."""
    if path == "-":
        if sys.stdin.isatty():
            msg = (
                "Refusing to read password from a terminal stdin; "
                "pipe the password in or use --password-file <path>."
            )
            raise ValueError(msg)
        password = sys.stdin.readline().rstrip("\n")
    else:
        try:
            password = Path(path).read_text(encoding="utf-8").rstrip("\n")
        except OSError as e:
            msg = f"Could not read password file {path!r}: {e}"
            raise ValueError(msg) from e
    if not password:
        msg = "Password is empty"
        raise ValueError(msg)
    return password


def _parse_deploy_args(args: list[str]) -> tuple[dict[str, str], list[str], bool]:
    """Parse deploy command arguments, extracting --env and --no-stream flags.

    Args:
        args: Arguments after 'deploy' command (app_name, --env flags, directory)

    Returns:
        Tuple of (env_vars dict, remaining args, streaming enabled)

    Example:
        >>> _parse_deploy_args(['myapp', '--env', 'FOO=bar', '--env', 'BAZ=qux', '.'])
        ({'FOO': 'bar', 'BAZ': 'qux'}, ['myapp', '.'], True)
        >>> _parse_deploy_args(['myapp', '--no-stream'])
        ({}, ['myapp'], False)
    """
    env_vars: dict[str, str] = {}
    remaining: list[str] = []
    streaming = True  # Enabled by default
    i = 0

    while i < len(args):
        arg = args[i]

        if arg in {"--env", "-e"}:
            # Next argument should be KEY=VALUE
            if i + 1 < len(args):
                env_spec = args[i + 1]
                if "=" in env_spec:
                    key, _, value = env_spec.partition("=")
                    env_vars[key] = value
                i += 2
            else:
                i += 1  # Skip malformed --env without value
        elif arg.startswith("--env="):
            # Handle --env=KEY=VALUE format
            env_spec = arg[6:]  # Remove --env=
            if "=" in env_spec:
                key, _, value = env_spec.partition("=")
                env_vars[key] = value
            i += 1
        elif arg == "--no-stream":
            # Disable real-time streaming (fallback to batch output)
            streaming = False
            i += 1
        elif arg == "--stream":
            # Explicitly enable streaming (default, but allow explicit)
            streaming = True
            i += 1
        else:
            remaining.append(arg)
            i += 1

    return env_vars, remaining, streaming


def pack_repository(directory: Path = Path(), verbosity: int = 1) -> str:
    """Pack a directory into a base64-encoded tar.gz archive.

    Args:
        directory: Directory to pack (defaults to current directory)
        verbosity: Verbosity level (0=quiet, 1=normal, 2+=verbose)

    Returns:
        Base64-encoded tar.gz archive
    """
    tar_gz = generate_archive(directory, verbosity=verbosity)
    return base64.b64encode(tar_gz).decode("ascii")


def generate_archive(source_dir: Path, verbosity: int = 1) -> bytes:
    """
    Creates an in-memory tar.gz archive of a source directory as a bytes object,
    excluding built-in defaults plus the app's hop3.toml [build].ignore patterns
    (ADR 046 §5). .gitignore and .dockerignore are not consulted for this upload.

    Args:
        source_dir: The path to the directory to archive.
        verbosity: Verbosity level (0=quiet, 1=normal, 2+=verbose)

    Returns:
        The content of the .tar.gz archive as a bytes object.

    Raises:
        ValueError: If the source_dir is not a valid directory or has too many files.
        FileNotFoundError: If the source_dir does not exist.
    """
    source_dir = Path(source_dir).resolve()
    verbose = verbosity >= 2

    if not source_dir.exists():
        msg = (
            f"Directory not found: {source_dir}\n\n"
            f"Make sure you are in the directory containing your application code,\n"
            f"or specify the path as the last argument:\n"
            f"  hop3 deploy <app_name> /path/to/app"
        )
        raise FileNotFoundError(msg)
    if not source_dir.is_dir():
        msg = f"Path is not a directory: {source_dir}"
        raise ValueError(msg)

    # Check if directory looks like an application
    _check_directory_is_app(source_dir, verbose)

    if verbose:
        print(f"Creating archive from: {source_dir}", file=sys.stderr)

    # --- 1. Load ignore rules (built-in defaults + hop3.toml [build].ignore) ---
    spec, ignore_source = get_ignored_spec(source_dir)
    if verbose:
        print(f"Using ignore patterns from: {ignore_source}", file=sys.stderr)

    # --- 2. Walk the directory and gather files to include ---
    if verbose:
        print("Scanning files...", file=sys.stderr)
    files_to_add = get_files_to_add(source_dir, spec)

    # --- 3. Log file count ---
    file_count = len(files_to_add)
    if verbose:
        print(f"Found {file_count} files to archive", file=sys.stderr)

    # --- 4. Create the tar.gz archive in memory ---
    if verbose:
        print("Creating archive...", file=sys.stderr)

    fileobj = io.BytesIO()

    # The 'w:gz' mode creates a gzip-compressed tar file.
    # We pass our BytesIO object as the file to write to.
    with tarfile.open(fileobj=fileobj, mode="w:gz") as tar:
        for file_path in files_to_add:
            relative_path = file_path.relative_to(source_dir)
            arcname = Path() / relative_path
            tar.add(file_path, arcname=str(arcname))

    archive_bytes = fileobj.getvalue()
    _check_archive_size(archive_bytes, files_to_add, source_dir, verbose)

    return archive_bytes


def _check_archive_size(
    archive_bytes: bytes,
    files: list[Path],
    source_dir: Path,
    verbose: bool,
) -> None:
    """Check archive size against soft and hard limits.

    Args:
        archive_bytes: The archive content
        files: List of files in the archive (for diagnostics)
        source_dir: Source directory (for computing relative paths)
        verbose: Whether to print verbose output
    """
    archive_size = len(archive_bytes)
    size_mb = archive_size / (1024 * 1024)

    if verbose:
        print(f"Archive created: {size_mb:.2f} MB", file=sys.stderr)

    if archive_size > HARD_SIZE_LIMIT:
        dir_summary = _largest_dirs_summary(files, source_dir)
        hard_limit_mb = HARD_SIZE_LIMIT / (1024 * 1024)

        msg = (
            f"Archive too large: {size_mb:.1f} MB exceeds the {hard_limit_mb:.0f} MB limit.\n"
            f"\n"
            f"Largest entries:\n"
            f"{dir_summary}\n"
            f"\n"
            f"Run 'hop3 deploy --dry-run' to see the full archive manifest.\n"
            f"Add patterns to the [build].ignore list in hop3.toml to exclude\n"
            f"them from deployment. The server may also have configurable size limits."
        )
        raise ValueError(msg)

    if archive_size > DEFAULT_SERVER_UPLOAD_LIMIT:
        dir_summary = _largest_dirs_summary(files, source_dir)
        limit_mb = DEFAULT_SERVER_UPLOAD_LIMIT / (1024 * 1024)
        print(
            f"Warning: archive ({size_mb:.1f} MB) exceeds the default server "
            f"upload limit ({limit_mb:.0f} MB); the deploy will likely be "
            f"rejected (HTTP 413).\n"
            f"Largest entries:\n{dir_summary}\n"
            f"Run 'hop3 deploy --dry-run' to see the full manifest. Exclude large "
            f"entries via [build].ignore in hop3.toml, or ask the server admin to "
            f"raise the limit.",
            file=sys.stderr,
        )
    elif archive_size > SOFT_SIZE_LIMIT:
        soft_limit_mb = SOFT_SIZE_LIMIT / (1024 * 1024)
        print(
            f"Warning: Large archive ({size_mb:.1f} MB). "
            f"Uploads over {soft_limit_mb:.0f} MB may be slow.",
            file=sys.stderr,
        )


def get_ignored_spec(source_dir: Path) -> tuple[pathspec.PathSpec, str]:
    """Build the ignore spec for the `hop3 deploy` upload.

    The upload always excludes a built-in set of never-deploy paths
    (`_DEFAULT_IGNORE_PATTERNS`), extended by the canonical per-app source:

    1. hop3.toml ``[build].ignore`` — the declarative ignore list (ADR 046 §5).
    2. ``.hop3ignore`` — DEPRECATED sidecar, still honored for one release with
       a loud warning; move its patterns into ``[build].ignore``.

    ``.gitignore`` (git-push path) and ``.dockerignore`` (server-side
    ``docker build``) are intentionally NOT consulted here.

    Returns:
        Tuple of (PathSpec, human-readable description of the pattern sources).
    """
    patterns = list(_DEFAULT_IGNORE_PATTERNS)
    sources = ["built-in defaults"]

    build_ignore = _get_build_ignore_patterns(source_dir)
    if build_ignore is not None:
        patterns.extend(build_ignore)
        sources.append(f"hop3.toml [build].ignore ({len(build_ignore)} patterns)")
    else:
        deprecated = source_dir / _DEPRECATED_IGNORE_FILE
        if deprecated.is_file():
            patterns.extend(deprecated.read_text(encoding="utf-8").splitlines())
            sources.append(f"{_DEPRECATED_IGNORE_FILE} (deprecated)")
            print(
                f"Warning: {_DEPRECATED_IGNORE_FILE} is deprecated and will stop "
                f"being read in a future release. Move its patterns into the "
                f"[build].ignore list in hop3.toml.",
                file=sys.stderr,
            )

    spec = pathspec.PathSpec.from_lines("gitignore", patterns)  # pyrefly: ignore
    return spec, ", ".join(sources)


def _get_build_ignore_patterns(source_dir: Path) -> list[str] | None:
    """Return hop3.toml ``[build].ignore`` patterns, or None if not declared.

    Reads the app's hop3.toml from the standard locations. ``[build].ignore`` is
    the canonical, declarative ignore list for the deploy upload (ADR 046 §5);
    the legacy ``[build].ignore-file`` pointer is no longer supported.
    """
    for hop3_toml_path in (
        source_dir / "hop3" / "hop3.toml",
        source_dir / "hop3.toml",
    ):
        # read_hop3_toml returns {} for a missing or unparseable file.
        build_section = read_hop3_toml(hop3_toml_path).get("build", {})
        if not isinstance(build_section, dict):
            continue
        patterns = build_section.get("ignore")
        if isinstance(patterns, list) and patterns:
            return [str(p) for p in patterns]
    return None


def _human_size(num_bytes: int) -> str:
    """Format a byte count as a short human-readable size (e.g. '207.8 MB')."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def _aggregate_by_top_dir(
    sized_files: list[tuple[Path, int]], source_dir: Path
) -> list[tuple[str, int]]:
    """Total upload size per top-level entry, largest first.

    Size (not file count) is what matters for the 413 limit, and a top-level
    entry is what you'd actually add to [build].ignore.
    """
    dir_sizes: dict[str, int] = {}
    for f, size in sized_files:
        rel = f.relative_to(source_dir)
        top = rel.parts[0] if len(rel.parts) > 1 else "(root)"
        dir_sizes[top] = dir_sizes.get(top, 0) + size
    return sorted(dir_sizes.items(), key=itemgetter(1), reverse=True)


def _largest_dirs_summary(files: list[Path], source_dir: Path, n: int = 5) -> str:
    """A few-line summary of the largest top-level entries, by size."""
    sized = [(f, f.stat().st_size) for f in files]
    top = _aggregate_by_top_dir(sized, source_dir)[:n]
    return "\n".join(f"  {_human_size(sz):>10}  {name}" for name, sz in top)


def describe_archive(source_dir: Path) -> str:
    """Human-readable manifest of what `hop3 deploy` would upload.

    Walks the source, applies the SAME ignore rules as the real upload, and
    reports the total size, the ignore rules in effect, and the largest
    directories and files — so the user can see exactly what's in the archive
    (and what to add to [build].ignore) instead of guessing. Stats only; does
    not build the tarball.
    """
    spec, sources = get_ignored_spec(source_dir)
    files = get_files_to_add(source_dir, spec)
    sized = [(f, f.stat().st_size) for f in files]
    total = sum(size for _, size in sized)

    lines = [
        (
            f"Deploy archive: {_human_size(total)} across {len(files)} files "
            f"(uncompressed; the upload itself is gzipped)."
        ),
        f"Ignore rules: {sources}.",
    ]

    top_dirs = _aggregate_by_top_dir(sized, source_dir)
    if top_dirs:
        lines.append("\nLargest entries:")
        lines += [f"  {_human_size(sz):>10}  {name}" for name, sz in top_dirs[:10]]

    largest = sorted(sized, key=itemgetter(1), reverse=True)[:15]
    if largest:
        lines.append("\nLargest files:")
        lines += [
            f"  {_human_size(sz):>10}  {f.relative_to(source_dir)}" for f, sz in largest
        ]

    lines.append("\nTo shrink it, add large entries to [build].ignore in hop3.toml.")
    return "\n".join(lines)


def _check_directory_is_app(source_dir: Path, verbose: bool) -> None:
    """Check if the directory looks like an application and warn if not.

    Args:
        source_dir: The directory to check
        verbose: Whether to print verbose output
    """
    # Common app indicators
    app_indicators = [
        "Procfile",
        "hop3.toml",
        "package.json",
        "requirements.txt",
        "pyproject.toml",
        "Cargo.toml",
        "go.mod",
        "Gemfile",
        "composer.json",
        "pom.xml",
        "build.gradle",
        "Makefile",
        "Dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
        "index.html",
        "index.php",
    ]

    has_indicator = any((source_dir / f).exists() for f in app_indicators)

    if not has_indicator:
        # Check if directory has any files at all
        files = list(source_dir.iterdir())
        if not files:
            msg = (
                f"Directory is empty: {source_dir}\n\n"
                f"The deploy command expects a directory containing your application code.\n"
                f"Make sure you are in the correct directory."
            )
            raise ValueError(msg)

        # Directory has files but no recognizable app structure
        if verbose:
            print(
                f"Warning: No recognized application files found in {source_dir}\n"
                f"Expected one of: {', '.join(app_indicators[:5])}...\n"
                f"Proceeding anyway - the server will attempt to deploy.",
                file=sys.stderr,
            )


def get_files_to_add(source_dir: Path, spec: pathspec.PathSpec) -> list[Path]:
    """Get list of files to add to archive, excluding ignored files."""
    files_to_add: list[Path] = []
    for file_path in source_dir.rglob("*"):
        relative_path = file_path.relative_to(source_dir)
        relative_str = str(relative_path)

        # Let pathspec determine if the file should be ignored (.git/ and other
        # never-deploy paths are in _DEFAULT_IGNORE_PATTERNS).
        if spec.match_file(relative_str):
            continue

        # We only add files to the tar, not directories
        if not file_path.is_file():
            continue

        files_to_add.append(file_path)
    return files_to_add
