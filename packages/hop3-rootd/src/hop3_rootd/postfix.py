# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0


"""Loopback SMTP relay for the email backend (ADR 054).

hop3-server's email addon injects ``SMTP_HOST=127.0.0.1`` into apps that
declare an email addon; this module renders the Postfix config that makes
``127.0.0.1:25`` a *queuing* relay to the active email backend. Postfix binds
loopback only and relays for no one but local processes — never an
internet-facing MTA, never an open relay, never a ``sendmail`` side-channel.

rootd owns ``/etc/postfix``: it writes ``main.cf`` and the SASL password map
(atomic write→fsync→rename, like ``state.save``), runs ``postmap``, and reloads
Postfix through the allow-listed ``systemctl`` / ``postfix`` binaries. The
provider password lives only in the ``0600`` ``sasl_passwd`` map — never in an
app's environment, never in a result dict, never logged.

Stateless: the config lives on disk in ``/etc/postfix`` and survives a rootd
restart, so there is no state row to reconcile. ``POSTFIX_DIR`` is a module
attribute so tests can point it at a tmp dir.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Final

from hop3_rootd.exec import DEFAULT_EXEC, CommandResult, Exec, InvalidBinaryError

# Postfix config directory (test override via this attribute).
POSTFIX_DIR: Path = Path("/etc/postfix")

_MAIN_CF: Final[str] = "main.cf"
_SASL_PASSWD: Final[str] = "sasl_passwd"
_WRAPPER_TLS_PORT: Final[int] = 465  # implicit TLS; 587 uses STARTTLS
_RELOAD_TIMEOUT_SECONDS: Final[float] = 15.0
_POSTMAP_TIMEOUT_SECONDS: Final[float] = 15.0

# Per-app sender maps (ADR 054): logical name → (filename, mode). The op accepts
# only these logical names and composes the path here — a raw path is never
# taken off the wire. ``sasl_passwd`` (0600) is the shared credential map; the
# others carry per-app, sender-keyed lines.
_MAP_FILES: Final[dict[str, tuple[str, int]]] = {
    "sender_relayhost": ("hop3_sender_relayhost", 0o644),
    "sender_transport": ("hop3_sender_transport", 0o644),
    "sender_canonical": ("hop3_sender_canonical", 0o644),
    "sasl_passwd": (_SASL_PASSWD, 0o600),
}
MAP_NAMES: Final[frozenset[str]] = frozenset(_MAP_FILES)


class PostfixError(Exception):
    """A Postfix configuration operation failed (dispatcher → kernel_error)."""


class PostfixUnavailableError(PostfixError):
    """postmap / a reload method isn't available or allow-listed here."""


# --- config rendering -----------------------------------------------------


def _sasl_block(*, use_sasl: bool) -> str:
    if not use_sasl:
        return "smtp_sasl_auth_enable = no\n"
    return (
        "smtp_sasl_auth_enable = yes\n"
        f"smtp_sasl_password_maps = hash:{POSTFIX_DIR / _SASL_PASSWD}\n"
        "smtp_sasl_security_options = noanonymous\n"
    )


def _tls_block(*, use_tls: bool, wrapper_tls: bool) -> str:
    if not use_tls:
        # A dev sink (catch backend) speaks plaintext on loopback — no TLS.
        return "smtp_tls_security_level = none\n"
    wrapper = "smtp_tls_wrappermode = yes\n" if wrapper_tls else ""
    return (
        "smtp_tls_security_level = encrypt\n"
        "smtp_tls_mandatory_protocols = >=TLSv1.2\n"
        "smtp_tls_CAfile = /etc/ssl/certs/ca-certificates.crt\n"
        f"{wrapper}"
    )


def _main_cf(nexthop: str, *, use_sasl: bool, use_tls: bool, wrapper_tls: bool) -> str:
    """Render a null-client ``main.cf`` relaying to ``nexthop`` (``[host]:port``).

    Loopback-only, submission-only, we are nobody's MX and deliver locally for
    no domain. A transient upstream failure defers and retries (the queue is
    the whole point — fail-loud, never a silent drop). ``use_sasl``/``use_tls``
    are off for a dev-sink (catch) backend, which relays plaintext to a local
    Mailpit with no auth.
    """
    return (
        "# Managed by Hop3 (ADR 054) — loopback null-client relay. Do not edit.\n"
        "inet_interfaces = loopback-only\n"
        "inet_protocols = all\n"
        "mynetworks = 127.0.0.0/8, [::1]/128\n"
        "smtpd_relay_restrictions = permit_mynetworks, reject\n"
        "mydestination =\n"
        "relay_domains =\n"
        "local_transport = error:5.1.1 local delivery disabled on this null client\n"
        f"relayhost = {nexthop}\n"
        + _sasl_block(use_sasl=use_sasl)
        + _tls_block(use_tls=use_tls, wrapper_tls=wrapper_tls)
        + "soft_bounce = no\n"
        "maximal_queue_lifetime = 5d\n"
        "bounce_queue_lifetime = 5d\n"
        "notify_classes = resource, software\n"
    )


