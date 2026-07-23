# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
Shared fixtures for nix gen tests.

Uses inline specs instead of importing from the app specs directory,
so tests are self-contained and don't depend on external app configs.
"""

from __future__ import annotations

import dataclasses

import pytest

from hop3.plugins.build.nix.gen.spec import (
    AppSpec,
    ConditionalEnvVar,
    ConfigFile,
    FileMapping,
    JavaWarPayload,
    NixpkgsWrapperPayload,
    PhpAppPayload,
    PrebuiltArchivePayload,
    PrebuiltBinaryPayload,
    PythonVenvPayload,
    Source,
)


@pytest.fixture
def miniflux_spec() -> AppSpec:
    """Minimal prebuilt-binary spec."""
    return AppSpec(
        pname="miniflux",
        version="2.1.1",
        description="Minimalist RSS reader",
        source=Source(
            url="https://example.com/miniflux-linux-amd64",
            sha256="abc123",
            executable=True,
        ),
        env_exports={
            "LISTEN_ADDR": "0.0.0.0:${PORT:-8080}",
            "RUN_MIGRATIONS": "1",
        },
        conditional_env_exports=[
            ConditionalEnvVar(
                name="DATABASE_URL",
                condition_var="DATABASE_URL",
                value="postgres://${PGUSER:-miniflux}:${PGPASSWORD:-}@${PGHOST:-localhost}:${PGPORT:-5432}/${PGDATABASE:-miniflux}?sslmode=disable",
            ),
        ],
        runtime_env={"RUN_MIGRATIONS": "1"},
        payload=PrebuiltBinaryPayload(
            binary_name="miniflux",
        ),
    )


@pytest.fixture
def gitea_spec() -> AppSpec:
    """Prebuilt-binary with INI config and exec args."""
    return AppSpec(
        pname="gitea",
        version="1.21.4",
        description="Self-hosted Git service",
        exec_args=["web"],
        source=Source(
            url="https://example.com/gitea-linux-amd64",
            sha256="def456",
            executable=True,
        ),
        local_vars={"PORT": "${PORT:-8080}"},
        env_exports={"GITEA_WORK_DIR": "$PWD"},
        pre_exec_commands=["mkdir -p custom/conf data"],
        config_files=[
            ConfigFile(
                path="custom/conf/app.ini",
                format="ini",
                sections={
                    "server": {"HTTP_PORT": "${PORT}"},
                    "security": {
                        "SECRET_KEY": "$(head -c 32 /dev/urandom | base64)",
                    },
                },
            ),
        ],
        payload=PrebuiltBinaryPayload(
            binary_name="gitea",
        ),
    )


@pytest.fixture
def grafana_spec() -> AppSpec:
    """Prebuilt-archive spec."""
    return AppSpec(
        pname="grafana",
        version="11.3.2",
        description="Observability platform",
        source=Source(
            url="https://example.com/grafana.tar.gz",
            sha256="ghi789",
            archive="tar-gz",
        ),
        source_root="grafana-v${version}",
        exec_target="grafana",
        exec_args=["server"],
        payload=PrebuiltArchivePayload(
            file_mappings=[
                FileMapping(source="bin/*", destination="bin/"),
                FileMapping(source="conf", destination="share/grafana/"),
            ],
        ),
    )


@pytest.fixture
def wordpress_spec() -> AppSpec:
    """PHP app spec."""
    return AppSpec(
        pname="wordpress",
        version="6.4.2",
        description="CMS",
        source=Source(
            url="https://example.com/wordpress.tar.gz",
            sha256="jkl012",
            archive="tar-gz",
        ),
        extra_paths=["${php}/bin"],
        payload=PhpAppPayload(
            php_extensions=["mysqli", "gd"],
        ),
    )


@pytest.fixture
def jenkins_spec() -> AppSpec:
    """Java WAR spec."""
    return AppSpec(
        pname="jenkins",
        version="2.541.2",
        description="CI/CD server",
        runtime_package="jdk17",
        source=Source(url="https://example.com/jenkins.war", sha256="mno345"),
        exec_args=['--httpPort="${PORT:-8080}"'],
        extra_paths=["${jdk}/bin"],
        payload=JavaWarPayload(
            war_file="jenkins.war",
        ),
    )


@pytest.fixture
def isso_spec() -> AppSpec:
    """Python venv spec."""
    return AppSpec(
        pname="isso",
        version="0.13.1",
        description="Commenting system",
        source=Source(url="file:///dev/null", sha256=""),
        exec_target="isso",
        exec_args=["-c", "config.cfg"],
        extra_paths=["$out/venv/bin"],
        payload=PythonVenvPayload(
            requirements="requirements.txt",
            deps_hash="sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
        ),
    )


@pytest.fixture
def radicale_spec() -> AppSpec:
    """Nixpkgs wrapper spec."""
    return AppSpec(
        pname="radicale",
        version="",
        description="CalDAV server",
        source=Source(url="file:///dev/null", sha256=""),
        exec_target="radicale",
        extra_paths=["${radicale}/bin"],
        payload=NixpkgsWrapperPayload(
            package="radicale",
        ),
    )


ALL_FIXTURE_NAMES = [
    "miniflux_spec",
    "gitea_spec",
    "grafana_spec",
    "wordpress_spec",
    "jenkins_spec",
    "isso_spec",
    "radicale_spec",
]


def spec_for(payload_cls, **kwargs) -> AppSpec:
    """
    Build an AppSpec from flat kwargs, routing payload fields automatically.

    Test helpers take overrides as flat keyword arguments; this splits them by
    what the payload dataclass actually declares, so a caller never has to
    restate which half a field lives in. An unknown name still raises, from the
    dataclass constructor.
    """
    fields = {f.name for f in dataclasses.fields(payload_cls)}
    payload = payload_cls(**{k: v for k, v in kwargs.items() if k in fields})
    core = {k: v for k, v in kwargs.items() if k not in fields}
    return AppSpec(payload=payload, **core)
