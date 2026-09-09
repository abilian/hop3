# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
`hop3-backup-server`: snapshot a Hop3 server from the operator's machine.

The sibling of `hop3-deploy-server`, for the step that comes before it.
Uploads the server-side script bundled with this package
(``hop3-server-backup.sh``), runs it as root over ssh under a label, streams
its output, and can fetch the snapshot back with ``--fetch``. The label is
``pre-<version>`` when ``--version`` names the release about to be installed,
else a timestamp, so every snapshot says what it was taken for.
"""

from __future__ import annotations

import argparse
import shlex
import sys
from datetime import datetime
from pathlib import Path

from hop3_installer.constants import DEFAULT_SSH_USER
from hop3_installer.deployer.backends.ssh import SSHDeployBackend
from hop3_installer.deployer.config import DeployConfig

#: The server-side script, shipped inside this package next to this module.
SERVER_SCRIPT = Path(__file__).with_name("hop3-server-backup.sh")
#: Where it lands on the server. `sbin`: it is root's tool.
REMOTE_SCRIPT = "/usr/local/sbin/hop3-server-backup.sh"
#: Where the server-side script writes when told nothing else.
REMOTE_BACKUP_ROOT = "/var/backups/hop3"


def infer_label(label: str | None, version: str | None) -> str:
    """``--label`` wins; else ``pre-<version>``; else a timestamp."""
    if label:
        return label
    if version:
        return f"pre-{version}"
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def remote_command(
    *, label: str, dest: str, skip_apps: bool, docker_volumes: bool
) -> str:
    """The server-side invocation, every argument quoted."""
    argv = [REMOTE_SCRIPT, "--label", label, "--dest", dest]
    if skip_apps:
        argv.append("--skip-apps")
    if docker_volumes:
        argv.append("--docker-volumes")
    return shlex.join(argv)


def run_backup(
    backend: SSHDeployBackend,
    *,
    label: str,
    dest: str | None,
    skip_apps: bool,
    docker_volumes: bool,
    fetch: Path | None,
    script: Path = SERVER_SCRIPT,
) -> int:
    """
    Upload the script, run it, report where the snapshot is. Returns an exit code.

    ``dest`` is decided here rather than on the server, so this side always
    knows the directory to name and to fetch: ``/var/backups/hop3/<host>-<label>``
    unless given.
    """
    target = backend.config.ssh_target
    print(f"Snapshotting {target} as '{label}'", flush=True)
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
    if dest is None:
        host = backend.run("hostname -s", check=False)
        short = (
            host.stdout.strip() if host.success and host.stdout.strip() else "server"
        )
        dest = f"{REMOTE_BACKUP_ROOT}/{short}-{label}"
    rc = backend.run_streaming(
        remote_command(
            label=label, dest=dest, skip_apps=skip_apps, docker_volumes=docker_volumes
        )
    )
    if rc != 0:
        print(
            f"  ✗ the snapshot did not complete on {target} (exit {rc}); see above",
            flush=True,
        )
        return rc
    print(f"  ✓ snapshot on {target}: {dest}", flush=True)
    if fetch is not None:
        local = fetch / Path(dest).name
        if not backend.download_dir(dest, local):
            print(
                f"  ✗ the snapshot is on the server but could not be fetched to {local}",
                flush=True,
            )
            return 1
        print(f"  ✓ fetched to {local}", flush=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hop3-backup-server",
        description="Snapshot a Hop3 server before an upgrade (or any time).",
        epilog=(
            "Examples:\n"
            "  hop3-backup-server --host server.example.com --version 0.7.3\n"
            "  hop3-backup-server --host server.example.com --fetch ~/backups\n"
            "  hop3-backup-server --host server.example.com --label weekly --skip-apps"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--host", required=True, help="Server to snapshot")
    parser.add_argument(
        "--user",
        "--ssh-user",
        "-u",
        dest="ssh_user",
        default=DEFAULT_SSH_USER,
        help=f"SSH user (default: {DEFAULT_SSH_USER}); the script needs root",
    )
    parser.add_argument("--port", type=int, default=22, help="SSH port (default: 22)")
    parser.add_argument(
        "--identity",
        "--ssh-key",
        "-i",
        dest="ssh_key",
        help="SSH private key (like `ssh -i`; default: ssh's own identity)",
    )
    parser.add_argument(
        "--version",
        help="The release about to be installed; labels the snapshot pre-<version>",
    )
    parser.add_argument(
        "--label", help="Snapshot label (default: pre-<version>, else a timestamp)"
    )
    parser.add_argument(
        "--dest",
        help=f"Directory on the server (default: {REMOTE_BACKUP_ROOT}/<host>-<label>)",
    )
    parser.add_argument(
        "--skip-apps", action="store_true", help="Do not archive the apps tree"
    )
    parser.add_argument(
        "--docker-volumes", action="store_true", help="Also archive every Docker volume"
    )
    parser.add_argument(
        "--fetch",
        type=Path,
        metavar="DIR",
        help="Copy the snapshot into this local directory",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = DeployConfig(
        host=args.host, ssh_user=args.ssh_user, ssh_port=args.port, ssh_key=args.ssh_key
    )
    return run_backup(
        SSHDeployBackend(config),
        label=infer_label(args.label, args.version),
        dest=args.dest,
        skip_apps=args.skip_apps,
        docker_volumes=args.docker_volumes,
        fetch=args.fetch,
    )


if __name__ == "__main__":
    sys.exit(main())