def _write_file(path: Path, content: str, *, mode: int) -> None:
    """Atomic write (tmp→fsync→rename), created at ``mode`` from the start.

    The tmp file is opened with ``mode`` so a secret (``sasl_passwd``, 0600) is
    never briefly world-readable between create and chmod.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)
    os.chmod(path, mode)


# --- external tools -------------------------------------------------------


def _postmap(postmap: str, path: Path, *, exec: Exec) -> None:
    """Rebuild the indexed ``.db`` Postfix reads. A bad map aborts loud."""
    try:
        result = exec.run([postmap, str(path)], timeout=_POSTMAP_TIMEOUT_SECONDS)
    except InvalidBinaryError as e:
        raise PostfixUnavailableError(str(e)) from e
    if not result.success:
        raise PostfixError(f"postmap {path} failed: {result.stderr.strip()}")


def _run(exec: Exec, argv: list[str]) -> CommandResult | None:
    """Run ``argv``; return the result, or None if the binary isn't allow-listed."""
    try:
        return exec.run(argv, timeout=_RELOAD_TIMEOUT_SECONDS)
    except InvalidBinaryError:
        return None


def _reload(exec: Exec) -> str:
    """Apply the new config, starting Postfix if it is not already running.

    Prefers systemd (``reload-or-restart`` starts a stopped unit); on a host
    without a working systemd — a supervisor-managed container, where
    ``systemctl`` is absent or a no-op — falls back to the ``postfix`` binary:
    ``postfix start`` when ``postfix status`` reports it stopped, ``postfix
    reload`` otherwise. This is the pm-aware handling the ``--docker`` target
    needs (a plain ``systemctl reload`` there is a silent no-op / failure).
    Raises if nothing works.
    """
    systemctl = exec.resolve("systemctl")
    postfix = exec.resolve("postfix")
    if systemctl is None and postfix is None:
        raise PostfixUnavailableError(
            "no Postfix reload method available (neither systemctl nor postfix "
            "on the allow-list); is Postfix installed?"
        )

    last_error: str | None = None
    if systemctl is not None:
        result = _run(exec, [systemctl, "reload-or-restart", "postfix"])
        if result is not None and result.success:
            return "systemctl"
        last_error = _format_error("systemctl reload-or-restart", result)

    if postfix is not None:
        method = _postfix_start_or_reload(exec, postfix)
        if method is not None:
            return method
        last_error = "postfix start/reload failed"

    raise PostfixError(f"all Postfix reload methods failed; last: {last_error}")


def _postfix_start_or_reload(exec: Exec, postfix: str) -> str | None:
    """Start Postfix if ``postfix status`` shows it stopped, else reload it."""
    status = _run(exec, [postfix, "status"])
    verb = "reload" if (status is not None and status.success) else "start"
    result = _run(exec, [postfix, verb])
    return f"postfix {verb}" if (result is not None and result.success) else None


def _format_error(label: str, result: CommandResult | None) -> str:
    if result is None:
        return f"{label} not runnable"
    return f"{label} rc={result.returncode}: {result.stderr.strip()}"


# --- public operation (called by ops/postfix.py) --------------------------


def configure(
    relay_host: str,
    relay_port: int,
    *,
    sasl_user: str = "",
    sasl_password: str = "",
    use_tls: bool = True,
    exec: Exec = DEFAULT_EXEC,
) -> dict[str, Any]:
    """Write the null-client ``main.cf`` (+ SASL map when authenticated), reload.

    Idempotent: overwrites the Hop3-managed ``main.cf`` and ``sasl_passwd`` each
    call, writing exactly what it is given (no credential rotation of its own),
    so selecting a backend is re-pointable. With no ``sasl_user`` (a dev-sink /
    catch backend) it writes no SASL map and relays plaintext. Returns
    ``{relayhost, reloaded}`` — never the password.
    """
    use_sasl = bool(sasl_user)
    nexthop = f"[{relay_host}]:{relay_port}"
    main_path = POSTFIX_DIR / _MAIN_CF
    sasl_path = POSTFIX_DIR / _SASL_PASSWD

    # Resolve postmap up front so an authenticated backend fails loud before
    # writing anything (a catch backend needs no map, so it needs no postmap).
    postmap = exec.resolve("postmap") if use_sasl else None
    if use_sasl and postmap is None:
        raise PostfixUnavailableError(
            "postmap not available/allow-listed; is Postfix installed "
            "('hop3-install server --with email')?"
        )

    _write_file(
        main_path,
        _main_cf(
            nexthop,
            use_sasl=use_sasl,
            use_tls=use_tls,
            wrapper_tls=relay_port == _WRAPPER_TLS_PORT,
        ),
        mode=0o644,
    )
    if use_sasl:
        assert postmap is not None
        _write_file(sasl_path, f"{nexthop} {sasl_user}:{sasl_password}\n", mode=0o600)
        _postmap(postmap, sasl_path, exec=exec)

    method = _reload(exec)
    return {"relayhost": nexthop, "reloaded": method}


