# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for DI container wiring (create_container).

These lock down that create_container() builds a container whose providers
actually wire together: APP-scope services resolve at container level, and
REQUEST-scope repositories / managers resolve inside a request subcontainer
with their dependencies satisfied.
"""

from __future__ import annotations

import os

import pytest

from hop3.config import HopConfig
from hop3.core.backup import BackupManager
from hop3.di import create_container
from hop3.di.container import _get_plugin_providers
from hop3.orm.repositories import (
    AddonCredentialRepository,
    AppRepository,
    BackupRepository,
    EnvVarRepository,
    RevokedTokenRepository,
    RoleRepository,
    UserRepository,
)
from hop3.platform.certificates import CertificatesManager

REQUEST_SCOPED_REPOSITORIES = [
    UserRepository,
    RoleRepository,
    AppRepository,
    AddonCredentialRepository,
    BackupRepository,
    EnvVarRepository,
    RevokedTokenRepository,
]


@pytest.fixture
def container():
    """A fresh container backed by in-memory SQLite (no on-disk side effects)."""
    os.environ["HOP3_DATABASE_URI"] = "sqlite:///:memory:"
    container = create_container()
    try:
        yield container
    finally:
        container.close()
        os.environ.pop("HOP3_DATABASE_URI", None)


def test_create_container_resolves_app_config(container):
    """APP-scope HopConfig is registered and resolvable at container level."""
    config = container.get(HopConfig)

    assert isinstance(config, HopConfig)


def test_create_container_resolves_certificates_manager(container):
    """The core HopCoreProvider wires up CertificatesManager."""
    cert_manager = container.get(CertificatesManager)

    assert isinstance(cert_manager, CertificatesManager)


@pytest.mark.parametrize("repo_cls", REQUEST_SCOPED_REPOSITORIES)
def test_create_container_resolves_each_repository(container, repo_cls):
    """Every repository provider resolves inside a request scope with a session."""
    with container() as request_container:
        repo = request_container.get(repo_cls)

        assert isinstance(repo, repo_cls)


def test_create_container_resolves_backup_manager_with_dependencies(container):
    """BackupManager wires its three repository dependencies, not just itself."""
    with container() as request_container:
        backup_manager = request_container.get(BackupManager)

    assert isinstance(backup_manager, BackupManager)


def test_repositories_share_one_session_within_a_request(container):
    """Repos resolved in the same request scope share a single DB session.

    This is the wiring guarantee that makes a request a unit of work: two
    repositories must see the same session so their writes commit together.
    """
    with container() as request_container:
        user_repo = request_container.get(UserRepository)
        app_repo = request_container.get(AppRepository)

        assert user_repo.session is app_repo.session


def test_each_request_scope_gets_a_fresh_session(container):
    """Distinct request scopes get distinct sessions (no cross-request leakage)."""
    with container() as first_request:
        first_session = first_request.get(UserRepository).session

    with container() as second_request:
        second_session = second_request.get(UserRepository).session

    assert first_session is not second_session


def test_app_scope_services_are_singletons_within_a_container(container):
    """APP-scope services are cached: the same instance is returned each time."""
    config_a = container.get(HopConfig)
    config_b = container.get(HopConfig)

    assert config_a is config_b


def test_separate_containers_are_independent(container):
    """create_container() returns an isolated container each call."""
    os.environ["HOP3_DATABASE_URI"] = "sqlite:///:memory:"
    other = create_container()
    try:
        assert other is not container
        assert other.get(CertificatesManager) is not container.get(CertificatesManager)
    finally:
        other.close()


def test_plugin_providers_are_flattened_to_a_single_list():
    """_get_plugin_providers() flattens the hook's list-of-lists into providers.

    The hook returns one list per plugin; the container expects a flat list of
    provider instances, so a nested list would silently break registration.
    """
    providers = _get_plugin_providers()

    assert isinstance(providers, list)
    assert all(not isinstance(p, list) for p in providers)
