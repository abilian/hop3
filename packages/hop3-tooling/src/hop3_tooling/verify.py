# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""Login-aware, functional verification of catalog apps' admin bootstrap.

For each app this asserts, through its real auth surface (API / basic-auth /
login form) — not a bare 200 (see the `test-validation-must-be-functional`
lesson):

  1. the app's former default credential NO LONGER authenticates;
  2. the Hop3-generated admin credential (from `hop3 app credentials`) DOES;
  3. open registration / anonymous access is closed where the app had a land-grab.

The login probes need each app at its PUBLIC url — the one `hop3 catalog install`
assigns. The dev box serves self-signed certs, so pass ``insecure=True`` there.
"""

from __future__ import annotations

import re
import shlex
import subprocess
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import TYPE_CHECKING

import httpx

from .credentials import Credential, read_generated_credential

if TYPE_CHECKING:
    from collections.abc import Callable

DEFAULT_HOST = "hop3-dev.abilian.com"

# Mutable run config (set once per run; attribute mutation avoids a `global`).
CFG = SimpleNamespace(verify_tls=True)


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #


def _client() -> httpx.Client:
    return httpx.Client(timeout=20.0, verify=CFG.verify_tls, follow_redirects=False)


def _hidden_input(html: str, name: str) -> str | None:
    """Extract a hidden form input value (CSRF token) by name."""
    m = re.search(
        rf'<input[^>]*name=["\']{re.escape(name)}["\'][^>]*value=["\']([^"\']*)["\']',
        html,
    ) or re.search(
        rf'<input[^>]*value=["\']([^"\']*)["\'][^>]*name=["\']{re.escape(name)}["\']',
        html,
    )
    return m.group(1) if m else None


# --------------------------------------------------------------------------- #
# Per-app auth probes: return True iff (login_id, password) is ACCEPTED.
# --------------------------------------------------------------------------- #


def probe_miniflux(base, cred, login_id, password) -> bool:
    r = httpx.get(
        f"{base}/v1/me", auth=(login_id, password), timeout=20, verify=CFG.verify_tls
    )
    return r.status_code == 200 and '"username"' in r.text


def probe_nextcloud(base, cred, login_id, password) -> bool:
    r = httpx.get(
        f"{base}/ocs/v1.php/cloud/user?format=json",
        auth=(login_id, password),
        headers={"OCS-APIRequest": "true"},
        timeout=20,
        verify=CFG.verify_tls,
    )
    # OCS wraps status: 100 = ok. 997 = unauthenticated.
    return r.status_code == 200 and '"id"' in r.text and ">997<" not in r.text


def probe_keycloak(base, cred, login_id, password) -> bool:
    r = httpx.post(
        f"{base}/realms/master/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": login_id,
            "password": password,
        },
        timeout=20,
        verify=CFG.verify_tls,
    )
    return r.status_code == 200 and "access_token" in r.text


def probe_kanboard(base, cred, login_id, password) -> bool:
    r = httpx.post(
        f"{base}/jsonrpc.php",
        auth=(login_id, password),
        json={"jsonrpc": "2.0", "method": "getMe", "id": 1},
        timeout=20,
        verify=CFG.verify_tls,
    )
    return r.status_code == 200 and '"result"' in r.text and '"id"' in r.text


def probe_gitea(base, cred, login_id, password) -> bool:
    r = httpx.get(
        f"{base}/api/v1/user",
        auth=(login_id, password),
        timeout=20,
        verify=CFG.verify_tls,
    )
    return r.status_code == 200 and '"login"' in r.text


def probe_mattermost(base, cred, login_id, password) -> bool:
    r = httpx.post(
        f"{base}/api/v4/users/login",
        json={"login_id": login_id, "password": password},
        timeout=20,
        verify=CFG.verify_tls,
    )
    return r.status_code == 200 and "Token" in r.headers


def probe_radicale(base, cred, login_id, password) -> bool:
    r = httpx.request(
        "PROPFIND",
        f"{base}/{login_id}/",
        auth=(login_id, password),
        headers={"Depth": "0"},
        timeout=20,
        verify=CFG.verify_tls,
    )
    return r.status_code in {200, 207}


def probe_radicale_anonymous(base, cred, login_id, password) -> bool:
    """No-auth PROPFIND. True = anonymous access is ALLOWED (the old hole)."""
    r = httpx.request(
        "PROPFIND",
        f"{base}/",
        headers={"Depth": "0"},
        timeout=20,
        verify=CFG.verify_tls,
    )
    return r.status_code in {200, 207}


def probe_bookstack(base, cred, login_id, password) -> bool:
    # Email-keyed form login with a Laravel CSRF token.
    with _client() as c:
        g = c.get(f"{base}/login")
        token = _hidden_input(g.text, "_token")
        if not token:
            return False
        r = c.post(
            f"{base}/login",
            data={"email": login_id, "password": password, "_token": token},
        )
        if r.status_code in {301, 302, 303}:
            return "/login" not in r.headers.get("location", "")
        return False


def probe_limesurvey(base, cred, login_id, password) -> bool:
    # Unused placeholder: LimeSurvey's Yii admin login isn't HTTP-scriptable, so
    # its AppCheck uses limesurvey_db_check instead. Kept for a uniform signature.
    return False


def probe_wordpress(base, cred, login_id, password) -> bool:
    # Form login: a wp_logged_in cookie in the jar means the credential worked.
    with _client() as c:
        c.get(f"{base}/wp-login.php")
        c.cookies.set("wordpress_test_cookie", "WP Cookie check")
        c.post(
            f"{base}/wp-login.php",
            data={
                "log": login_id,
                "pwd": password,
                "wp-submit": "Log In",
                "testcookie": "1",
                "redirect_to": f"{base}/wp-admin/",
            },
        )
        return any(k.startswith("wordpress_logged_in") for k in c.cookies)


def probe_easyappointments(base, cred, login_id, password) -> bool:
    # Basic-auth on the REST API validates through the same Accounts::check_login
    # the login form uses (401 on bad creds).
    r = httpx.get(
        f"{base}/index.php/api/v1/settings",
        auth=(login_id, password),
        timeout=20,
        verify=CFG.verify_tls,
    )
    return r.status_code == 200 and r.text.lstrip().startswith(("[", "{"))


def probe_bugsink(base, cred, login_id, password) -> bool:
    # Django form login (username-keyed) with a CSRF token.
    with _client() as c:
        gp = c.get(f"{base}/accounts/login/")
        m = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', gp.text)
        r = c.post(
            f"{base}/accounts/login/",
            data={
                "username": login_id,
                "password": password,
                "csrfmiddlewaretoken": m.group(1) if m else "",
            },
            headers={"Referer": f"{base}/accounts/login/"},
        )
        if r.status_code in {301, 302, 303}:
            return "/accounts/login" not in r.headers.get("location", "")
        return False


def probe_vikunja(base, cred, login_id, password) -> bool:
    r = httpx.post(
        f"{base}/api/v1/login",
        json={"username": login_id, "password": password},
        timeout=20,
        verify=CFG.verify_tls,
    )
    return r.status_code == 200 and '"token"' in r.text


def probe_isso(base, cred, login_id, password) -> bool:
    # Password-only admin dashboard: POST the password to /login/; success is a
    # 302 that sets an admin-session cookie (login_id is unused — no username).
    r = httpx.post(
        f"{base}/login/",
        data={"password": password},
        timeout=20,
        verify=CFG.verify_tls,
    )
    if r.status_code in {301, 302, 303}:
        return "admin-session" in " ".join(r.headers.get_list("set-cookie"))
    return False


def probe_paheko(base, cred, login_id, password) -> bool:
    # Email-keyed form login; the CSRF hidden field is named ct_<sha1> (dynamic).
    login_url = f"{base}/admin/login.php"
    with _client() as c:
        g = c.get(login_url)
        m = re.search(r'name=["\'](ct_[0-9a-f]+)["\'][^>]*value=["\']([^"\']*)["\']', g.text)
        if not m:
            return False
        r = c.post(
            login_url,
            data={
                "id": login_id,
                "password": password,
                "login": "1",
                m.group(1): m.group(2),
            },
        )
        if r.status_code in {301, 302, 303}:
            loc = r.headers.get("location", "")
            return "/admin/" in loc and "login" not in loc.lower()
        return False


def probe_invoiceninja(base, cred, login_id, password) -> bool:
    r = httpx.post(
        f"{base}/api/v1/login",
        json={"email": login_id, "password": password},
        headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
        timeout=20,
        verify=CFG.verify_tls,
    )
    return r.status_code == 200 and '"token"' in r.text


# --------------------------------------------------------------------------- #
# Registration-closed probes: return True iff signup is CLOSED.
# --------------------------------------------------------------------------- #


def reg_closed_gitea(base, cred) -> bool:
    r = httpx.get(
        f"{base}/user/sign_up",
        timeout=20,
        verify=CFG.verify_tls,
        follow_redirects=False,
    )
    if r.status_code in {302, 303, 404}:
        return True
    body = r.text.lower()
    return "registration" in body and ("disabled" in body or "closed" in body)


def reg_closed_mattermost(base, cred) -> bool:
    r = httpx.post(
        f"{base}/api/v4/users",
        json={
            "email": "probe-x@example.com",
            "username": "probe_x",
            "password": "Abcd1234!x",
        },
        timeout=20,
        verify=CFG.verify_tls,
    )
    # 501 = "User sign-up with email is disabled" (EnableSignUpWithEmail=false);
    # 403 = server-side creation disabled. Either means the land-grab is closed.
    return r.status_code in {400, 403, 501}


# --------------------------------------------------------------------------- #
# SSH DB check (LimeSurvey — its Yii admin login is not HTTP-scriptable)
# --------------------------------------------------------------------------- #

LIMESURVEY_OLD_DEFAULT = "change-me-admin-password"

# PHP (no single quotes — uses \x27 — so it nests safely inside a single-quoted
# `php -r '...'`). Reads the DB creds from config.php and password_verify()s the
# generated + old-default passwords against the stored bcrypt hash.
_LIMESURVEY_PHP = (
    '$c=file_get_contents("application/config/config.php");'
    '$re=function($k)use($c){'
    'preg_match("/\\x27".$k."\\x27\\s*=>\\s*\\x27([^\\x27]*)\\x27/",$c,$m);'
    'return $m[1]??"";};'
    '$pdo=new PDO($re("connectionString"),$re("username"),$re("password"));'
    '$rows=$pdo->query("SELECT users_name,password FROM lime_users")'
    "->fetchAll(PDO::FETCH_ASSOC);"
    'if(!$rows){echo "NOROWS\\n";}'
    'foreach($rows as $r){'
    'echo "USER=".$r["users_name"]'
    '." GEN=".(password_verify(getenv("GEN"),$r["password"])?"yes":"no")'
    '." OLD=".(password_verify(getenv("OLD"),$r["password"])?"yes":"no")."\\n";}'
)


def limesurvey_db_check(host, app_name, cred) -> list[tuple[str, bool, str]]:
    """Verify LimeSurvey's admin at the DB level over SSH (functional check).

    LimeSurvey's Yii admin login resists scripted HTTP login, so we probe the
    stored bcrypt hash directly: the generated password must verify, and the old
    default must not. Requires SSH (root@host) to the box.
    """
    remote = (
        f"cd /home/hop3/apps/{app_name}/src 2>/dev/null || {{ echo NOAPP; exit 0; }}\n"
        f"sudo -u hop3 env GEN={shlex.quote(cred.password)} "
        f"OLD={shlex.quote(LIMESURVEY_OLD_DEFAULT)} php -r {shlex.quote(_LIMESURVEY_PHP)}"
    )
    proc = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=10", f"root@{host}", "bash -s"],
        input=remote,
        capture_output=True,
        text=True,
        check=False,
    )
    m = re.search(r"USER=(\S+)\s+GEN=(yes|no)\s+OLD=(yes|no)", proc.stdout)
    if not m:
        detail = (proc.stdout + proc.stderr).strip().splitlines()
        return [("db_admin_check", False, f"no admin row / ssh error: {detail[-1:]}")]
    return [
        ("old_default_rejected", m.group(3) == "no", "DB password_verify (SSH)"),
        ("generated_login_works", m.group(2) == "yes", f"DB user={m.group(1)} (SSH)"),
    ]


# --------------------------------------------------------------------------- #
# App registry
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class AppCheck:
    app_id: str
    probe: Callable  # (base, cred, login_id, password) -> bool
    # (login_id, password) that MUST be rejected; a literal here.
    old_default: tuple[str, str] | None
    # which identity the generated login uses: "username" or "email".
    generated_login_key: str = "username"
    registration_closed: Callable | None = None  # (base, cred) -> bool
    extra: list[tuple] = field(default_factory=list)  # (name, callable, expected)
    # For apps whose admin login isn't HTTP-scriptable (LimeSurvey's Yii form):
    # (host, app_name, cred) -> [(check, ok, detail)]; replaces the HTTP login
    # assertions with a direct check over SSH.
    db_check: Callable | None = None


CHECKS: dict[str, AppCheck] = {
    "bugsink": AppCheck("bugsink", probe_bugsink, None),  # ADR-056 reference app
    "miniflux": AppCheck("miniflux", probe_miniflux, ("admin", "changeme")),
    "nextcloud": AppCheck("nextcloud", probe_nextcloud, ("admin", "changeme")),
    "keycloak": AppCheck("keycloak", probe_keycloak, ("admin", "changeme")),
    "kanboard": AppCheck("kanboard", probe_kanboard, ("admin", "admin")),
    "bookstack": AppCheck(
        "bookstack",
        probe_bookstack,
        ("admin@admin.com", "password"),
        generated_login_key="email",
    ),
    "limesurvey": AppCheck(
        "limesurvey",
        probe_limesurvey,  # unused: LimeSurvey login isn't HTTP-scriptable
        None,
        db_check=limesurvey_db_check,
    ),
    "gitea": AppCheck("gitea", probe_gitea, None, registration_closed=reg_closed_gitea),
    "forgejo": AppCheck(
        "forgejo", probe_gitea, None, registration_closed=reg_closed_gitea
    ),
    "mattermost": AppCheck(
        "mattermost",
        probe_mattermost,
        None,
        # Login works by username; the mmctl-created admin's email isn't a valid
        # login_id here ("invalid_credentials_username" on the email form).
        generated_login_key="username",
        registration_closed=reg_closed_mattermost,
    ),
    "radicale": AppCheck(
        "radicale",
        probe_radicale,
        None,
        extra=[("anonymous_access_closed", probe_radicale_anonymous, False)],
    ),
    # Web-installer apps (fresh headless install; no prior default admin except EA).
    "wordpress": AppCheck("wordpress", probe_wordpress, None),
    "easy-appointments": AppCheck(
        "easy-appointments", probe_easyappointments, ("administrator", "administrator")
    ),
    "invoice-ninja": AppCheck(
        "invoice-ninja", probe_invoiceninja, None, generated_login_key="email"
    ),
    "paheko": AppCheck("paheko", probe_paheko, None, generated_login_key="email"),
    "vikunja": AppCheck("vikunja", probe_vikunja, None),  # login by username → JWT
    "isso": AppCheck("isso", probe_isso, None),  # password-only admin dashboard
}


# --------------------------------------------------------------------------- #
# Deploy + verify
# --------------------------------------------------------------------------- #


def deploy(app_id: str) -> str | None:
    """Install one app from the catalog (public URL) via `hop3 catalog install`.

    Installed under its own id (`--app <app_id>`), which yields the public
    `<app_id>.<admin-domain>` vhost the login probes need. PRECONDITION: the
    tested recipe must already be promoted + staged into the catalog this server
    installs from. Returns the app name on success, else None.
    """
    print(f"  hop3 catalog install {app_id} --app {app_id} ...", flush=True)
    proc = subprocess.run(
        ["hop3", "catalog", "install", app_id, "--app", app_id],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-15:])
        print(f"  INSTALL FAILED for {app_id}:\n{tail}")
        return None
    return app_id


def teardown(app_name: str) -> None:
    """Destroy a verified app (best-effort) so re-runs don't accumulate state."""
    subprocess.run(
        ["hop3", "app", "destroy", "--app", app_name, "--force"],
        capture_output=True,
        text=True,
        check=False,
    )