def _direct_main_cf(milter: str) -> str:
    """Render a ``main.cf`` that delivers to recipients' MX itself (no relayhost),
    signing outbound mail through the opendkim ``milter``."""
    return (
        "# Managed by Hop3 (ADR 054) — direct MTA: deliver to MX, DKIM-signed.\n"
        "inet_interfaces = loopback-only\n"
        "inet_protocols = all\n"
        "mynetworks = 127.0.0.0/8, [::1]/128\n"
        "smtpd_relay_restrictions = permit_mynetworks, reject\n"
        "mydestination =\n"
        "relay_domains =\n"
        "local_transport = error:5.1.1 local delivery disabled on this null client\n"
        "relayhost =\n"  # empty: deliver to the recipient's MX
        "smtp_tls_security_level = may\n"  # opportunistic TLS to recipient MX
        f"smtp_milters = {milter}\n"
        f"non_smtpd_milters = {milter}\n"
        "milter_default_action = accept\n"
        "milter_protocol = 6\n"
        "soft_bounce = no\n"
        "maximal_queue_lifetime = 5d\n"
        "bounce_queue_lifetime = 5d\n"
        "notify_classes = resource, software\n"
    )


def _read_map_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [ln for ln in path.read_text().splitlines() if ln.strip()]


def _map_key(line: str) -> str:
    return line.split(maxsplit=1)[0] if line.split() else ""


def _postmap_and_reload(path: Path, *, exec: Exec) -> str:
    postmap = exec.resolve("postmap")
    if postmap is None:
        raise PostfixUnavailableError(
            "postmap not available/allow-listed; is Postfix installed?"
        )
    _postmap(postmap, path, exec=exec)
    return _reload(exec)


def map_add(
    logical: str, key: str, value: str, *, exec: Exec = DEFAULT_EXEC
) -> dict[str, Any]:
    """Set the ``key`` line in a per-app map (replace-or-add), postmap, reload.

    Rewrites the whole file from the desired lines (never a blind append), so a
    re-run is idempotent. Returns ``{map, key, reloaded}``.
    """
    filename, mode = _MAP_FILES[logical]
    path = POSTFIX_DIR / filename
    lines = [ln for ln in _read_map_lines(path) if _map_key(ln) != key]
    lines.append(f"{key} {value}")
    _write_file(path, "\n".join(lines) + "\n", mode=mode)
    return {
        "map": logical,
        "key": key,
        "reloaded": _postmap_and_reload(path, exec=exec),
    }


def map_remove(logical: str, key: str, *, exec: Exec = DEFAULT_EXEC) -> dict[str, Any]:
    """Remove the ``key`` line from a per-app map, postmap, reload. Idempotent —
    removing an absent key reports ``removed=False`` and touches nothing else."""
    filename, mode = _MAP_FILES[logical]
    path = POSTFIX_DIR / filename
    lines = _read_map_lines(path)
    kept = [ln for ln in lines if _map_key(ln) != key]
    if len(kept) == len(lines) and path.exists():
        return {"map": logical, "key": key, "removed": False, "reloaded": "none"}
    _write_file(path, ("\n".join(kept) + "\n") if kept else "", mode=mode)
    return {
        "map": logical,
        "key": key,
        "removed": True,
        "reloaded": _postmap_and_reload(path, exec=exec),
    }


def configure_direct(*, milter: str, exec: Exec = DEFAULT_EXEC) -> dict[str, Any]:
    """Write the direct-delivery ``main.cf`` (deliver to MX + DKIM milter), reload.

    No relayhost and no upstream SASL — Postfix is the MTA. Returns
    ``{relayhost, reloaded}`` (``relayhost`` empty for direct).
    """
    _write_file(POSTFIX_DIR / _MAIN_CF, _direct_main_cf(milter), mode=0o644)
    method = _reload(exec)
    return {"relayhost": "", "reloaded": method}
