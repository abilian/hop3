# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0


"""
DKIM key generation + DNS records for the direct email backend (ADR 054).

The direct backend delivers to recipients' MX itself, so Hop3 — not a provider —
signs outgoing mail. This module generates the DKIM keypair (via
``opendkim-genkey``), parses the public half into a publishable DNS TXT value,
and assembles the SPF / DKIM / DMARC records the operator must publish for the
sending domain. rootd owns the private key (root-owned, ``0600``).

Deliverability is never faked: these are the records to publish, surfaced so the
operator can act; whether they are live is what the server's DNS pre-flight
checks separately.

``KEY_DIR`` is a module attribute so tests can point it at a tmp dir.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Final

from hop3_rootd.exec import DEFAULT_EXEC, Exec, InvalidBinaryError

# Where the DKIM private keys and opendkim config live (test overrides).
KEY_DIR: Path = Path("/etc/hop3/dkim")
OPENDKIM_CONF: Path = Path("/etc/opendkim.conf")
OPENDKIM_DIR: Path = Path("/etc/opendkim")

_KEY_BITS: Final[str] = "2048"
_GENKEY_TIMEOUT_SECONDS: Final[float] = 30.0
_RELOAD_TIMEOUT_SECONDS: Final[float] = 15.0
_QUOTED: Final[re.Pattern[str]] = re.compile(r'"([^"]*)"')

# opendkim listens here; Postfix's milter connects to the same address. A TCP
# loopback socket avoids the chroot/permission traps of a unix socket.
_MILTER_LISTEN: Final[str] = "inet:8891@localhost"
_MILTER_ADDRESS: Final[str] = "inet:localhost:8891"


class DkimError(Exception):
    """DKIM key generation or opendkim config failed (dispatcher → kernel_error)."""


def milter_address() -> str:
    """The milter socket address Postfix connects to for DKIM signing."""
    return _MILTER_ADDRESS


def _genkey_argv(genkey: str, domain: str, selector: str, keydir: Path) -> list[str]:
    """The ``opendkim-genkey`` argv: a 2048-bit key for ``selector._domainkey``."""
    return [genkey, "-b", _KEY_BITS, "-s", selector, "-d", domain, "-D", str(keydir)]


def _parse_dkim_txt(text: str) -> str:
    """
    Join ``opendkim-genkey``'s multi-line quoted TXT into one record value.

    The ``.txt`` file splits the record across ``"…"`` segments (BIND syntax);
    the publishable value is those segments concatenated, e.g.
    ``v=DKIM1; h=sha256; k=rsa; p=MIGf…``.
    """
    return "".join(_QUOTED.findall(text)).strip()


def ensure_keypair(
    domain: str, selector: str, *, exec: Exec = DEFAULT_EXEC
) -> dict[str, str]:
    """
    Generate the DKIM keypair for ``domain`` if absent; return its DNS record.

    Idempotent: an existing private key is reused (never rotated silently), so
    re-selecting the direct backend keeps the published record valid. Returns
    ``{name, value}`` for the ``<selector>._domainkey.<domain>`` TXT record.
    """
    KEY_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(KEY_DIR, 0o700)
    private = KEY_DIR / f"{selector}.private"
    txt = KEY_DIR / f"{selector}.txt"

    if not private.exists():
        genkey = exec.resolve("opendkim-genkey")
        if genkey is None:
            raise DkimError(
                "opendkim-genkey not available/allow-listed; is opendkim "
                "installed ('hop3-install server --with email')?"
            )
        try:
            result = exec.run(
                _genkey_argv(genkey, domain, selector, KEY_DIR),
                timeout=_GENKEY_TIMEOUT_SECONDS,
            )
        except InvalidBinaryError as e:
            raise DkimError(str(e)) from e
        if not result.success:
            raise DkimError(f"opendkim-genkey failed: {result.stderr.strip()}")
        if not private.exists():
            raise DkimError("opendkim-genkey reported success but wrote no key")
        os.chmod(private, 0o600)

    if not txt.exists():
        raise DkimError(f"DKIM public record {txt} is missing")
    return {
        "name": f"{selector}._domainkey.{domain}",
        "value": _parse_dkim_txt(txt.read_text()),
    }


def _write_conf(path: Path, content: str) -> None:
    """Atomic write of a non-secret config file (0644, tmp→fsync→rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)
    os.chmod(path, 0o644)


