# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Configuration for server installer."""

from __future__ import annotations

from dataclasses import dataclass, field

from hop3_installer.common import env_bool, env_str
from hop3_installer.constants import ALL_FEATURES, DEFAULT_BRANCH_PRODUCTION
from hop3_installer.deprecation import env_bool_with_alias, env_with_alias


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
    # Skip step 4 (hop3-server package install). Used by the deployer when
    # re-running the installer purely to install features: the package was
    # already installed in the prior --local/--git/--pypi step, and
    # reinstalling from PyPI would clobber it (downgrading to whatever
    # PyPI's latest stable is).
    skip_package_install: bool = False
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

    @property
    def with_nix(self) -> bool:
        return "nix" in self.features

    @property
    def with_s3(self) -> bool:
        return "s3" in self.features

    @property
    def with_rust(self) -> bool:
        return "rust" in self.features

    @property
    def with_email(self) -> bool:
        return "email" in self.features

    @classmethod
    def from_env(cls) -> ServerInstallerConfig:
        """Create config from environment variables."""
        features = parse_features(env_str("HOP3_WITH", ""))
        # HOP3_FROM is the canonical source selector (pypi|git|local); HOP3_GIT /
        # HOP3_LOCAL_PACKAGE still work. HOP3_PATH is canonical; HOP3_LOCAL_PACKAGE
        # is the deprecated alias (canonical wins, warns on the old one — D7).
        from_source = env_str("HOP3_FROM", "").lower().strip()

        return cls(
            version=env_str("HOP3_VERSION"),
            use_git=env_bool("HOP3_GIT") or from_source == "git",
            branch=env_str("HOP3_BRANCH", DEFAULT_BRANCH_PRODUCTION),
            local_path=env_with_alias("HOP3_PATH", "HOP3_LOCAL_PACKAGE"),
            pre_release=env_bool("HOP3_PRE"),
            force=env_bool_with_alias("HOP3_CLEAN", "HOP3_FORCE"),
            skip_deps=env_bool("HOP3_SKIP_DEPS"),
            skip_nginx=env_bool("HOP3_SKIP_NGINX"),
            skip_postgres=env_bool("HOP3_SKIP_POSTGRES"),
            skip_acme=env_bool("HOP3_SKIP_ACME"),
            skip_package_install=env_bool("HOP3_SKIP_PACKAGE_INSTALL"),
            domain=env_str("HOP3_DOMAIN"),
            acme_email=env_str("HOP3_ACME_EMAIL"),
            verbose=env_bool("HOP3_VERBOSE"),
            features=features,
        )


def parse_features(features_str: str) -> set[str]:
    """Parse a comma-separated feature list; reject unknown features loudly.

    An unknown ``--with`` value used to be silently dropped (a fail-loud
    violation — the user asked for something they didn't get, with no word).
    Now any unknown token raises ``ValueError`` listing the valid features.
    ``postgres`` is accepted but ignored: it is the always-on baseline, not an
    optional feature. ``all`` expands to every optional feature.

    Args:
        features_str: Comma-separated features (e.g., "mysql,redis" or "all")

    Returns:
        Set of feature names to install

    Raises:
        ValueError: if any token is not a known feature, ``all``, or ``postgres``.
    """
    if not features_str:
        return set()

    features_str = features_str.lower().strip()
    if features_str == "all":
        return ALL_FEATURES.copy()

    features: set[str] = set()
    unknown: list[str] = []
    for raw in features_str.split(","):
        feature = raw.strip()
        if not feature:
            continue
        if feature == "all":
            features.update(ALL_FEATURES)
        elif feature in ALL_FEATURES:
            features.add(feature)
        elif feature in {"postgres", "postgresql"}:
            # Always-on baseline (either spelling); accepted, not a feature.
            continue
        else:
            unknown.append(feature)

    if unknown:
        valid = ", ".join(sorted(ALL_FEATURES))
        msg = (
            f"Unknown --with feature(s): {', '.join(unknown)}. "
            f"Valid features: {valid} (or 'all'). "
            f"PostgreSQL is the always-installed baseline, not a feature."
        )
        raise ValueError(msg)

    return features
