# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""The feature/redeploy installer path must forward --acme-email.

Regression: `hop3-deploy --local --acme-email X` silently dropped the flag on
the feature-install path, so the server installer ran without it and wrote
ACME_ENGINE=self-signed — certs never became Let's Encrypt despite the flag.
"""

from __future__ import annotations

from hop3_installer.deployer.config import DeployConfig
from hop3_installer.deployer.deploy import Deployer


def _cmd(**cfg) -> str:
    # The helper only reads self.config; the backend is unused here.
    deployer = Deployer(DeployConfig(**cfg), backend=object())  # type: ignore[arg-type]
    return deployer._feature_install_command("python3")


def test_feature_install_forwards_acme_email():
    cmd = _cmd(with_features=["all"], acme_email="sf@fermigier.com")
    assert "--acme-email sf@fermigier.com" in cmd
    assert "--with all" in cmd
    # Issuance stays deferred to `hop3 cert renew`, not every redeploy.
    assert "--skip-acme" in cmd


def test_feature_install_omits_acme_email_when_unset():
    cmd = _cmd(with_features=["redis"])
    assert "--acme-email" not in cmd
