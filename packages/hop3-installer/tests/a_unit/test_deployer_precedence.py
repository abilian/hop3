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
    DeployConfig,
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


# --- ADR 052 D3: --from install-source selector -----------------------------


def test_from_git_selects_git(clean_env):
    config = _config(["--docker", "--from", "git"])
    assert config.use_git is True
    assert "git" in config.install_source


def test_from_local_selects_local(clean_env):
    config = _config(["--docker", "--from", "local"])
    assert config.use_local_code is True
    assert config.install_source == "local code"


def test_from_pypi_is_default_source(clean_env):
    config = _config(["--docker", "--from", "pypi"])
    assert config.use_git is False
    assert config.use_local_code is False
    assert "PyPI" in config.install_source


def test_hop3_from_env_selects_source(clean_env):
    clean_env["HOP3_FROM"] = "git"
    config = _config(["--docker"])
    assert config.use_git is True


def test_default_branch_is_main(clean_env):
    # No --branch, --from git -> the safe default branch (main), not devel.
    config = _config(["--docker", "--from", "git"])
    assert config.branch == "main"


# --- ADR 052 D2: canonical target flags (--user / --identity) ---------------


def test_user_is_alias_for_ssh_user(clean_env):
    config = _config(["--host", "h", "--user", "deploy"])
    assert config.ssh_user == "deploy"


def test_ssh_user_still_accepted(clean_env):
    config = _config(["--host", "h", "--ssh-user", "deploy"])
    assert config.ssh_user == "deploy"


def test_identity_is_alias_for_ssh_key(clean_env):
    config = _config(["--host", "h", "--identity", "/k"])
    assert config.ssh_key == "/k"


def test_ssh_key_still_accepted(clean_env):
    config = _config(["--host", "h", "--ssh-key", "/k"])
    assert config.ssh_key == "/k"


def test_hop3_host_env_is_canonical_target(clean_env):
    clean_env["HOP3_HOST"] = "canonical.example"
    config = _config([])
    assert config.host == "canonical.example"


def test_hop3_ssh_key_env(clean_env):
    clean_env["HOP3_SSH_KEY"] = "/env/key"
    config = _config(["--host", "h"])
    assert config.ssh_key == "/env/key"


# --- ADR 052 D7/Phase 8a: canonical env vars (HOP3_VERSION / HOP3_PRE) -------


def test_env_version_canonical(clean_env):
    clean_env["HOP3_VERSION"] = "1.2.3"
    assert DeployConfig.from_env().pypi_version == "1.2.3"


def test_env_version_legacy_alias(clean_env):
    clean_env["HOP3_PYPI_VERSION"] = "0.9"
    assert DeployConfig.from_env().pypi_version == "0.9"


def test_env_version_new_wins_over_legacy(clean_env):
    clean_env["HOP3_VERSION"] = "1.2.3"
    clean_env["HOP3_PYPI_VERSION"] = "0.9"
    assert DeployConfig.from_env().pypi_version == "1.2.3"


def test_env_pre_canonical(clean_env):
    clean_env["HOP3_PRE"] = "1"
    assert DeployConfig.from_env().pypi_pre is True


def test_env_pre_legacy_alias(clean_env):
    clean_env["HOP3_PYPI_PRE"] = "true"
    assert DeployConfig.from_env().pypi_pre is True
