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
        use_local=False,
        clean=False,
        branch="devel",
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
        use_local=True,
        clean=False,
        branch="devel",
        verbose=False,
    )
    assert cmd[0] == "hop3-deploy-server"
    assert "--host" in cmd


def test_cloud_deploy_manager_uses_renamed_binary():
    # The `hop3-test cloud` path has its OWN deploy wrapper (system_tests) —
    # Phase 3 initially missed it, emitting the deprecation warning which the
    # cloud path then mis-reported as the failure. Pin it here.
    from hop3_testing.system_tests.config import DeploymentConfig  # noqa: PLC0415
    from hop3_testing.system_tests.deployment import (  # noqa: PLC0415
        DeploymentManager,
    )

    mgr = DeploymentManager(host="h.example", config=DeploymentConfig())
    cmd = mgr._build_deploy_command()
    assert "hop3-deploy-server" in cmd
    assert "hop3-deploy" not in cmd  # not the deprecated bare name
