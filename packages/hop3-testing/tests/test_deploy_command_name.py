# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""The engine invokes the renamed `hop3-deploy-server` binary (ADR 052 D10).

hop3-testing shells out to deploy Hop3 onto a target. After the rename it must
call `hop3-deploy-server`, not the deprecated `hop3-deploy` alias (which would
print a deprecation notice into every deploy log). Lockstep with the pyproject
rename (ADR 052 rule R2).
"""

from __future__ import annotations

from hop3_testing.targets.helpers import _build_deploy_command


def test_deploy_command_uses_renamed_binary_docker():
    cmd = _build_deploy_command(
        docker=True,
        host=None,
        user="root",
        container_name="c",
        image="i",
        source="local",
        clean=False,
        branch="main",
        verbose=False,
    )
    assert cmd[0] == "hop3-deploy-server"


def test_deploy_command_uses_renamed_binary_ssh():
    cmd = _build_deploy_command(
        docker=False,
        host="h.example",
        user="root",
        container_name="c",
        image="i",
        source="local",
        clean=False,
        branch="main",
        verbose=False,
    )
    assert cmd[0] == "hop3-deploy-server"
    assert "--host" in cmd


def test_cloud_deploy_manager_delegates_to_shared_builder():
    # ADR 052 Phase 7b collapsed the two wrappers: the cloud path (`run --provider
    # hetzner`) no longer has its OWN deploy command builder — DeploymentManager.deploy()
    # delegates to run_hop3_deploy, so it inherits the shared _build_deploy_command
    # (tested above to emit the renamed binary). A fix to the binary name now
    # reaches BOTH paths — the class of bug that bit Phase 3 can't recur.
    from hop3_testing.system_tests.deployment import (  # noqa: PLC0415
        DeploymentManager,
    )

    assert not hasattr(DeploymentManager, "_build_deploy_command")
    # The shared builder the cloud path now uses emits the renamed binary:
    cmd = _build_deploy_command(
        docker=False,
        host="h.example",
        user="root",
        container_name="c",
        image="i",
        source="local",
        clean=False,
        branch="main",
        verbose=False,
    )
    assert cmd[0] == "hop3-deploy-server"
