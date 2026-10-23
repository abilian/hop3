# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
`hop3-restore-server`: put a server back to a snapshot, from the operator's machine.

The other half of `hop3-backup-server`. Uploads the bundled server-side script
(``hop3-server-restore.sh``), optionally uploads a snapshot kept locally
(``--from-local``), and runs the restore as root over ssh, streaming its
report. It replaces the server's state, so it refuses to run without
``--yes``; the server-side script refuses too, on its own.
"""

from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path

from hop3_installer.deployer.backends.ssh import SSHDeployBackend
from hop3_installer.deployer.backup import (
    REMOTE_BACKUP_ROOT,
    add_ssh_arguments,
    backend_from,
)

#: The server-side script, shipped inside this package next to this module.
SERVER_SCRIPT = Path(__file__).with_name("hop3-server-restore.sh")
REMOTE_SCRIPT = "/usr/local/sbin/hop3-server-restore.sh"
#: What the script can restore, each by itself with `--only`.
COMPONENTS = (
    "db",
    "config",
    "apps",
    "postgres",
    "mysql",
    "redis",
    "garage",
    "docker-volumes",
)


def remote_snapshot_path(snapshot: str) -> str:
    """A bare name is a directory under the server's backup root."""
    return snapshot if snapshot.startswith("/") else f"{REMOTE_BACKUP_ROOT}/{snapshot}"


def remote_command(*, snapshot_dir: str, only: str | None) -> str:
    argv = [REMOTE_SCRIPT, snapshot_dir, "--yes"]
    if only:
        argv += ["--only", only]
    return shlex.join(argv)


def run_restore(
    backend: SSHDeployBackend,
    *,
    snapshot: str,
    from_local: Path | None,
    only: str | None,
    script: Path = SERVER_SCRIPT,
) -> int:
    """Upload what is needed, run the restore, return an exit code."""
    target = backend.config.ssh_target
    snapshot_dir = remote_snapshot_path(snapshot)
    if from_local is not None:
        if not (from_local / "SHA256SUMS").is_file():
            print(f"  ✗ {from_local} is not a snapshot (no SHA256SUMS)", flush=True)
            return 1
        print(f"Uploading {from_local} to {target}:{snapshot_dir}", flush=True)
        if not backend.upload_dir(from_local, snapshot_dir):
            print(f"  ✗ could not upload the snapshot to {target}", flush=True)
            return 1
    print(f"Restoring {target} from {snapshot_dir}", flush=True)
    if not backend.upload_file(script, REMOTE_SCRIPT):
        print(
            f"  ✗ could not upload {script.name} to {target}:{REMOTE_SCRIPT}",
            flush=True,
        )
        return 1
    chmod = backend.run(f"chmod 0755 {REMOTE_SCRIPT}", check=False)
    if not chmod.success:
        print(
            f"  ✗ chmod on {REMOTE_SCRIPT} failed: {(chmod.stderr or chmod.stdout).strip()}",
            flush=True,
        )
        return 1
    rc = backend.run_streaming(remote_command(snapshot_dir=snapshot_dir, only=only))
    if rc != 0:
        print(
            f"  ✗ the restore did not complete on {target} (exit {rc}); see above",
            flush=True,
        )
        return rc
    print(f"  ✓ {target} restored from {snapshot_dir}", flush=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hop3-restore-server",
        description="Put a Hop3 server back to a snapshot taken by hop3-backup-server.",
        epilog=(
            "Examples:\n"
            "  hop3-restore-server --host server.example.com --snapshot prod-pre-0.7.3 --yes\n"
            "  hop3-restore-server --host server.example.com --snapshot prod-pre-0.7.3 "
            "--from-local ~/backups/prod-pre-0.7.3 --yes\n"
            "  hop3-restore-server --host server.example.com --snapshot prod-weekly --only db,config --yes"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_ssh_arguments(parser)
    parser.add_argument(
        "--snapshot",
        required=True,
        help=f"Snapshot name (a directory under {REMOTE_BACKUP_ROOT} on the server) or absolute path",
    )
    parser.add_argument(
        "--from-local",
        type=Path,
        metavar="DIR",
        help="A snapshot fetched to this machine; uploaded to the server first",
    )
    parser.add_argument(
        "--only",
        help=f"Comma-separated components: {','.join(COMPONENTS)}",
    )
    parser.add_argument(
        "--yes", action="store_true", help="Confirm: this replaces the server's state"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.yes:
        print(
            "hop3-restore-server replaces the server's state; pass --yes to proceed",
            flush=True,
        )
        return 2
    return run_restore(
        backend_from(args),
        snapshot=args.snapshot,
        from_local=args.from_local,
        only=args.only,
    )


if __name__ == "__main__":
    sys.exit(main())
