# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The golden-app benchmark matrix: every app, in every variant, timed.

One command replaces the former provision/setup/run shell trio.

Two invariants this module exists to keep:

- **It never creates a cloud box.** The bench owns exactly one dedicated server,
  named by ``$HETZNER_SERVER_ID``, wiped between runs by an *OS rebuild* — same
  server, same IP, fresh Ubuntu. Creating boxes leaks paid infrastructure.
- **The corpus comes from the committed pre-registration** (``protocol.yaml``),
  never from a list duplicated here, so a run cannot silently drift from what
  was pre-registered.

Each cell is written to the results file as soon as it finishes, so an
interrupted run keeps everything measured up to that point.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from hop3_tooling import catalog
from hop3_tooling.catalog import find_repo_root

if TYPE_CHECKING:
    from collections.abc import Mapping

# The ONE dedicated benchmark box is named by this environment variable. This
# module rebuilds that server in place and must never create one.
SERVER_ID_ENVVAR = "HETZNER_SERVER_ID"
REBUILD_IMAGE = "ubuntu-24.04"

# Hop3 standardises on HETZNER_API_TOKEN; the hcloud CLI reads HCLOUD_TOKEN and,
# finding none, silently falls back to its stored context — whose token may be
# stale, giving a baffling "unauthorized" against a correctly-configured
# environment. Bridge the two rather than let that fallback happen.
TOKEN_ENVVAR = "HETZNER_API_TOKEN"
HCLOUD_TOKEN_ENVVAR = "HCLOUD_TOKEN"

VARIANTS = ("native", "docker", "nix", "nix-gen")

PROTOCOL_PATH = Path("notes/benchmarks/protocol.yaml")
# Without an operator email every ADR-056 admin-bootstrap app fails to deploy.
OPERATOR_EMAIL = "bench@hop3.example"

SSH_OPTS = (
    "-o",
    "StrictHostKeyChecking=no",
    "-o",
    "BatchMode=yes",
    "-o",
    "ConnectTimeout=8",
)
_SSH_WAIT_TRIES = 30
_SSH_WAIT_SLEEP = 8

# Ordered most-specific first; the first pattern that matches wins. Ordering
# matters: a generic "Deploy failed: Exit code: 1" says nothing, while the
# deploy error that follows it names the actual cause.
_REASON_PATTERNS = (
    re.compile(r"ERROR: deploying app failed:[^\n]+"),  # deploy, with cause
    re.compile(r"Error: HTTP [^\n]+"),  # validation (content/status)
    re.compile(r"[✗x] (?:build|startup)-failure[^\n]*"),  # classified kind
    re.compile(r"Error: Deploy failed:[^\n]+"),  # generic deploy
    re.compile(r"No such file[^\n]*|command not found[^\n]*"),
)
# Harness bookkeeping that merely contains the word "failed". Matching one of
# these reports the runner's own chatter as if it were the app's failure.
_NOISE_RE = re.compile(
    r"Re-running|previously-failed|No failures recorded|Failed tests:|\b0 failed\b",
    re.IGNORECASE,
)
_FALLBACK_RE = re.compile(
    r"^.*(?:error|failed|timeout).*$", re.IGNORECASE | re.MULTILINE
)
_REASON_MAX = 200


class MatrixError(RuntimeError):
    """A required step failed. Never downgraded to a skip."""


@dataclass(frozen=True, slots=True)
class Cell:
    """One ``(app, variant)`` measurement."""

    app: str
    variant: str
    status: str  # ok | failed | no-recipe
    seconds: int | None = None
    rc: int | None = None
    reason: str | None = None
    log: str | None = None

    def to_json(self) -> str:
        return json.dumps({k: v for k, v in asdict(self).items() if v is not None})


# --------------------------------------------------------------------------
# Pure logic (no I/O) — testable without a box.
# --------------------------------------------------------------------------


def load_corpus(protocol: Path) -> list[str]:
    """The pre-registered app list (``corpus.apps`` in protocol.yaml)."""
    if not protocol.is_file():
        msg = f"pre-registration not found: {protocol} — the corpus is defined there"
        raise MatrixError(msg)
    data: dict[str, Any] = yaml.safe_load(protocol.read_text()) or {}
    apps = (data.get("corpus") or {}).get("apps")
    if not apps:
        msg = f"{protocol}: corpus.apps is empty — refusing to benchmark nothing"
        raise MatrixError(msg)
    return list(apps)


