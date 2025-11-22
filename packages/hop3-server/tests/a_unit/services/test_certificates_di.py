# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for CertificatesManager with Dishka DI."""

from __future__ import annotations

from hop3.di import create_container
from hop3.services.certificates import CertificatesManager


def test_certificates_manager_with_di(di_container):
    """Test that CertificatesManager can be retrieved from DI container."""
    cert_manager = di_container.get(CertificatesManager)
    assert cert_manager is not None
    assert isinstance(cert_manager, CertificatesManager)


def test_certificates_manager_is_singleton(di_container):
    """Test that CertificatesManager is a singleton in APP scope."""
    cert_manager1 = di_container.get(CertificatesManager)
    cert_manager2 = di_container.get(CertificatesManager)
    assert cert_manager1 is cert_manager2


def test_create_container_returns_fresh_instance():
    """Test that create_container() returns a fresh instance each time."""
    container1 = create_container()
    container2 = create_container()
    try:
        # Different container instances
        assert container1 is not container2

        # But each container provides singletons within its own scope
        cert_manager1a = container1.get(CertificatesManager)
        cert_manager1b = container1.get(CertificatesManager)
        assert cert_manager1a is cert_manager1b

        cert_manager2a = container2.get(CertificatesManager)
        cert_manager2b = container2.get(CertificatesManager)
        assert cert_manager2a is cert_manager2b

        # Services from different containers are different instances
        assert cert_manager1a is not cert_manager2a
    finally:
        container1.close()
        container2.close()
