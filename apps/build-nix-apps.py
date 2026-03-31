#!/usr/bin/env python3
# Copyright (c) 2024-2025 Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Build nix apps locally to verify they work.

Scans directories for hop3.nix files and runs nix-build on each one.
When a build fails due to a hash mismatch, --fix-hashes automatically
updates the hop3.nix file with the correct hash and retries the build.

Usage:
    ./build-nix-apps.py test-apps-nix             # Build only test apps
    ./build-nix-apps.py real-apps-nix             # Build only real apps
    ./build-nix-apps.py test-apps-nix real-apps-nix  # Both
    ./build-nix-apps.py test-apps-nix --app flask-hello  # Single app
    ./build-nix-apps.py test-apps-nix --fix-hashes       # Auto-fix hashes
    ./build-nix-apps.py test-apps-nix --debug            # Full error output
"""

from __future__ import annotations

import argparse
import re
import selectors
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent


# ── Main ────────────────────────────────────────────────────


def main() -> None:
    args = _parse_args()
    _check_nix_available()

    app_dirs = _resolve_app_dirs(args)

    label = f"Building {len(app_dirs)} nix apps"
    if args.fix_hashes:
        label += " (auto-fixing hashes)"
    print(f"{label}...\n")

    summary = BuildSummary()

    for app_dir in app_dirs:
        print(f"[{app_dir.name}] ", end="", flush=True)

        result = build_app(
            app_dir,
            show_trace=args.show_trace,
            fix_hashes=args.fix_hashes,
            verbose=args.verbose or args.debug,
            timeout=args.timeout,
        )
        summary.results.append(result)
        _print_result(result, verbose=args.verbose, debug=args.debug)

    _print_summary(summary, debug=args.debug, fix_hashes=args.fix_hashes)

    if summary.failed:
        sys.exit(1)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build nix apps locally")
    parser.add_argument(
        "dirs",
        nargs="+",
        help="Directories to scan for hop3.nix files",
    )
    parser.add_argument("--app", help="Build only this app (searched in all dirs)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show store paths")
    parser.add_argument(
        "--debug", "-d", action="store_true",
        help="Show full nix output for failed builds",
    )
    parser.add_argument(
        "--show-trace", action="store_true",
        help="Run nix-build with --show-trace",
    )
    parser.add_argument(
        "--fix-hashes", action="store_true",
        help="Auto-fix SHA256 hash mismatches in hop3.nix files",
    )
    parser.add_argument(
        "--timeout", type=int, default=300,
        help="Timeout per app in seconds (default: 300)",
    )
    return parser.parse_args()


def _check_nix_available() -> None:
    result = subprocess.run(
        ["nix", "--version"], capture_output=True, check=False
    )
    if result.returncode != 0:
        print("Error: nix is not installed or not in PATH")
        sys.exit(1)


# ── Core build logic ────────────────────────────────────────


def build_app(
    app_dir: Path,
    *,
    show_trace: bool = False,
    fix_hashes: bool = False,
    max_hash_retries: int = 3,
    verbose: bool = False,
    timeout: int = 300,
) -> BuildResult:
    """Build a single nix app.

    Returns a BuildResult. On failure the result contains the exception.
    """
    nix_file = app_dir / "hop3.nix"
    app_name = app_dir.name
    if not nix_file.exists():
        return BuildResult(
            app_name=app_name,
            error=NixBuildError("no hop3.nix found"),
        )

    hashes_fixed = 0
    for attempt in range(max_hash_retries + 1):
        cmd = ["nix-build", str(nix_file), "-A", "package", "--no-out-link"]
        if show_trace:
            cmd.append("--show-trace")

        try:
            result = _run_nix_build(
                cmd, app_dir, verbose=verbose, timeout=timeout
            )
        except NixBuildTimeoutError as exc:
            return BuildResult(app_name=app_name, error=exc)

        stderr = result.stderr.strip()

        if result.returncode == 0:
            return BuildResult(
                app_name=app_name,
                store_path=result.stdout.strip(),
                hashes_fixed=hashes_fixed,
            )

        # Try auto-fixing hash mismatches
        if fix_hashes and attempt < max_hash_retries:
            correct_hash = _extract_expected_hash(stderr)
            if correct_hash and _fix_hash_in_file(nix_file, correct_hash):
                hashes_fixed += 1
                print(
                    f"(fixing hash, attempt {hashes_fixed}) ",
                    end="", flush=True,
                )
                continue

        # Permanent failure
        msg = _extract_error_message(stderr)
        return BuildResult(
            app_name=app_name,
            error=NixBuildError(msg, stderr),
        )

    return BuildResult(
        app_name=app_name,
        error=NixBuildError("max hash fix retries exceeded"),
    )


# ── Exceptions ──────────────────────────────────────────────


class NixBuildError(Exception):
    """Raised when a nix-build invocation fails."""

    def __init__(self, message: str, full_stderr: str = "") -> None:
        super().__init__(message)
        self.full_stderr = full_stderr


class NixBuildTimeoutError(NixBuildError):
    """Raised when nix-build exceeds the time limit."""


class NixHashMismatchError(NixBuildError):
    """Raised when nix-build fails due to a hash mismatch."""

    def __init__(
        self, message: str, full_stderr: str, correct_hash: str
    ) -> None:
        super().__init__(message, full_stderr)
        self.correct_hash = correct_hash


# ── Result tracking ─────────────────────────────────────────


@dataclass
class BuildResult:
    """Outcome of a single app build."""

    app_name: str
    store_path: str = ""
    hashes_fixed: int = 0
    error: NixBuildError | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass
class BuildSummary:
    """Aggregated results for a full run."""

    results: list[BuildResult] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.ok)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.ok)

    @property
    def failures(self) -> list[BuildResult]:
        return [r for r in self.results if not r.ok]


# ── Nix build runners ──────────────────────────────────────


def _run_nix_build(
    cmd: list[str],
    cwd: Path,
    *,
    verbose: bool = False,
    timeout: int = 300,
) -> subprocess.CompletedProcess:
    """Run nix-build, optionally streaming stderr.

    Raises:
        NixBuildTimeoutError: If the build exceeds *timeout* seconds.
    """
    if verbose:
        return _run_nix_build_verbose(cmd, cwd, timeout)
    return _run_nix_build_quiet(cmd, cwd, timeout)


def _run_nix_build_quiet(
    cmd: list[str], cwd: Path, timeout: int
) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(
            cmd, capture_output=True, cwd=cwd, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired as exc:
        msg = f"timed out after {timeout}s"
        raise NixBuildTimeoutError(msg, "") from exc

    return subprocess.CompletedProcess(
        result.args,
        result.returncode,
        result.stdout.decode("utf-8", errors="replace"),
        result.stderr.decode("utf-8", errors="replace"),
    )


def _run_nix_build_verbose(
    cmd: list[str], cwd: Path, timeout: int
) -> subprocess.CompletedProcess:
    # Use binary mode to handle non-UTF-8 output (e.g., pip progress bars)
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
    )
    assert proc.stderr is not None
    assert proc.stdout is not None
    stderr_chunks: list[bytes] = []
    try:
        sel = selectors.DefaultSelector()
        sel.register(proc.stderr, selectors.EVENT_READ)

        start = time.time()
        last_print = 0.0
        while proc.poll() is None:
            elapsed = time.time() - start
            if elapsed > timeout:
                proc.kill()
                proc.wait()
                msg = f"timed out after {timeout}s"
                raise NixBuildTimeoutError(msg, "")
            for key, _ in sel.select(timeout=1.0):
                chunk = key.fileobj.read1(4096)  # type: ignore[union-attr]
                if not chunk:
                    continue
                stderr_chunks.append(chunk)
                stripped = chunk.decode("utf-8", errors="replace").strip()
                if stripped and (elapsed - last_print) > 1.0:
                    # Show last line of the chunk
                    last_line = stripped.splitlines()[-1]
                    print(f"    {last_line[:74]}", flush=True)
                    last_print = elapsed
        remaining = proc.stderr.read()
        if remaining:
            stderr_chunks.append(remaining)
        sel.close()
    except NixBuildTimeoutError:
        raise
    except Exception:
        proc.kill()
        proc.wait()
        raise

    stdout = proc.stdout.read().decode("utf-8", errors="replace")
    stderr = b"".join(stderr_chunks).decode("utf-8", errors="replace")
    return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)


# ── Hash fixing ─────────────────────────────────────────────

HASH_MISMATCH_PATTERNS = [
    re.compile(r"got:\s+sha256[:-](\S+)"),
    re.compile(r"got:\s+(sha256-\S+=*)"),
]

PLACEHOLDER_PATTERNS = [
    r'sha256 = "0+";',
    r'sha256 = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=";',
    r"sha256 = pkgs\.lib\.fakeSha256;",
    r"sha256 = lib\.fakeSha256;",
    r'vendorHash = "0+";',
    r'npmDepsHash = "0+";',
]


def _extract_expected_hash(stderr: str) -> str | None:
    """Extract the correct hash from a nix-build hash mismatch error."""
    for pattern in HASH_MISMATCH_PATTERNS:
        match = pattern.search(stderr)
        if match:
            return match.group(1)
    return None


def _fix_hash_in_file(nix_file: Path, correct_hash: str) -> bool:
    """Replace a placeholder hash in hop3.nix with the correct one.

    Returns True if a replacement was made.
    """
    content = nix_file.read_text()
    original = content

    for pattern in PLACEHOLDER_PATTERNS:
        if "vendorHash" in pattern:
            replacement = f'vendorHash = "{correct_hash}";'
        elif "npmDepsHash" in pattern:
            replacement = f'npmDepsHash = "{correct_hash}";'
        else:
            replacement = f'sha256 = "{correct_hash}";'
        content = re.sub(pattern, replacement, content)

    if content != original:
        nix_file.write_text(content)
        return True
    return False


# ── Error extraction ────────────────────────────────────────


def _extract_error_message(stderr: str) -> str:
    """Extract a human-readable error from nix-build stderr."""
    lines = stderr.split("\n")

    last_error = None
    last_error_idx = -1
    for i, line in enumerate(lines):
        if line.strip().startswith("error:"):
            last_error = line.strip()
            last_error_idx = i

    if last_error:
        msg = last_error[6:].strip()
        if not msg and last_error_idx + 1 < len(lines):
            msg = lines[last_error_idx + 1].strip()
        return msg or "build error"

    for line in reversed(lines):
        if line.strip():
            return line.strip()[:100]

    return "build failed (no error message)"


# ── CLI helpers ─────────────────────────────────────────────


def _resolve_app_dirs(args: argparse.Namespace) -> list[Path]:
    """Turn CLI arguments into a list of app directories to build."""
    assert args.dirs
    scan_dirs: list[Path] = []
    for name in args.dirs:
        d = Path(name).absolute()
        if not d.exists():
            print(f"Error: Directory '{d}' not found")
            sys.exit(1)
        scan_dirs.append(d)

    if args.app:
        for d in scan_dirs:
            candidate = d / args.app
            if candidate.exists():
                return [candidate]
        dirs_str = ", ".join(str(d) for d in scan_dirs)
        print(f"Error: App '{args.app}' not found in {dirs_str}")
        sys.exit(1)

    return sorted([
        d
        for scan_dir in scan_dirs
        for d in scan_dir.iterdir()
        if d.is_dir() and (d / "hop3.nix").exists()
    ])


def _print_result(result: BuildResult, *, verbose: bool, debug: bool) -> None:
    """Print a single build result."""
    if result.ok:
        print("PASS")
        if verbose:
            msg = result.store_path
            if result.hashes_fixed:
                msg += f" (fixed {result.hashes_fixed} hash(es))"
            print(f"  -> {msg}")
    else:
        assert result.error is not None
        print("FAIL")
        print(f"  -> {result.error}")
        if debug and result.error.full_stderr:
            print("\n  --- Full nix output ---")
            for line in result.error.full_stderr.split("\n"):
                print(f"  {line}")
            print("  --- End of output ---\n")


def _print_summary(
    summary: BuildSummary, *, debug: bool, fix_hashes: bool
) -> None:
    """Print final summary."""
    total = len(summary.results)
    print(f"\n{'=' * 60}")
    print(
        f"Results: {summary.passed} passed, {summary.failed} failed"
        f" out of {total}"
    )
    print("=" * 60)

    if summary.failures:
        print("\nFailed apps:")
        for r in summary.failures:
            print(f"  - {r.app_name}: {r.error}")

        if not debug:
            print("\nTip: Use --debug for full nix output")
            print("     Use --show-trace for nix stack traces")
            if not fix_hashes:
                print("     Use --fix-hashes to auto-fix SHA256 mismatches")


if __name__ == "__main__":
    main()
