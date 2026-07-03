# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import datetime
import os
import re
import shlex
import shutil
import subprocess
from contextlib import suppress
from textwrap import dedent
from typing import TYPE_CHECKING, ClassVar, assert_never

from attrs import frozen

from hop3.config import (
    ACME_EMAIL,
    ACME_ENGINE,
    ACME_SERVER,
    ACME_WWW,
    HOP3_ROOT,
    NGINX_ROOT,
)
from hop3.lib import log
from hop3.lib.rootd import LocalRootdClient, RootdOpError, RootdUnavailableError

if TYPE_CHECKING:
    from pathlib import Path

KEY_STORE = HOP3_ROOT / "certificates"
KEY_STORE.mkdir(parents=True, exist_ok=True)

# The ACME HTTP-01 webroot every proxy conf serves (root ${ACME_WWW}). Create it
# so the challenge path exists even before the first issuance — its absence is
# what blocked edrix.eu's certbot run.
ACME_WWW.mkdir(parents=True, exist_ok=True)

# Domain validation for certbot - must be a valid FQDN
# Allows multi-level subdomains like "app.subdomain.example.com"
# Rejects: localhost, .local, .test, IP addresses, wildcards
RE_DOMAIN_VALIDATOR = re.compile(
    r"^(?!.*\.\.)(?!-)"  # No consecutive dots, no leading hyphen
    r"[a-z0-9]"  # Must start with alphanumeric
    r"(?:[a-z0-9-]*[a-z0-9])?"  # Middle chars (optional, ends alphanumeric)
    r"(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*"  # Additional labels
    r"\.[a-z]{2,}$"  # TLD (at least 2 chars)
)

# TLDs no public CA (Let's Encrypt included) can issue certificates for.
RESERVED_TLDS = (".local", ".test", ".localhost", ".invalid", ".example")


class CertificateError(RuntimeError):
    """A certificate could not be issued. Raised loudly — never swallowed."""


def is_public_fqdn(domain_name: str) -> bool:
    """True if ``domain_name`` is a real, public FQDN a CA could issue for.

    False for the catch-all name ("_"), bare hostnames / app names with no dot,
    IP addresses, wildcards, and reserved TLDs (.local/.test/...). Such names can
    only ever get a self-signed cert, so they must never be sent to certbot —
    this is also what keeps tests off certbot (their domains aren't public).
    """
    domain_lower = domain_name.lower()
    if not RE_DOMAIN_VALIDATOR.fullmatch(domain_lower):
        return False
    return not domain_lower.endswith(RESERVED_TLDS)


def write_private_key(path: Path, content: str) -> None:
    """Atomically write a TLS private key with owner-only (0600) permissions.

    Centralized so no call site ships a world-readable key, and atomic (write a
    sibling temp file, chmod, then rename) so a concurrent reader -- an nginx
    reload, or the renewal thread racing a deploy -- never sees a half-written
    key.
    """
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(content)
    tmp.chmod(0o600)
    tmp.replace(path)


class CertificatesManager:
    """Stateless service class for managing SSL certificates.

    This service is now managed by Dishka dependency injection framework.
    It is registered in APP scope, meaning a single instance is created
    and reused throughout the application lifetime.
    """

    def get_certificate(self, domain_name: str) -> Certificate:
        # if not RE_DOMAIN_VALIDATOR.match(domain_name):
        #     msg = f"Invalid domain name: {domain_name}"
        #     raise ValueError(msg)

        certificate = Certificate(domain_name=domain_name)
        if not certificate.crt_file.exists():
            certificate.generate()
        return certificate

    def renew(
        self, domain_name: str, *, threshold_days: int = 30, force: bool = False
    ) -> bool:
        """Re-issue the cert for ``domain_name`` if it is due (or ``force``).

        Returns True if the cert was re-issued, False if it was still valid and
        left untouched. Reinstalling the renewed cert into the proxy and
        reloading it is the caller's job (it knows the app -> proxy mapping).
        """
        certificate = Certificate(domain_name=domain_name)
        if not force and not certificate.needs_renewal(threshold_days=threshold_days):
            return False
        certificate.generate(force=True)
        return True


