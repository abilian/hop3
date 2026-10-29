# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""LocalBuilder: explicit toolchain selection and multi-toolchain projects."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hop3.config import HopConfig
from hop3.core.protocols import BuildContext, DeploymentContext
from hop3.lib import Abort
from hop3.plugins.build.local_build.builder import LocalBuilder
from hop3.plugins.deploy.uwsgi.deployer import UWSGIDeployer
from hop3.toolchains import NodeToolchain, PythonToolchain

if TYPE_CHECKING:
    from pathlib import Path


def _ctx(tmp_path: Path, files: dict[str, str], app_config: dict) -> BuildContext:
    src = tmp_path / "src"
    src.mkdir()
    for name, content in files.items():
        (src / name).write_text(content)
    return BuildContext(app_name="myapp", source_path=src, app_config=app_config)


@pytest.fixture(autouse=True)
def _build_log_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(HopConfig, "_instance", HopConfig(hop3_root=tmp_path))


def test_an_unknown_explicit_toolchain_names_the_available_ones(tmp_path):
    """A typo used to warn, then fail as "No language toolchain detected"."""
    ctx = _ctx(tmp_path, {}, {"hop3_config": {"build": {"toolchain": "pyhton"}}})
    builder = LocalBuilder(ctx)
    assert builder.accept()  # an explicit toolchain is trusted at accept time

    with pytest.raises(Abort, match=r"no toolchain is named 'pyhton'.*python"):
        builder.build()


def test_a_python_and_node_project_builds_one_python_artifact(tmp_path, monkeypatch):
    """
    Django with npm-built assets: both toolchains accept.

    The combined artifact used to be kind "multi-language" with no runtime,
    which no deployer accepts, so the deploy failed after a full build.
    """
    for step in ("make_virtual_env", "install_virtualenv"):
        monkeypatch.setattr(PythonToolchain, step, lambda self: None)
    for step in ("install_node", "install_modules"):
        monkeypatch.setattr(NodeToolchain, step, lambda self, env: None)
    ctx = _ctx(
        tmp_path,
        {"requirements.txt": "django==5.0\n", "package.json": "{}", "wsgi.py": ""},
        {"procfile": {"workers": {}}},
    )

    artifact = LocalBuilder(ctx).build()

    assert artifact.kind == "python"
    assert artifact.runtime.workers == {"wsgi": "wsgi:application"}
    assert artifact.runtime.env_vars["PYTHONUNBUFFERED"] == "1"
    assert artifact.runtime.env_vars["NODE_PATH"].endswith("node_modules")
    venv_bin = str(tmp_path / "venv" / "bin")
    assert artifact.runtime.path_prepend.count(venv_bin) <= 1
    assert artifact.metadata["also_built_by"] == ["node"]

    deploy_ctx = DeploymentContext(
        app_name="myapp", source_path=ctx.source_path, app_config={}
    )
    assert UWSGIDeployer(deploy_ctx, artifact).accept()
