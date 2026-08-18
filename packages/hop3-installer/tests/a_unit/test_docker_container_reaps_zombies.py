# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The test container needs a real init as PID 1.

PID 1 was `sleep infinity`, which never calls wait(), so nothing reaped exited
children. Any package whose postinst forks a helper and waits for it to
disappear then hung on a zombie. mysql-server-8.0 does exactly that: it starts a
temporary mysqld for the upgrade step, shuts it down — cleanly, the error log
says "Shutdown complete" — and polls for the pid to go. The pid stayed
`<defunct>`, so the postinst reported "Unable to shut down server with process
id N", dpkg failed, and the run died three steps later under an unrelated
message about apt-utils being missing.

`--init` makes docker put tini at PID 1, which reaps. Verified against the same
image: mysql-server and postfix both configure with exit 0 under `--init` and
fail without it — nothing else about the container differs.
"""

from __future__ import annotations

from unittest.mock import patch

from hop3_installer.deployer.backends.docker import DockerDeployBackend
from hop3_installer.deployer.config import DeployConfig


def _run_argv() -> list[str]:
    """The argv of the `docker run` the backend issues to start a container."""
    backend = DockerDeployBackend(DeployConfig(use_docker=True))
    with patch("subprocess.run") as run:
        run.return_value.returncode = 0
        backend._start_container()
        return list(run.call_args[0][0])


def test_the_container_runs_under_an_init():
    argv = _run_argv()

    assert "--init" in argv


def test_the_init_flag_precedes_the_image():
    """
    A `docker run` flag after the image name is an argument to the command.

    `--init` landing there would be passed to `sleep` instead of docker, so the
    container would start without an init and the failure would look like the
    zombie bug all over again.
    """
    argv = _run_argv()

    assert argv.index("--init") < argv.index("sleep")


def test_the_container_can_manage_the_firewall():
    """
    rootd needs CAP_NET_ADMIN, and exits without it.

    It opens each app's fixed `[[ports]]` in the nftables `inet hop3` table.
    While `nftables` was missing from the installer's package list this was
    invisible — no `nft` binary, so rootd skipped reconciliation and started.
    Installing the package made it try, `nft add table` returned "Operation not
    permitted", and rootd exited. Proxy reloads go through rootd too, so every
    single deploy then failed, not just the two apps declaring ports.
    """
    argv = _run_argv()

    assert "--cap-add=NET_ADMIN" in argv
    assert argv.index("--cap-add=NET_ADMIN") < argv.index("sleep")
