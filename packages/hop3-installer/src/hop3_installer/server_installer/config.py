# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Configuration for server installer."""

from __future__ import annotations

from dataclasses import dataclass, field

from hop3_installer.common import env_bool, env_str
from hop3_installer.constants import ALL_FEATURES, DEFAULT_BRANCH_PRODUCTION


@dataclass
class ServerInstallerConfig:
    """Configuration for server installer."""

    # Installation source
    version: str | None = None
    use_git: bool = False
    branch: str = DEFAULT_BRANCH_PRODUCTION
    local_path: str | None = None
    pre_release: bool = False  # Allow pre-release versions from PyPI

    # Installation options
    force: bool = False
    skip_deps: bool = False
    skip_nginx: bool = False
    skip_postgres: bool = False
    skip_acme: bool = False
    domain: str | None = None
    acme_email: str | None = None  # Email for Let's Encrypt registration
    verbose: bool = False

    # Optional features
    features: set[str] = field(default_factory=set)

    @property
    def with_mysql(self) -> bool:
        return "mysql" in self.features

    @property
    def with_redis(self) -> bool:
        return "redis" in self.features

    @property
    def with_docker(self) -> bool:
        return "docker" in self.features

    @classmethod
    def from_env(cls) -> ServerInstallerConfig:
        """Create config from environment variables."""
        features = parse_features(env_str("HOP3_WITH", ""))

        return cls(
            version=env_str("HOP3_VERSION"),
            use_git=env_bool("HOP3_GIT"),
            branch=env_str("HOP3_BRANCH", DEFAULT_BRANCH_PRODUCTION),
            local_path=env_str("HOP3_LOCAL_PACKAGE"),
            pre_release=env_bool("HOP3_PRE"),
            force=env_bool("HOP3_FORCE"),
            skip_deps=env_bool("HOP3_SKIP_DEPS"),
            skip_nginx=env_bool("HOP3_SKIP_NGINX"),
            skip_postgres=env_bool("HOP3_SKIP_POSTGRES"),
            skip_acme=env_bool("HOP3_SKIP_ACME"),
            domain=env_str("HOP3_DOMAIN"),
            acme_email=env_str("HOP3_ACME_EMAIL"),
            verbose=env_bool("HOP3_VERBOSE"),
            features=features,
        )


def parse_features(features_str: str) -> set[str]:
    """Parse comma-separated feature list.

    Args:
        features_str: Comma-separated features (e.g., "mysql,redis" or "all")

    Returns:
        Set of feature names to install
    """
    if not features_str:
        return set()

    features_str = features_str.lower().strip()

    # Handle "all" keyword
    if features_str == "all":
        return ALL_FEATURES.copy()

    # Parse comma-separated list
    features = set()
    for feature in features_str.split(","):
        feature = feature.strip()
        if feature == "all":
            features.update(ALL_FEATURES)
        elif feature in ALL_FEATURES:
            features.add(feature)
        elif feature == "postgres":
            # PostgreSQL is always installed by default, ignore
            pass
        elif feature:
            # Unknown feature - will be warned about in main
            pass

    return features
