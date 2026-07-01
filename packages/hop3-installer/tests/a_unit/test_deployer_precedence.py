# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Flag/env precedence for hop3-deploy (ADR 052 D7).

An explicitly-passed flag must win over an env-supplied value **even when the
flag's value equals the built-in default**. The old code applied a value option
only when it differed from the argparse default, so ``HOP3_SSH_USER=deploy`` in
the environment silently swallowed ``--ssh-user root`` (root == default). These
tests pin the corrected precedence: explicit flag > env var > default.
"""

from __future__ import annotations

from hop3_installer.deployer.cli import config_from_args, create_parser
from hop3_installer.deployer.config import (
    DEFAULT_ADMIN_USER,
    DEFAULT_SSH_USER,
    DOCKER_IMAGE,
)


def _config(argv: list[str]):
    return config_from_args(create_parser().parse_args(argv))


def test_explicit_flag_beats_env_even_at_default(clean_env):
    # The regression: env sets a non-default user; the explicit flag equals the
    # default and must still win.
    clean_env["HOP3_SSH_USER"] = "deploy"
    config = _config(["--docker", "--ssh-user", "root"])
    assert config.ssh_user == "root"


def test_env_value_used_when_flag_absent(clean_env):
    clean_env["HOP3_SSH_USER"] = "deploy"
    config = _config(["--docker"])
    assert config.ssh_user == "deploy"


def test_default_when_neither_env_nor_flag(clean_env):
    config = _config(["--docker"])
    assert config.ssh_user == DEFAULT_SSH_USER
    assert config.admin_user == DEFAULT_ADMIN_USER
    assert config.docker_image == DOCKER_IMAGE


def test_explicit_admin_user_at_default_beats_env(clean_env):
    clean_env["HOP3_ADMIN_USER"] = "superadmin"
    config = _config(["--docker", "--admin-user", "admin"])
    assert config.admin_user == "admin"


def test_explicit_docker_image_at_default_beats_env_free_field(clean_env):
    # docker_image has no env var, but the same precedence rule applies: an
    # explicit value equal to the default must still be accepted, not dropped.
    config = _config(["--docker", "--docker-image", DOCKER_IMAGE])
    assert config.docker_image == DOCKER_IMAGE


def test_explicit_branch_equal_default_applies_and_implies_git(clean_env):
    # Previously `--branch devel` (== default) was a no-op, so it did NOT imply
    # git and the deploy silently used PyPI. Now an explicit --branch always
    # applies and implies git.
    config = _config(["--docker", "--branch", "devel"])
    assert config.branch == "devel"
    assert config.use_git is True


def test_branch_absent_does_not_imply_git(clean_env):
    config = _config(["--docker"])
    assert config.use_git is False