def recipe_dir(root: Path, variant: str, app: str) -> Path:
    """
    Where a variant's recipe for an app lives.

    Resolved through the catalog rather than built from the variant name: the
    directory is the recipe's maturity now, not its packaging, so the path
    cannot be constructed from `variant` alone.
    """
    found = catalog.recipe_for(app, variant)
    if found is None:
        msg = f"no {variant} recipe for {app!r} in the catalog"
        raise MatrixError(msg)
    return found


def anchor(root: Path, path: Path) -> Path:
    """
    Resolve a possibly-relative output path against the repo root.

    Output paths are repo-relative by default; leaving them relative would make
    results land wherever the caller happened to stand, and would break the
    repo-relative log path recorded on a failed cell.
    """
    return path if path.is_absolute() else root / path


def reason_from(log_text: str) -> str:
    """
    A one-line cause for a failed cell. Never empty.

    A failure whose cause was discarded is a silent skip, and the per-variant
    failure reasons are the point of the exercise — they are the platform backlog.
    """
    for pattern in _REASON_PATTERNS:
        for candidate in pattern.finditer(log_text):
            if not _NOISE_RE.search(candidate.group(0)):
                return _clean(candidate.group(0))

    for candidate in _FALLBACK_RE.finditer(log_text):
        if not _NOISE_RE.search(candidate.group(0)):
            return _clean(candidate.group(0))

    return "no diagnostic in log"


def _clean(line: str) -> str:
    return line.replace('"', "").replace("\\", "").strip()[:_REASON_MAX]


def parse_variants(raw: str) -> list[str]:
    """Validate a comma-separated variant selection."""
    chosen = [v.strip() for v in raw.split(",") if v.strip()]
    unknown = [v for v in chosen if v not in VARIANTS]
    if unknown:
        msg = f"unknown variant(s): {unknown}. Known: {list(VARIANTS)}"
        raise MatrixError(msg)
    return chosen or list(VARIANTS)


# --------------------------------------------------------------------------
# Side effects
# --------------------------------------------------------------------------


def _run(
    cmd: list[str],
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, capture_output=True, text=True, check=False, cwd=cwd, env=env
    )


def hcloud_env(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """
    Environment for `hcloud` calls, with the API token bridged across names.

    Without this, an environment that sets only HETZNER_API_TOKEN leaves the CLI
    to fall back on its stored context, so a rotated token surfaces as
    "unauthorized" while the correct token sits unused in the environment.
    """
    env = dict(os.environ if environ is None else environ)
    if not env.get(HCLOUD_TOKEN_ENVVAR):
        token = env.get(TOKEN_ENVVAR)
        if not token:
            msg = (
                f"neither ${HCLOUD_TOKEN_ENVVAR} nor ${TOKEN_ENVVAR} is set — "
                "cannot reach the Hetzner API"
            )
            raise MatrixError(msg)
        env[HCLOUD_TOKEN_ENVVAR] = token
    return env


def _hcloud(*args: str) -> subprocess.CompletedProcess[str]:
    return _run(["hcloud", *args], env=hcloud_env())


def box_ip(server_id: str) -> str:
    """The dedicated box's IPv4, or a loud failure."""
    proc = _hcloud("server", "ip", server_id)
    ip = proc.stdout.strip()
    if proc.returncode != 0 or not ip:
        detail = proc.stderr.strip() or "no address returned"
        msg = f"could not read the IP of server {server_id}: {detail}"
        raise MatrixError(msg)
    return ip


def _hostnames_for(ip: str) -> set[str]:
    """
    DNS names the box also answers to, so their host keys can be cleared too.

    Best-effort: a missing reverse record is normal and simply means there is
    no extra name to clear.
    """
    try:
        name, aliases, _ = socket.gethostbyaddr(ip)
    except OSError:
        return set()
    return {name, *aliases}


def rebuild_box(server_id: str) -> str:
    """
    Wipe the dedicated box and return its IP once SSH answers.

    Rebuild, never create: the server and its IP are preserved, the disk is not.
    """
    proc = _hcloud("server", "rebuild", server_id, "--image", REBUILD_IMAGE)
    if proc.returncode != 0:
        msg = f"rebuild of server {server_id} failed: {proc.stderr.strip()[:300]}"
        raise MatrixError(msg)

    ip = box_ip(server_id)
    # A rebuilt box presents a new host key. Clear it under every name it is
    # reachable by, not just the address: a stale entry for the DNS name blocks
    # the next tool that connects that way with a bare "host key verification
    # failed", well after the rebuild that caused it.
    for name in {ip, *_hostnames_for(ip)}:
        _run(["ssh-keygen", "-R", name])
    for _ in range(_SSH_WAIT_TRIES):
        if _run(["ssh", *SSH_OPTS, f"root@{ip}", "true"]).returncode == 0:
            return ip
        time.sleep(_SSH_WAIT_SLEEP)

    msg = f"server {server_id} ({ip}) never answered SSH after the rebuild"
    raise MatrixError(msg)


def install_hop3(root: Path, ip: str) -> None:
    """Install Hop3 from local code onto the blank box, with OPERATOR_EMAIL set."""
    proc = _run(
        [
            "uv",
            "run",
            "hop3-deploy-server",
            "--host",
            ip,
            "--user",
            "root",
            "--from",
            "local",
            "--clean",
            "--with",
            "all",
        ],
        cwd=root,
    )
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout).strip()[-400:]
        msg = f"Hop3 install failed on {ip}: {tail}"
        raise MatrixError(msg)

    remote = (
        'grep -q "^OPERATOR_EMAIL" /home/hop3/hop3-server.toml || '
        f'sed -i "1i OPERATOR_EMAIL = \\"{OPERATOR_EMAIL}\\"" '
        "/home/hop3/hop3-server.toml; "
        "systemctl restart hop3-server; sleep 5; systemctl is-active hop3-server"
    )
    proc = _run(["ssh", *SSH_OPTS, f"root@{ip}", remote])
    if proc.returncode != 0 or "active" not in proc.stdout:
        msg = f"hop3-server is not active on {ip}: {proc.stdout.strip()} {proc.stderr.strip()}"
        raise MatrixError(msg)