@frozen
class Certificate:
    domain_name: str

    @property
    def key_file(self) -> Path:
        return KEY_STORE / f"{self.domain_name}.key"

    @property
    def crt_file(self) -> Path:
        return KEY_STORE / f"{self.domain_name}.crt"

    def get_key(self):
        return self.key_file.read_text()

    def get_crt(self):
        return self.crt_file.read_text()

    def not_after(self) -> datetime.datetime | None:
        """Expiry instant (UTC) of the stored cert, or None if absent/unreadable."""
        if not self.crt_file.exists():
            return None
        try:
            result = subprocess.run(
                ["openssl", "x509", "-enddate", "-noout", "-in", str(self.crt_file)],
                capture_output=True,
                text=True,
                check=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None
        # e.g. "notAfter=Jun 11 13:19:10 2027 GMT"
        _, _, value = result.stdout.strip().partition("=")
        value = value.strip()
        for fmt in ("%b %d %H:%M:%S %Y %Z", "%b %d %H:%M:%S %Y"):
            try:
                parsed = datetime.datetime.strptime(value, fmt)  # noqa: DTZ007
            except ValueError:
                continue
            return parsed.replace(tzinfo=datetime.timezone.utc)
        return None

    def days_until_expiry(self, *, now: datetime.datetime | None = None) -> int | None:
        """Whole days until the stored cert expires (negative if already expired)."""
        expiry = self.not_after()
        if expiry is None:
            return None
        now = now or datetime.datetime.now(datetime.timezone.utc)
        return (expiry - now).days

    def is_self_signed(self) -> bool:
        """True if the stored cert is self-signed (issuer == subject)."""
        if not self.crt_file.exists():
            return False
        try:
            result = subprocess.run(
                [
                    "openssl",
                    "x509",
                    "-noout",
                    "-subject",
                    "-issuer",
                    "-in",
                    str(self.crt_file),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
        subject = issuer = None
        for line in result.stdout.splitlines():
            if line.startswith("subject="):
                subject = line.partition("=")[2].strip()
            elif line.startswith("issuer="):
                issuer = line.partition("=")[2].strip()
        return subject is not None and subject == issuer

    def covers_domain(self, domain_name: str) -> bool:
        """True if the cert's CN or a SAN DNS entry covers ``domain_name``.

        Handles a single leftmost-label wildcard (``*.example.com`` matches
        ``a.example.com`` but not ``a.b.example.com`` or the bare apex).
        """
        if not self.crt_file.exists():
            return False
        try:
            result = subprocess.run(
                [
                    "openssl",
                    "x509",
                    "-noout",
                    "-subject",
                    "-ext",
                    "subjectAltName",
                    "-in",
                    str(self.crt_file),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
        target = domain_name.lower()
        return any(_dns_name_matches(n, target) for n in _cert_dns_names(result.stdout))

    def needs_renewal(self, *, threshold_days: int = 30) -> bool:
        """Whether this cert should be re-issued.

        True when there is no cert yet; it expires within ``threshold_days`` (or
        is already expired); or it is a self-signed cert while the engine is
        certbot (a prior fallback that should be replaced by a real Let's Encrypt
        cert).
        """
        if not self.crt_file.exists():
            return True
        days = self.days_until_expiry()
        if days is None or days < threshold_days:
            return True
        # A self-signed cert left over from a fallback should be upgraded to a
        # real one — but only if the domain could actually get one.
        return (
            ACME_ENGINE == "certbot"
            and is_public_fqdn(self.domain_name)
            and self.is_self_signed()
        )

    def generate(self, *, force: bool = False) -> None:
        """Issue (or re-issue) this cert via the engine selected for its domain.

        Engine choice (self-signed vs certbot vs ...) and the public-FQDN gate
        live in ``select_engine``, which fails LOUDLY rather than silently
        self-signing a public domain when the chosen engine cannot issue.
        """
        select_engine(self.domain_name).issue(self, force=force)

    def generate_self_signed(self) -> None:
        """Generate a self-signed SSL certificate for the specified domain.

        Uses the OpenSSL command-line tool to generate a self-signed
        certificate with a 4096-bit RSA key, valid for 365 days. A
        subjectAltName is REQUIRED: modern TLS clients ignore the CN entirely,
        and verify_cert/covers_domain rely on the SAN's stable ``DNS:`` line
        (the ``subject=`` line's format varies across OpenSSL versions).
        """
        log("Generating self-signed certificate", level=2)
        cmd = (
            "openssl req -new -newkey rsa:4096 -days 365 -nodes -x509 -subj"
            f' "/C=FR/ST=NA/L=Paris/O=Hop3/OU=Self-Signed/CN={self.domain_name}"'
            f' -addext "subjectAltName=DNS:{self.domain_name}"'
            f" -keyout {self.key_file} -out {self.crt_file}"
        )
        shell(cmd)
        self.key_file.chmod(0o600)  # openssl's default umask can leave it readable

    def generate_with_certbot(self, *, force: bool = False) -> None:
        """Obtain a Let's Encrypt cert via certbot's webroot challenge.

        Preconditions — the engine is available (certbot present, ACME_EMAIL set)
        and the domain is a public FQDN — are enforced by ``select_engine`` before
        we get here. The challenge is served from ``ACME_WWW``, the SAME webroot
        every app's nginx conf already serves (``root ${ACME_WWW}``), which we
        create here so issuance and serving never disagree. A temporary :80 vhost
        covers the first deploy, when the app's own conf isn't written yet
        (setup_certificates runs before generate_config).
        """
        certbot_root = HOP3_ROOT / "certbot"
        live_cert_file = certbot_root / f"config/live/{self.domain_name}/fullchain.pem"
        live_key_file = certbot_root / f"config/live/{self.domain_name}/privkey.pem"

        if force or not live_cert_file.exists() or not live_key_file.exists():
            ACME_WWW.mkdir(parents=True, exist_ok=True)

            nginx_webroot_conf = dedent(
                f"""
                server {{
                  listen      [::]:80;
                  listen      0.0.0.0:80;
                  server_name {self.domain_name};

                  location ^~ /.well-known/acme-challenge {{
                    allow all;
                    root {ACME_WWW};
                  }}
                }}
                """
            )
            (NGINX_ROOT / "__certbot_webroot.conf").write_text(nginx_webroot_conf)
            reload_nginx()

            cmd = (
                f"certbot certonly --webroot -w {ACME_WWW} -d {self.domain_name} -n "
                f"--config-dir {certbot_root}/config "
                f"--work-dir {certbot_root}/work "
                f"--logs-dir {certbot_root}/logs "
                f"--agree-tos --email {ACME_EMAIL}"
                + (f" --server {ACME_SERVER}" if ACME_SERVER else "")
                + (" --force-renewal" if force else "")
            )
            try:
                shell(cmd)
            except subprocess.CalledProcessError as e:
                raise CertificateError(self._certbot_error(e, certbot_root)) from e
            finally:
                (NGINX_ROOT / "__certbot_webroot.conf").unlink(missing_ok=True)

        self.crt_file.write_text(live_cert_file.read_text())
        write_private_key(self.key_file, live_key_file.read_text())

    def _certbot_error(
        self, e: subprocess.CalledProcessError, certbot_root: Path
    ) -> str:
        details = [
            f"certbot failed for domain '{self.domain_name}' (exit code {e.returncode})"
        ]
        if e.stderr:
            details.append(f"stderr: {e.stderr}")
        if e.stdout:
            details.append(f"stdout: {e.stdout}")
        certbot_log = certbot_root / "logs" / "letsencrypt.log"
        log_text = ""
        if certbot_log.exists():
            with suppress(Exception):
                log_text = certbot_log.read_text()
                tail = log_text.strip().split("\n")[-20:]
                details.append(f"certbot log ({certbot_log}):\n" + "\n".join(tail))
        haystack = f"{e.stderr or ''}\n{e.stdout or ''}\n{log_text}"
        return (
            "Certificate generation failed:\n"
            + "\n".join(details)
            + "\n\n"
            + _certbot_failure_hint(haystack)
            + "\n\nTo use a self-signed cert instead, set ACME_ENGINE=self-signed"
        )


# certbot fails at two layers whose fixes are opposite. Reaching Let's Encrypt's
# API is an OUTBOUND TLS/egress problem on THIS server (the request fails before
# any challenge). The challenge failing is INBOUND — Let's Encrypt can't reach
# your domain (DNS / port 80). These markers, from certbot's own output, mean the
# former: the client couldn't even talk to the ACME server. They are kept specific
# (not bare "connection refused", which also appears in an inbound challenge
# failure against your server) so we don't misclassify the two.
_ACME_UNREACHABLE_MARKERS = (
    "max retries exceeded",
    "acme-v02.api.letsencrypt.org",
    "acme-staging-v02.api.letsencrypt.org",
    "unexpected_eof",
    "ssleoferror",
    "sslerror",
    "failed to establish a new connection",
    "newconnectionerror",
    "get_directory",
    "temporary failure in name resolution",
)
_ACME_RATE_LIMIT_MARKERS = (
    "rate limit",
    "too many certificates",
    "too many failed authorizations",
)


def _certbot_failure_hint(output: str) -> str:
    """Cause-specific certbot guidance keyed off certbot's own output.

    A single generic cause list ("check your DNS / port 80") sent operators to
    debug their (correct) domain when the real failure was the server's OUTBOUND
    path to Let's Encrypt — the call died before any ACME challenge, so DNS and
    inbound :80 were irrelevant. Name the layer that actually failed so the
    operator debugs the right side of the connection.
    """
    text = output.lower()
    if any(m in text for m in _ACME_UNREACHABLE_MARKERS):
        return (
            "Cause: this server could not reach Let's Encrypt's API "
            "(acme-v02.api.letsencrypt.org:443). The call failed BEFORE any ACME "
            "challenge, so your domain's DNS and inbound port 80 are NOT the "
            "problem — debug the server's OUTBOUND path to Let's Encrypt:\n"
            "  - Egress firewall / security group blocking outbound 443 to Let's Encrypt\n"
            "  - Broken IPv6 route (certbot may try LE over IPv6 and get an EOF) — "
            "fix or disable IPv6 egress, then retry\n"
            "  - MTU/PMTU blackhole dropping the TLS handshake (tunnels/VPNs)\n"
            "  - An intercepting proxy/DPI resetting the handshake\n"
            "  - A transient Let's Encrypt or network blip — retry"
        )
    if any(m in text for m in _ACME_RATE_LIMIT_MARKERS):
        return (
            "Cause: Let's Encrypt rate limit for this domain. Wait out the window, "
            "or point ACME_SERVER at the staging environment while iterating. "
            "See https://letsencrypt.org/docs/rate-limits/"
        )
    return (
        "Common causes (Let's Encrypt could not reach your domain to validate the "
        "challenge):\n"
        "  - Domain DNS not pointing to this server\n"
        "  - Port 80 not accessible from the internet\n"
        "  - Rate limit exceeded (https://letsencrypt.org/docs/rate-limits/)"
    )


class CertEngine:
    """A certificate-issuance backend.

    Two engines exist today (``self-signed`` and ``certbot``). Adding more —
    a paid CA, wildcard/DNS-01, ... — is a matter of subclassing and registering
    in ``CERT_ENGINES``; eventually this becomes a plugin hook.
    """

    name: ClassVar[str] = ""

    def is_available(self) -> tuple[bool, str]:
        """Return ``(ok, reason)`` — whether this engine can issue right now."""
        return (True, "")

    def issue(self, cert: Certificate, *, force: bool = False) -> None:
        raise NotImplementedError


class SelfSignedEngine(CertEngine):
    name = "self-signed"

    def issue(self, cert: Certificate, *, force: bool = False) -> None:
        cert.generate_self_signed()


class CertbotEngine(CertEngine):
    name = "certbot"

    def is_available(self) -> tuple[bool, str]:
        if not shutil.which("certbot"):
            return (False, "certbot is not installed")
        if not ACME_EMAIL:
            return (False, "ACME_EMAIL is not set")
        return (True, "")

    def issue(self, cert: Certificate, *, force: bool = False) -> None:
        cert.generate_with_certbot(force=force)


CERT_ENGINES: dict[str, CertEngine] = {
    SelfSignedEngine.name: SelfSignedEngine(),
    CertbotEngine.name: CertbotEngine(),
}


def select_engine(domain_name: str) -> CertEngine:
    """Pick the issuance engine for ``domain_name`` — loud on misconfiguration.

    A name that isn't a real public FQDN can only ever be self-signed, so it uses
    the self-signed engine regardless of ``ACME_ENGINE`` (this keeps tests and
    internal/catch-all hosts off certbot). A public FQDN uses the configured
    engine — but if that engine can't issue (certbot missing, no ACME_EMAIL, ...)
    we RAISE rather than silently shipping an untrusted self-signed cert for a
    public domain.
    """
    if not is_public_fqdn(domain_name):
        return CERT_ENGINES["self-signed"]

    engine = CERT_ENGINES.get(ACME_ENGINE)
    if engine is None:
        msg = (
            f"Unknown ACME_ENGINE {ACME_ENGINE!r} "
            f"(known engines: {', '.join(sorted(CERT_ENGINES))})"
        )
        raise CertificateError(msg)

    ok, reason = engine.is_available()
    if not ok:
        msg = (
            f"ACME_ENGINE={engine.name!r} cannot issue a certificate for the "
            f"public domain {domain_name!r}: {reason}. Refusing to fall back to an "
            f"untrusted self-signed certificate. Fix the engine, or set "
            f"ACME_ENGINE=self-signed explicitly if a self-signed cert is "
            f"acceptable for this host."
        )
        raise CertificateError(msg)

    return engine


def verify_cert(domain_name: str) -> None:
    """Assert the stored cert for ``domain_name`` is fit to serve, else raise.

    A deploy/renewal post-condition: checks the cert exists, is not already
    expired, covers the domain, and — for a public FQDN under certbot — is a real
    CA cert rather than a silently self-signed one. Raising here turns a bad cert
    into a loud failure instead of quietly serving an untrusted/expired cert (the
    edrix.eu failure mode).
    """
    cert = Certificate(domain_name=domain_name)
    if not cert.crt_file.exists():
        msg = f"No certificate was produced for {domain_name!r}."
        raise CertificateError(msg)

    problems: list[str] = []
    days = cert.days_until_expiry()
    if days is None:
        problems.append("its expiry could not be read")
    elif days < 0:
        problems.append(f"it expired {-days} day(s) ago")
    if not cert.covers_domain(domain_name):
        problems.append(f"it does not cover {domain_name!r}")
    if (
        is_public_fqdn(domain_name)
        and ACME_ENGINE == "certbot"
        and cert.is_self_signed()
    ):
        problems.append(
            "it is self-signed (untrusted), but a public domain under "
            "ACME_ENGINE=certbot must have a CA-issued certificate"
        )

    if problems:
        msg = (
            f"Certificate for {domain_name!r} is not fit to serve: "
            + "; ".join(problems)
            + "."
        )
        raise CertificateError(msg)


def _cert_dns_names(openssl_text: str) -> set[str]:
    """Extract CN + SAN DNS names from `openssl x509 -subject -ext ...` output.

    Tolerates the several subject formats OpenSSL emits across versions:
    slash-separated (``/.../CN=x``) and comma-separated, with or without spaces
    around ``=`` (``CN=x`` or ``CN = x``). Getting this wrong made covers_domain
    reject self-signed certs on the target's OpenSSL and failed every deploy.
    """
    names: set[str] = set()
    for raw in openssl_text.splitlines():
        line = raw.strip()
        if line.startswith("subject="):
            for part in re.split(r"[,/]", line[len("subject=") :]):
                key, sep, value = part.partition("=")
                if sep and key.strip().upper() == "CN":
                    names.add(value.strip().lower())
        elif line.startswith("DNS:"):
            for entry in line.split(","):
                entry = entry.strip()
                if entry.startswith("DNS:"):
                    names.add(entry[len("DNS:") :].strip().lower())
    return names


def _dns_name_matches(cert_name: str, domain: str) -> bool:
    """Exact match, or a single leftmost-label wildcard match."""
    if cert_name == domain:
        return True
    if cert_name.startswith("*."):
        suffix = cert_name[1:]  # ".example.com"
        return domain.endswith(suffix) and "." not in domain[: -len(suffix)]
    return False


def reload_nginx() -> None:
    """Reload nginx via hop3-rootd to apply configuration changes.

    Reloads through the SAME privileged path as a normal deploy — hop3-rootd's
    ``nginx.reload`` op (which runs ``systemctl reload nginx`` / ``nginx -s
    reload``, both validating the config first). The platform grants privilege
    through hop3-rootd, NOT passwordless sudo, so the old sudo path failed on real
    servers. Used to publish the temporary ACME-challenge vhost during certbot
    issuance and to apply renewed certs; raises loudly if nginx cannot be
    reloaded (a deploy/renewal blocker, never swallowed).
    """
    # Skip reload in test environments.
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    try:
        with LocalRootdClient() as client:
            client.call("nginx.reload", {})
    except (RootdUnavailableError, RootdOpError) as e:
        msg = f"Cannot reload nginx (via hop3-rootd): {e}"
        raise CertificateError(msg) from e
    log("nginx reloaded (hop3-rootd)", level=2)


def shell(cmd: str | list[str]) -> None:
    """Execute a command safely without shell=True.

    Args:
        cmd: Command to execute (string or list).
             Strings are parsed with shlex.split().

    Raises:
        subprocess.CalledProcessError: If command fails.
    """
    # Parse string commands safely
    match cmd:
        case str():
            cmd_list = shlex.split(cmd)
            cmd_display = cmd
        case list():
            cmd_list = cmd
            cmd_display = shlex.join(cmd)
        case _ as unreachable:
            assert_never(unreachable)

    log(f"Running command: {cmd_display}", level=2)
    result = subprocess.run(
        cmd_list,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Re-raise with captured output available
        error = subprocess.CalledProcessError(result.returncode, cmd_display)
        error.stdout = result.stdout
        error.stderr = result.stderr
        raise error
