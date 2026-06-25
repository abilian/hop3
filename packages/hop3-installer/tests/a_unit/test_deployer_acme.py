# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""The feature/redeploy installer path must forward --acme-email.

Regression: `hop3-deploy --local --acme-email X` silently dropped the flag on
the feature-install path, so the server installer ran without it and wrote
ACME_ENGINE=self-signed — certs never became Let's Encrypt despite the flag.
"""

from __future__ import annotations

from types import SimpleNamespace

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


class _StubBackend:
    """Minimal backend: only the `test -f .../acme.sh` probe is exercised."""

    def __init__(self, acme_present: bool = True) -> None:
        self.acme_present = acme_present

    def run(self, cmd, check=False):
        return SimpleNamespace(success=self.acme_present)


def _skip_reason(*, acme_present: bool = True, **cfg) -> str | None:
    deployer = Deployer(DeployConfig(**cfg), backend=_StubBackend(acme_present))  # type: ignore[arg-type]
    return deployer._letsencrypt_skip_reason()


def test_skip_reason_no_email():
    """No --acme-email → self-signed, with an actionable reason (not silent)."""
    reason = _skip_reason()
    assert reason is not None
    assert "acme-email" in reason


def test_skip_reason_placeholder_email():
    assert "placeholder" in (_skip_reason(acme_email="admin@example.com") or "")
    assert "placeholder" in (_skip_reason(acme_email="ops@example.com") or "")


def test_skip_reason_acme_sh_missing():
    reason = _skip_reason(acme_email="sf@fermigier.com", acme_present=False)
    assert reason is not None
    assert "acme.sh" in reason


def test_skip_reason_none_when_ready():
    """Real email + acme.sh present → Let's Encrypt is attempted (no skip)."""
    assert _skip_reason(acme_email="sf@fermigier.com", acme_present=True) is None


class _OpensslBackend:
    """Stub returning crafted `openssl x509 -issuer -subject` output."""

    def __init__(self, issuer: str, subject: str, ok: bool = True) -> None:
        self._out = f"issuer={issuer}\nsubject={subject}\n"
        self._ok = ok

    def run(self, cmd, check=False):
        return SimpleNamespace(success=self._ok, stdout=self._out)


def _is_self_signed(issuer: str, subject: str, ok: bool = True) -> bool:
    deployer = Deployer(DeployConfig(), backend=_OpensslBackend(issuer, subject, ok))  # type: ignore[arg-type]
    return deployer._is_self_signed_cert("/home/hop3/ssl/x/fullchain.pem")


def test_self_signed_placeholder_detected():
    """Our placeholder (issuer == subject, marked O=Hop3) is auto-replaceable."""
    same = "CN=hop3.abilian.com, O=Hop3, C=US"
    assert _is_self_signed(issuer=same, subject=same) is True


def test_letsencrypt_cert_not_self_signed():
    assert (
        _is_self_signed(
            issuer="C=US, O=Let's Encrypt, CN=R3",
            subject="CN=hop3.abilian.com",
        )
        is False
    )


def test_unreadable_cert_is_left_alone():
    """openssl failure → not self-signed (don't churn the CA on a bad read)."""
    assert _is_self_signed(issuer="", subject="", ok=False) is False


class _RecordingBackend:
    """Records every command; `--install-cert` and `test -s` get scripted results."""

    def __init__(self, *, acme_ok: bool = True, cert_present: bool = True) -> None:
        self.commands: list[str] = []
        self._acme_ok = acme_ok
        self._cert_present = cert_present

    def run(self, cmd, check=False):
        self.commands.append(cmd)
        if "--install-cert" in cmd:
            ok = self._acme_ok
        elif cmd.startswith("test -s"):
            ok = self._cert_present
        else:
            ok = True
        return SimpleNamespace(success=ok, stdout="", stderr="", returncode=0 if ok else 1)


def _install_cert_commands(*, acme_ok: bool, cert_present: bool) -> list[str]:
    backend = _RecordingBackend(acme_ok=acme_ok, cert_present=cert_present)
    deployer = Deployer(DeployConfig(quiet=True), backend=backend)  # type: ignore[arg-type]
    deployer._install_ssl_cert("hop3.abilian.com", "/home/hop3/ssl/hop3.abilian.com")
    return backend.commands


def test_install_cert_uses_noop_reload_not_sudo():
    """acme.sh runs as hop3; its reloadcmd must not `sudo systemctl reload nginx`
    (rootd retires that sudo right) — use a no-op; the deploy reloads as root."""
    install = next(c for c in _install_cert_commands(acme_ok=True, cert_present=True) if "--install-cert" in c)
    assert "--reloadcmd true" in install
    assert "sudo systemctl reload nginx" not in install


def test_install_cert_proceeds_despite_failed_reloadcmd():
    """acme.sh exits non-zero (reload failed) but the cert is on disk → the
    deploy still reconfigures + reloads nginx itself (an `nginx -t` is run)."""
    cmds = _install_cert_commands(acme_ok=False, cert_present=True)
    assert any("nginx -t" in c for c in cmds)


def test_install_cert_aborts_when_cert_missing():
    """No cert file on disk → genuine failure, nginx is not reconfigured."""
    cmds = _install_cert_commands(acme_ok=False, cert_present=False)
    assert not any("nginx -t" in c for c in cmds)
