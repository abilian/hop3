# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""The deployer must invoke the installer with CANONICAL flags (ADR 052).

hop3-deploy-server shells out to install-server.py. If it passes the deprecated
--local-path / --git spellings, the installer prints a deprecation warning into
every deploy log for the platform's OWN internal call (self-inflicted). It must
use --path / --from git instead. Regression guard for that R2 lockstep miss.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

from hop3_installer.deployer.deploy import Deployer


def _source_args(local_path, **config_fields):
    # _build_source_args reads only self.config; call it on a light stub so we
    # don't need a backend / log file / real Deployer construction.
    cfg = SimpleNamespace(
        use_git=False, branch="main", pypi_version=None, pypi_pre=False
    )
    cfg.__dict__.update(config_fields)
    stub = cast("Deployer", SimpleNamespace(config=cfg))
    return Deployer._build_source_args(stub, local_path)


def test_local_source_uses_canonical_path():
    args = _source_args("/srv/hop3-upload")
    assert "--path /srv/hop3-upload" in args
    assert "--local-path" not in args  # not the deprecated installer spelling


def test_git_source_uses_from_git():
    args = _source_args(None, use_git=True, branch="release")
    assert args.strip().startswith("--from git")
    assert "--branch release" in args


def test_pypi_source_unaffected():
    args = _source_args(None, pypi_version="0.4.0", pypi_pre=True)
    assert "--version 0.4.0" in args
    assert "--pre" in args
