# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Configuration management for the daily system test framework."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Self

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


@dataclass(frozen=True)
class HetznerConfig:
    """Hetzner Cloud API configuration."""

    api_token: str
    server_id: int
    image: str = "debian-12"
    ssh_key_name: str | None = None

    @classmethod
    def from_dict(cls, data: dict, env: dict[str, str] | None = None) -> Self:
        """Create from dictionary, resolving environment variables."""
        env = env or dict(os.environ)

        api_token = _resolve_env(data.get("api_token", ""), env)
        if not api_token:
            api_token = env.get("HETZNER_API_TOKEN", "")

        server_id_raw = data.get("server_id", "")
        if isinstance(server_id_raw, str) and server_id_raw.startswith("$"):
            server_id_raw = env.get(server_id_raw[1:], "")
        server_id = int(server_id_raw) if server_id_raw else 0

        if not server_id:
            server_id = int(env.get("HETZNER_SERVER_ID", "0"))

        return cls(
            api_token=api_token,
            server_id=server_id,
            image=data.get("image", "debian-12"),
            ssh_key_name=data.get("ssh_key_name"),
        )


@dataclass(frozen=True)
class DeploymentConfig:
    """Deployment configuration."""

    branch: str = "devel"
    domain: str | None = None
    acme_email: str | None = None
    use_local_code: bool = True
    clean_before: bool = True
    verbose: bool = False
    use_local_repo: bool = False
    """Use local working directory instead of cloning from git."""
    local_repo_path: Path | None = None
    """Path to local repo (defaults to current working directory)."""


@dataclass(frozen=True)
class TestConfig:
    """Test execution configuration."""

    suites: list[str] = field(default_factory=lambda: ["test-apps"])
    timeout_per_test: int = 300
    fail_fast: bool = False
    docker_apps_subset: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Config:
    """Main configuration container."""

    hetzner: HetznerConfig
    deployment: DeploymentConfig
    tests: TestConfig
    report_dir: Path = field(default_factory=lambda: Path("./reports"))

    @classmethod
    def from_file(cls, path: Path) -> Self:
        """Load configuration from a TOML file."""
        with path.open("rb") as f:
            data = tomllib.load(f)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        """Create configuration from a dictionary."""
        hetzner_data = data.get("hetzner", {})
        deployment_data = data.get("deployment", {})
        tests_data = data.get("tests", {})

        return cls(
            hetzner=HetznerConfig.from_dict(hetzner_data),
            deployment=DeploymentConfig(
                branch=deployment_data.get("branch", "devel"),
                domain=deployment_data.get("domain"),
                acme_email=deployment_data.get("acme_email"),
                use_local_code=deployment_data.get("use_local_code", True),
                clean_before=deployment_data.get("clean_before", True),
                verbose=deployment_data.get("verbose", False),
            ),
            tests=TestConfig(
                suites=tests_data.get("suites", ["test-apps"]),
                timeout_per_test=tests_data.get("timeout_per_test", 300),
                fail_fast=tests_data.get("fail_fast", False),
                docker_apps_subset=tests_data.get("docker_apps_subset", []),
            ),
            report_dir=Path(data.get("report_dir", "./reports")),
        )

    @classmethod
    def from_env(cls) -> Self:
        """Create configuration from environment variables only."""
        env = dict(os.environ)

        return cls(
            hetzner=HetznerConfig(
                api_token=env.get("HETZNER_API_TOKEN", ""),
                server_id=int(env.get("HETZNER_SERVER_ID", "0")),
                image=env.get("HETZNER_IMAGE", "debian-12"),
            ),
            deployment=DeploymentConfig(
                branch=env.get("HOP3_BRANCH", "devel"),
                domain=env.get("HOP3_DOMAIN"),
                acme_email=env.get("HOP3_ACME_EMAIL"),
            ),
            tests=TestConfig(
                suites=env.get("HOP3_TEST_SUITES", "test-apps").split(","),
            ),
            report_dir=Path(env.get("HOP3_REPORT_DIR", "./reports")),
        )

    def validate(self) -> list[str]:
        """Validate configuration and return list of errors."""
        errors = []

        if not self.hetzner.api_token:
            errors.append("Hetzner API token is required (HETZNER_API_TOKEN)")
        if not self.hetzner.server_id:
            errors.append("Hetzner server ID is required (HETZNER_SERVER_ID)")

        return errors


def _resolve_env(value: str, env: dict[str, str]) -> str:
    """Resolve environment variable reference in a string."""
    if value.startswith("$"):
        var_name = value[1:]
        # Handle ${VAR} syntax
        if var_name.startswith("{") and var_name.endswith("}"):
            var_name = var_name[1:-1]
        return env.get(var_name, "")
    return value


def load_config(
    config_file: Path | None = None,
    cli_overrides: dict | None = None,
) -> Config:
    """Load configuration with CLI overrides.

    Priority (highest to lowest):
    1. CLI arguments
    2. Config file
    3. Environment variables
    """
    # Start with environment-based config
    if config_file and config_file.exists():
        config = Config.from_file(config_file)
    else:
        config = Config.from_env()

    # Apply CLI overrides
    if cli_overrides:
        config = _apply_overrides(config, cli_overrides)

    return config


def _apply_overrides(config: Config, overrides: dict) -> Config:
    """Apply CLI overrides to configuration."""
    # Since we use frozen dataclasses, we need to create new instances
    hetzner = config.hetzner
    deployment = config.deployment
    tests = config.tests
    report_dir = config.report_dir

    if "server_id" in overrides and overrides["server_id"]:
        hetzner = HetznerConfig(
            api_token=hetzner.api_token,
            server_id=overrides["server_id"],
            image=hetzner.image,
            ssh_key_name=hetzner.ssh_key_name,
        )

    if "branch" in overrides and overrides["branch"]:
        deployment = DeploymentConfig(
            branch=overrides["branch"],
            domain=deployment.domain,
            acme_email=deployment.acme_email,
            use_local_code=deployment.use_local_code,
            clean_before=deployment.clean_before,
            verbose=deployment.verbose,
            use_local_repo=deployment.use_local_repo,
            local_repo_path=deployment.local_repo_path,
        )

    if overrides.get("use_local_repo") or overrides.get("local_repo_path"):
        deployment = DeploymentConfig(
            branch=deployment.branch,
            domain=deployment.domain,
            acme_email=deployment.acme_email,
            use_local_code=deployment.use_local_code,
            clean_before=deployment.clean_before,
            verbose=deployment.verbose,
            use_local_repo=overrides.get("use_local_repo", deployment.use_local_repo),
            local_repo_path=overrides.get(
                "local_repo_path", deployment.local_repo_path
            ),
        )

    if "suites" in overrides and overrides["suites"]:
        tests = TestConfig(
            suites=overrides["suites"],
            timeout_per_test=tests.timeout_per_test,
            fail_fast=tests.fail_fast,
            docker_apps_subset=tests.docker_apps_subset,
        )

    if "report_dir" in overrides and overrides["report_dir"]:
        report_dir = Path(overrides["report_dir"])

    return Config(
        hetzner=hetzner,
        deployment=deployment,
        tests=tests,
        report_dir=report_dir,
    )
