# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Screenshot a catalog app while its test has it deployed.

Two images per app, its sign-in page and its first page once signed in, for
the application gallery and the experience reports. They land in the recipe's
own ``screenshots/`` directory in the catalog checkout, which the catalog
loader lists and publishes with the recipe.

**A real browser, over HTTPS, at the app's own name.** A screenshot shows what a
user sees, so it is taken through nginx with TLS and real rendering. The test
hostname (``<app>.test.local``) exists only in the server's nginx, so Chromium
is told to resolve it to the server, which is what DNS does for a real domain.
A Docker target's vhosts are reachable only through a Host header on a
published port, which a browser cannot send, so screenshots need a server.

**Verification as well as documentation.** Some apps build their sign-in form
in JavaScript, so their ``check.py`` cannot sign in over HTTP and says so
(``SIGN-IN VERIFIED BY BROWSER``). For those, the signed-in shot is the
evidence that the credential works, and a failed one fails the test.

Playwright is a large dependency used only here, so it is imported when a shot
is taken: run ``uv run --with playwright hop3-test run ... --screenshots``.
"""

from __future__ import annotations

import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

PAGE_TIMEOUT_MS = 30_000
#: After submitting the form, give the app a moment to finish its post-login
#: redirect and first render. A fixed settle beats racing a `networkidle` that
#: some of these apps never reach (long-polling, websockets).
SETTLE_MS = 3_000

#: Longer than the page timeout on purpose: capture is the step that has hung.
SCREENSHOT_TIMEOUT_MS = 60_000

#: How long a sign-in form may take to appear, and to go away once submitted.
#: Several of these apps build their form in JavaScript (Keycloak's console,
#: Mattermost, Vikunja, Easy!Appointments) and sign in over XHR without ever
#: navigating. Asking the DOM once, the instant the document loads, reported
#: those as "no password field found" and, after a successful submit, as a
#: refused credential.
FORM_WAIT_MS = 15_000

LOGIN_SHOT = "01-login"
SIGNED_IN_SHOT = "02-signed-in"

INSTALL_HINT = (
    "run hop3-test with Playwright and its browser:\n"
    "  uv run --with playwright playwright install chromium   # once\n"
    "  uv run --with playwright hop3-test run --host <server> --screenshots ..."
)


class ScreenshotError(Exception):
    """A shot could not be taken; the message says what the page was doing."""


@dataclass(frozen=True)
class ScreenshotSettings:
    """Where a run files its images."""

    catalog_apps: Path
    """The catalog checkout's ``apps/``: each recipe's images go beside it."""

    copy_to: Path | None = None
    """A second directory every image is copied into (the experience reports)."""


@dataclass(frozen=True)
class SignIn:
    """Everything needed to sign in to one deployed app."""

    app_id: str
    """The recipe id: it names the images and selects the override."""

    url: str
    """``https://<the app's hostname>``."""

    resolve_to: str
    """The server the hostname resolves to."""

    identifier: str
    password: str

    email: str = ""
    """The credential's email, when it has one. Kept beside the identifier
    because the FORM decides which is usable: paheko authenticates on the login
    name but renders ``<input type=email>``, so a browser refuses to submit
    "admin" before the app ever sees it."""

    @classmethod
    def from_credentials(
        cls, app_id: str, url: str, resolve_to: str, credentials: dict[str, str]
    ) -> SignIn:
        """
        Sign in with the admin credential ``check_credentials`` hands a check.

        The operator's account, which is what a gallery shows. Its identifier is
        the field the app's form takes (``HOP3_ADMIN_LOGIN``): offering the
        other one is refused as a bad password.
        """
        password = credentials.get("HOP3_ADMIN_PASSWORD", "")
        if not password:
            msg = "the server holds no admin credential for this app"
            raise ScreenshotError(msg)
        username = credentials.get("HOP3_ADMIN_USER", "")
        email = credentials.get("HOP3_ADMIN_EMAIL", "")
        if credentials.get("HOP3_ADMIN_LOGIN") == "email":
            identifier = email
        else:
            identifier = username or email
        return cls(
            app_id=app_id,
            url=url,
            resolve_to=resolve_to,
            identifier=identifier,
            password=password,
            email=email,
        )