def resolve_login_id(check: AppCheck, cred: Credential) -> str:
    return cred.email if check.generated_login_key == "email" else cred.username


def verify_app(
    check: AppCheck, app_name: str, host: str
) -> list[tuple[str, bool, str]]:
    """Run all checks for one app. Returns [(check_name, ok, detail)]."""
    results: list[tuple[str, bool, str]] = []
    try:
        cred = read_generated_credential(app_name)
    except RuntimeError as e:
        return [("credentials_retrieved", False, str(e).splitlines()[0])]
    results.append(("credentials_retrieved", True, f"user={cred.username or cred.email}"))

    base = cred.url
    login_id = resolve_login_id(check, cred)

    # Login assertions: either an SSH DB check (login not HTTP-scriptable) or the
    # HTTP auth probe (old default rejected + generated accepted).
    if check.db_check is not None:
        results.extend(check.db_check(host, app_name, cred))
    else:
        if check.old_default is not None:
            old_id, old_pw = check.old_default
            try:
                accepted = check.probe(base, cred, old_id, old_pw)
                results.append(("old_default_rejected", not accepted, f"{old_id}/{old_pw}"))
            except httpx.HTTPError as e:
                results.append(("old_default_rejected", False, f"probe error: {e}"))

        try:
            accepted = check.probe(base, cred, login_id, cred.password)
            results.append(("generated_login_works", accepted, f"as {login_id}"))
        except httpx.HTTPError as e:
            results.append(("generated_login_works", False, f"probe error: {e}"))

    if check.registration_closed is not None:
        try:
            results.append(
                ("registration_closed", check.registration_closed(base, cred), "")
            )
        except httpx.HTTPError as e:
            results.append(("registration_closed", False, f"probe error: {e}"))

    for name, fn, expected in check.extra:
        try:
            ok = fn(base, cred, cred.username, cred.password) == expected
            results.append((name, ok, ""))
        except httpx.HTTPError as e:
            results.append((name, False, f"probe error: {e}"))

    return results