def _opendkim_conf(keytable: Path, signingtable: Path, trusted: Path) -> str:
    return (
        "# Managed by Hop3 (ADR 054) — sign outbound mail for the direct backend.\n"
        "Syslog yes\n"
        "UMask 007\n"
        "Mode s\n"  # sign only — a null client verifies no inbound mail
        "Canonicalization relaxed/simple\n"
        "SubDomains no\n"
        f"Socket {_MILTER_LISTEN}\n"
        f"KeyTable file:{keytable}\n"
        f"SigningTable file:{signingtable}\n"
        f"InternalHosts file:{trusted}\n"
    )


def write_opendkim_config(domain: str, selector: str) -> None:
    """
    Write ``opendkim.conf`` + KeyTable/SigningTable/TrustedHosts to sign mail
    from ``domain`` with the generated key. Idempotent (rewrites to state).
    """
    key_path = KEY_DIR / f"{selector}.private"
    keytable = OPENDKIM_DIR / "KeyTable"
    signingtable = OPENDKIM_DIR / "SigningTable"
    trusted = OPENDKIM_DIR / "TrustedHosts"

    label = f"{selector}._domainkey.{domain}"
    _write_conf(keytable, f"{label} {domain}:{selector}:{key_path}\n")
    _write_conf(signingtable, f"*@{domain} {label}\n")
    _write_conf(trusted, "127.0.0.1\n::1\nlocalhost\n")
    _write_conf(OPENDKIM_CONF, _opendkim_conf(keytable, signingtable, trusted))


def reload_opendkim(exec: Exec = DEFAULT_EXEC) -> str:
    """
    Apply the opendkim config (start it if stopped) via systemd.

    Non-systemd hosts (a supervisor-managed container) must have the process
    manager run opendkim — the installer's ``--with email`` wires that — so a
    missing systemd here fails loud rather than leaving mail unsigned.
    """
    systemctl = exec.resolve("systemctl")
    if systemctl is None:
        raise DkimError(
            "opendkim needs a process manager to run — no systemctl here; the "
            "container must start it under supervisor ('--with email')"
        )
    try:
        result = exec.run(
            [systemctl, "reload-or-restart", "opendkim"],
            timeout=_RELOAD_TIMEOUT_SECONDS,
        )
    except InvalidBinaryError as e:
        raise DkimError(str(e)) from e
    if not result.success:
        raise DkimError(f"could not start opendkim: {result.stderr.strip()}")
    return "systemctl"


def publishable_records(
    domain: str, selector: str, dkim_value: str, server_ip: str
) -> dict[str, Any]:
    """
    The SPF / DKIM / DMARC records (and the PTR reminder) to publish.

    SPF authorises the box's own IP with a soft-fail; DMARC starts at ``p=none``
    (monitor) so setup never self-inflicts a delivery break — the operator
    tightens it once confident. PTR is a hosting-provider action, not a record
    we can hand over.
    """
    return {
        "spf": {"name": domain, "type": "TXT", "value": f"v=spf1 ip4:{server_ip} ~all"},
        "dkim": {
            "name": f"{selector}._domainkey.{domain}",
            "type": "TXT",
            "value": dkim_value,
        },
        "dmarc": {
            "name": f"_dmarc.{domain}",
            "type": "TXT",
            "value": f"v=DMARC1; p=none; rua=mailto:postmaster@{domain}",
        },
        "ptr": (
            f"Set reverse DNS (PTR) for {server_ip} to the server's hostname at "
            "your hosting provider — large receivers require it."
        ),
    }