@dataclass(frozen=True)
class Override:
    """Per-app deviations from the generic sign-in flow."""

    login_path: str = ""
    #: Something to click before the form is reachable: an interstitial, a
    #: "continue in browser" link, a tab. Applied after the initial load.
    click_through: str = ""
    #: Explicit selectors, when the generic detection cannot find the fields.
    identifier_selector: str = ""
    password_selector: str = ""
    #: Apps whose sign-in a browser cannot drive at all, with the reason. These
    #: get the sign-in shot and no signed-in shot, reported as partial.
    unsupported: str = ""
    #: Authentication is HTTP Basic, not a form. The browser answers the
    #: server's challenge itself, so there is nothing to fill or submit.
    basic_auth: bool = False


# Where an app's sign-in form actually lives, when it is not at `/`.
#
# These are NOT the paths in each app's `check.py`, and mattermost shows why:
# its check posts to the REST endpoint `/api/v4/users/login`, while a browser
# needs the page at `/login`. One is an API target, the other is a document, so
# the browser path is stated here.
OVERRIDES: dict[str, Override] = {
    "easy-appointments": Override(login_path="/index.php/login"),
    "forgejo": Override(login_path="/user/login"),
    "gitea": Override(login_path="/user/login"),
    # A comment widget: `/` serves the embeddable JS, not a page with a form.
    "isso": Override(login_path="/admin/"),
    "limesurvey": Override(login_path="/index.php/admin/authentication/sa/login"),
    # A browser that has not chosen between the desktop app and the browser yet
    # (every fresh one) is sent to `/landing#/login`, which has no form. On
    # 2026-10-18 that page was all three recipes' sign-in image; the Nix
    # variants, which served no web client at all, had only an error line.
    "mattermost": Override(login_path="/login", click_through="text=View in Browser"),
    "wordpress": Override(login_path="/wp-login.php"),
    # Radicale authenticates with HTTP Basic against its htpasswd file. The
    # `.web` interface renders identically whether or not a credential was
    # sent, so a "signed-in" image would be the sign-in image again: on
    # 2026-07-30 the two files were byte-identical and reported as a pair.
    "radicale": Override(
        basic_auth=True,
        unsupported="HTTP Basic: the .web UI renders identically signed in",
    ),
    # Authenticates over socket.io; there is no form to fill. Its check drives
    # the app's own bundled client through node for the same reason.
    "uptime-kuma": Override(unsupported="signs in over socket.io, not a form"),
    # A Flutter canvas application: its inputs are not DOM elements.
    "invoice-ninja": Override(unsupported="Flutter canvas UI: inputs are not DOM"),
}


def override_for(app_id: str) -> Override:
    """
    The override for an app, falling back to the variant it was derived from.

    OVERRIDES is keyed by the native id, and the catalog carries the same
    application up to three times (`limesurvey`, `limesurvey-nix`,
    `limesurvey-nixgen`). Keyed lookup alone gave the variants the generic flow,
    so limesurvey-nix was photographed at `/`, which has no form. An exact key
    still wins, for a variant that genuinely differs.
    """
    if app_id in OVERRIDES:
        return OVERRIDES[app_id]
    for suffix in ("-nixgen", "-nix", "-docker"):
        if app_id.endswith(suffix):
            return OVERRIDES.get(app_id.removesuffix(suffix), Override())
    return Override()


def recipe_screenshot_dir(catalog_apps: Path, app_id: str) -> Path | None:
    """The ``screenshots/`` directory of the catalog recipe ``app_id``, if any."""
    matches = [d for d in catalog_apps.glob(f"*/{app_id}") if d.is_dir()]
    if len(matches) > 1:
        names = ", ".join(str(m) for m in matches)
        msg = f"two catalog recipes are named {app_id!r}: {names}"
        raise ScreenshotError(msg)
    return matches[0] / "screenshots" if matches else None


@dataclass(frozen=True)
class ScreenshotOutcome:
    """What the browser produced for one app, and why it stopped if it did."""

    written: tuple[Path, ...] = ()
    problem: str = ""
    #: Why no signed-in shot is possible for this app (an `Override.unsupported`).
    unsupported: str = ""

    @property
    def signed_in(self) -> bool:
        """The browser got past the sign-in form, and photographed what followed."""
        return any(SIGNED_IN_SHOT in p.name for p in self.written)


def self_test() -> str | None:
    """
    Why a browser cannot launch and render here, or None if it can.

    Run before the target is touched, so a missing browser costs seconds
    instead of a whole run.
    """
    try:
        from playwright.sync_api import (  # ruff:ignore[import-outside-top-level] — optional, see the module docstring
            sync_playwright,
        )
    except ImportError as e:
        return f"Playwright is not importable ({e}); {INSTALL_HINT}"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_context().new_page()
            page.set_content("<h1>ok</h1>")
            page.screenshot(path=str(Path(tempfile.mkdtemp()) / "probe.png"))
            browser.close()
    except Exception as e:  # ken: broad — the reason is the whole message
        return f"the browser could not launch or render: {e}; {INSTALL_HINT}"
    return None