def run_verification(
    apps: list[str],
    *,
    host: str = DEFAULT_HOST,
    do_deploy: bool = False,
    cleanup: bool = False,
    insecure: bool = False,
    name_map: dict[str, str] | None = None,
) -> bool:
    """Verify the given apps; return True iff every check passed."""
    CFG.verify_tls = not insecure
    name_map = name_map or {}

    print(
        f"Verifying catalog apps against {host} "
        f"(TLS verify={'on' if CFG.verify_tls else 'OFF'})\n"
    )

    all_ok = True
    for app_id in apps:
        check = CHECKS[app_id]
        print(f"== {app_id} ==")

        if do_deploy:
            app_name = deploy(app_id)
            if app_name is None:
                # A failed install can leave a partial app + a generated
                # credential the next install reuses; tear it down.
                if cleanup:
                    teardown(app_id)
                print("  FAIL: deploy failed\n")
                all_ok = False
                continue
        else:
            app_name = name_map.get(app_id, app_id)
            print(f"  verifying deployed app '{app_name}'")

        app_ok = True
        for name, ok, detail in verify_app(check, app_name, host):
            mark = "PASS" if ok else "FAIL"
            app_ok = app_ok and ok
            extra = f"  [{detail}]" if detail else ""
            print(f"  [{mark}] {name}{extra}")
        all_ok = all_ok and app_ok

        if do_deploy and cleanup:
            teardown(app_name)
            print(f"  (cleaned up '{app_name}')")
        print()

    print("=" * 60)
    print("ALL CHECKS PASSED" if all_ok else "SOME CHECKS FAILED")
    return all_ok