def run_cell(root: Path, ip: str, variant: str, app: str, logs: Path) -> Cell:
    """Deploy one app in one variant against the box, timing it."""
    path = recipe_dir(root, variant, app)
    if not (path / "hop3.toml").is_file():
        # Not a failure: a missing variant is coverage data in its own right.
        return Cell(app=app, variant=variant, status="no-recipe")

    rel = path.relative_to(root)
    start = time.monotonic()
    proc = _run(["uv", "run", "hop3-test", "run", "--host", ip, str(rel)], cwd=root)
    seconds = int(time.monotonic() - start)

    if proc.returncode == 0:
        # Successes need no log; the timing is the measurement.
        return Cell(app=app, variant=variant, status="ok", seconds=seconds, rc=0)

    output = proc.stdout + proc.stderr
    logs.mkdir(parents=True, exist_ok=True)
    log_file = logs / f"{variant}-{app}.log"
    log_file.write_text(output)
    return Cell(
        app=app,
        variant=variant,
        status="failed",
        seconds=seconds,
        rc=proc.returncode,
        reason=reason_from(output),
        log=str(log_file.relative_to(root)),
    )


def run_matrix(
    *,
    server_id: str,
    variants: list[str],
    out_path: Path,
    logs_dir: Path,
    skip_rebuild: bool,
    append: bool,
    echo,
) -> list[Cell]:
    """
    Blank-slate the box, install Hop3, then measure every (app, variant) cell.

    Cells are flushed to ``out_path`` as they complete, so an interrupted run
    keeps everything measured so far.
    """
    root = find_repo_root()
    # Anchor outputs to the repo, so results land in the same place whatever the
    # caller's cwd — and so a failed cell's log path stays repo-relative.
    out_path = anchor(root, out_path)
    logs_dir = anchor(root, logs_dir)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Results files are date-named, so a same-day re-run collides. Appending
    # would silently blend two runs — different box state, maybe a different
    # build — into one file that reads like a single measurement.
    if out_path.exists() and not append:
        msg = (
            f"{out_path} already exists — appending would silently mix two runs. "
            "Move it aside, pass --out, or pass --append if that is intended."
        )
        raise MatrixError(msg)

    apps = load_corpus(root / PROTOCOL_PATH)
    echo(f"corpus: {len(apps)} pre-registered apps x {len(variants)} variants")

    if skip_rebuild:
        ip = box_ip(server_id)
        echo(f"reusing box {server_id} at {ip} as-is (no wipe, no install)")
    else:
        echo(f"rebuilding dedicated box {server_id} (wipes it; never creates one)")
        ip = rebuild_box(server_id)
        echo(f"box up at {ip}; installing Hop3 (--from local --clean --with all)")
        install_hop3(root, ip)
        echo("hop3-server active")

    cells: list[Cell] = []
    with out_path.open("a", encoding="utf-8") as fh:
        for variant in variants:
            for app in apps:
                cell = run_cell(root, ip, variant, app, logs_dir)
                cells.append(cell)
                fh.write(cell.to_json() + "\n")
                fh.flush()  # survive an interrupted run
                echo(f"  {variant:8} {app:16} {cell.status:9} {cell.seconds or '-'}s")
    return cells