def take(sign_in: SignIn, out_dir: Path, copy_to: Path | None) -> ScreenshotOutcome:
    """
    Take one app's shots into ``out_dir``, and copy them to ``copy_to`` if given.

    Never raises for the app's sake: a failure is the outcome's ``problem``,
    with the images taken before it.
    """
    written: list[Path] = []
    override = override_for(sign_in.app_id)
    try:
        _shoot(sign_in, override, out_dir, written)
    except Exception as e:  # ken: broad — one app's browser failure is its outcome
        return ScreenshotOutcome(tuple(written), problem=str(e))
    if copy_to is not None:
        copy_to.mkdir(parents=True, exist_ok=True)
        for path in written:
            shutil.copy2(path, copy_to / path.name)
    return ScreenshotOutcome(tuple(written), unsupported=override.unsupported)


def _shoot(
    sign_in: SignIn, override: Override, out_dir: Path, written: list[Path]
) -> None:
    """Take the two shots for one app, appending each to ``written``."""
    from playwright.sync_api import (  # ruff:ignore[import-outside-top-level] — optional, see the module docstring
        sync_playwright,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    host = urlsplit(sign_in.url).hostname
    with sync_playwright() as p:
        browser = p.chromium.launch(
            args=[f"--host-resolver-rules=MAP {host} {sign_in.resolve_to}"]
        )
        # A fixed viewport keeps the set visually consistent; the test server's
        # certificate is self-signed, which must not stop us documenting an app
        # that is otherwise working.
        context_args: dict[str, Any] = {
            "viewport": {"width": 1280, "height": 800},
            "ignore_https_errors": True,
        }
        if override.basic_auth:
            context_args["http_credentials"] = {
                "username": sign_in.identifier,
                "password": sign_in.password,
            }
        context = browser.new_context(**context_args)
        page = context.new_page()
        page.set_default_timeout(PAGE_TIMEOUT_MS)
        watcher = PageWatcher(page)
        try:
            page.goto(sign_in.url + override.login_path, wait_until="load")
            page.wait_for_timeout(SETTLE_MS)
            if override.click_through:
                _click_through(page, override.click_through)
            login_shot = out_dir / f"{sign_in.app_id}-{LOGIN_SHOT}.png"
            _capture(page, login_shot, watcher)
            written.append(login_shot)

            if override.unsupported:
                return

            # Every path to a second shot goes through _assert_signed_in. A
            # `basic_auth` branch that reloaded and photographed skipped it, and
            # produced two byte-identical Radicale images reported as a pair.
            _sign_in(page, sign_in, override)
            page.wait_for_timeout(SETTLE_MS)
            _assert_signed_in(
                page, override.password_selector or "input[type=password]"
            )
            after_shot = out_dir / f"{sign_in.app_id}-{SIGNED_IN_SHOT}.png"
            _capture(page, after_shot, watcher)
            written.append(after_shot)
        finally:
            context.close()
            browser.close()


class PageWatcher:
    """
    What the page is still waiting for, and what it complained about.

    A hung capture reports only "Timeout exceeded". paheko's screenshot failed
    identically at 30s and at 60s, with animations disabled and with its PHP
    workers doubled: three guesses, no evidence. The browser knows what it is
    blocked on; it just was never asked.
    """

    def __init__(self, page) -> None:
        self._inflight: dict[Any, str] = {}
        self.errors: list[str] = []
        page.on("request", lambda r: self._inflight.__setitem__(r, r.url))
        page.on("requestfinished", lambda r: self._inflight.pop(r, None))
        page.on("requestfailed", lambda r: self._inflight.pop(r, None))
        page.on("pageerror", lambda e: self.errors.append(str(e)[:200]))

    def report(self) -> str:
        """One line naming what is outstanding, or that nothing is."""
        parts = []
        if self._inflight:
            urls = sorted(self._inflight.values())[:5]
            parts.append(f"still fetching {len(self._inflight)}: {', '.join(urls)}")
        else:
            parts.append("no requests outstanding")
        if self.errors:
            parts.append(f"page errors: {self.errors[:3]}")
        return "; ".join(parts)


def _capture(page, path: Path, watcher: PageWatcher) -> None:
    """
    Take one shot, with animations frozen.

    A page that never settles never returns: paheko's sign-in page animates
    continuously. `animations="disabled"` fast-forwards CSS animations to their
    end state, which makes the capture terminate and the images reproducible.
    """
    try:
        page.screenshot(
            path=str(path),
            full_page=False,
            animations="disabled",
            timeout=SCREENSHOT_TIMEOUT_MS,
        )
    except Exception as e:  # ken: broad — re-raised with what the page was doing
        msg = f"{type(e).__name__}: {str(e).splitlines()[0]} ({watcher.report()})"
        raise ScreenshotError(msg) from e


def _click_through(page, selector: str) -> None:
    """
    Get past an interstitial that stands between the URL and the form.

    An override that names a gate asserts the gate is there. If it never
    appears, that assertion is wrong and the run says which one.
    """
    gate = page.locator(selector)
    try:
        gate.first.wait_for(state="visible", timeout=FORM_WAIT_MS)
    except Exception as e:  # ken: broad — Playwright's timeout, restated
        msg = (
            f"the declared click-through {selector!r} never appeared at "
            f"{page.url} (waited {FORM_WAIT_MS // 1000}s): the page changed, "
            f"or the interstitial is gone and the override with it"
        )
        raise ScreenshotError(msg) from e
    gate.first.click()
    page.wait_for_load_state("load")
    page.wait_for_timeout(SETTLE_MS)


def _sign_in(page, sign_in: SignIn, override: Override) -> None:
    """
    Fill and submit the sign-in form.

    Generic by default: find the password box, then the nearest text or email
    input. The exceptions are declared in OVERRIDES rather than guessed at.
    """
    password_sel = override.password_selector or "input[type=password]"
    try:
        page.locator(password_sel).first.wait_for(state="visible", timeout=FORM_WAIT_MS)
    except Exception as e:  # ken: broad — Playwright's timeout, restated
        msg = (
            f"no password field found at {page.url} after "
            f"{FORM_WAIT_MS // 1000}s: the page serves no sign-in form, or "
            f"builds one this harness cannot see"
        )
        raise ScreenshotError(msg) from e

    identifier_sel = (
        override.identifier_selector
        or "input[type=text], input[type=email], input:not([type])"
    )
    # Isso's moderation dashboard is password-only: there is no account to
    # name, and a password on its own is a complete credential for it.
    if page.locator(identifier_sel).count():
        field = page.locator(identifier_sel).first
        field.fill(_identifier_for(field.get_attribute("type"), sign_in))

    page.locator(password_sel).first.fill(sign_in.password)
    _submit(page, password_sel)
    page.wait_for_load_state("load")


def _submit(page, password_sel: str) -> None:
    """
    Submit the form the way a user would: click its button.

    An application that binds its handler to the button's click ignores Enter,
    and the form stays on screen, which reads as a refused credential. Enter
    remains the fallback for forms that expose no button at all.
    """
    for selector in (
        "button[type=submit]",
        "input[type=submit]",
        "form button",
        "button",
    ):
        control = page.locator(selector)
        if control.count() and control.first.is_visible():
            control.first.click()
            return
    page.locator(password_sel).first.press("Enter")


def _identifier_for(field_type: str | None, sign_in: SignIn) -> str:
    """
    The identifier a field of this type will accept.

    An `<input type=email>` is validated by the browser before the form is
    submitted, so a login name without an "@" never leaves the page. Where the
    field demands an email and we hold one, send that.
    """
    if (field_type or "").lower() == "email" and sign_in.email:
        return sign_in.email
    return sign_in.identifier


def _assert_signed_in(page, password_sel: str) -> None:
    """
    Refuse to call the next screenshot "signed in" without evidence.

    A sign-in that fails leaves the form on screen, and photographing it files
    the image as proof the application works. The evidence is the form's
    absence: VISIBLE fields only (Nextcloud keeps a hidden password input in its
    markup), given time to disappear (an app that signs in over XHR replaces
    the form without navigating).
    """
    visible_password = page.locator(password_sel).locator("visible=true")
    deadline = time.monotonic() + FORM_WAIT_MS / 1000
    while visible_password.count() > 0:
        if time.monotonic() >= deadline:
            msg = (
                f"still on a sign-in form after submitting ({page.url}): "
                f"the credential was refused, or the field would not accept it"
            )
            raise ScreenshotError(msg)
        page.wait_for_timeout(250)
