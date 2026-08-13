# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
Support library for an app's ``check.py``, uploaded beside it and run ON the server.

Every app's smoke test is a plain Python script, so it can express whatever that
app actually needs — a form login, HTTP Basic, a socket.io handshake, or a
sequence of authenticated actions after signing in. This module exists so those
scripts stay *similar*: same entry point, same request plumbing, same failure
wording, same exit codes. Only the app-specific steps differ.

A script looks like::

    from hop3.server.checks import run

    def check(c):
        c.step("sign in")
        page = c.get("/login")
        token = c.extract(page, r'name="_token" value="([^"]+)"')
        form_data = {
            "email": c.admin.email,
            "password": c.admin.password,
            "_token": token,
        }
        c.post("/login", form_data)
        c.signed_in_looks_like("/", contains="Log out")
        c.expect_signed_in()

        c.step("a wrong password is refused")
        c.expect_sign_in_refused(...)

    run(check)

Failure is always loud and specific: every helper says what it expected, what it
got, and which step it was on. A check that cannot run (no credentials, missing
token) FAILS — it never degrades into a weaker assertion, because a smoke test
that quietly tests less than it claims is worse than none.
"""

from __future__ import annotations

import os
import re
import sys
import traceback
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypedDict, Unpack

import httpx

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

TIMEOUT = 30.0

#: Printed by a check whose sign-in needs a real browser. The runner reports the
#: weaker claim, and the catalog driver requires the browser harness to have
#: signed in before calling such an app verified.
BROWSER_REQUIRED_MARKER = "SIGN-IN VERIFIED BY BROWSER"


class RequestOptions(TypedDict, total=False):
    """
    The httpx options a check may pass through ``get``/``post``.

    Named rather than opened up as ``**kwargs: Any``: a check script is written
    against this class, so the set of things it can send is part of the contract
    and shows up in an editor. Add a field when a real check needs one.
    """

    headers: Mapping[str, str]
    params: Mapping[str, str]
    auth: tuple[str, str]
    json: Any
    follow_redirects: bool
    #: Rarely needed: ``LoopbackTransport`` already sets the SNI name, and it
    #: overrides whatever is passed here.
    extensions: Mapping[str, Any]


class LoopbackTransport(httpx.HTTPTransport):
    """
    Reach the app over loopback while the REQUEST keeps its real hostname.

    The check runs on the server, so the app is reachable at 127.0.0.1 and no
    DNS or egress is needed. The obvious way to express that — point the client
    at ``https://localhost`` and override the ``Host`` header — has a defect
    that took a long time to find, because it fails silently and only for some
    applications.

    **Cookies are scoped by the host in the request URL.** An application that
    sets ``Set-Cookie: session=...; Domain=matomo.example.com`` is telling the
    client to store that cookie for *that* domain; a client that believes it is
    talking to ``localhost`` discards it, without error. The sign-in then
    succeeds — Matomo answered 302, the credentials were accepted — and every
    request afterwards is anonymous, which reads exactly like a refused
    password. Applications whose cookies carry no ``Domain`` were unaffected,
    so the failure looked app-specific rather than transport-wide.

    Rewriting the connection target here, below the cookie layer, gives both:
    the client (and its cookie jar) sees the real hostname, while the socket
    goes to loopback. It is what ``curl --resolve`` does, for the same reason.
    """

    def __init__(self, host: str, port: int, *, verify: bool = False) -> None:
        # Named rather than **kwargs: this transport needs one option, and the
        # certificate is not verified because these are self-signed per-host
        # certs and the connection never leaves the machine.
        super().__init__(verify=verify)
        self._host = host
        self._port = port

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        real_url = request.url
        # The port follows the SCHEME, not this transport's own. Forcing 443
        # onto everything sent a plain-HTTP request to the TLS port the moment
        # an app redirected to an http:// URL of itself — nginx answered "400
        # The plain HTTP request was sent to HTTPS port", which paheko hit while
        # following its post-login redirect. Apps do emit absolute http:// URLs
        # for themselves; the transport has to cope rather than assume.
        port = self._port if request.url.scheme == "https" else 80
        request.url = request.url.copy_with(host="127.0.0.1", port=port)
        # nginx selects the vhost by SNI over TLS; the Host header is already
        # the app's, set by httpx from the real URL when the request was built.
        request.extensions = {**request.extensions, "sni_hostname": self._host}
        try:
            return super().handle_request(request)
        finally:
            # The rewrite is for the SOCKET only. httpx scopes cookies off
            # `response.request.url`, which it reads after this returns — leave
            # loopback in place and the jar files every cookie under 127.0.0.1,
            # then never sends one back, because outgoing headers are built
            # against the real hostname. That loses the session for every app
            # that has one, which is a refused password to anyone reading the
            # report. Restoring here is what makes the docstring above true.
            request.url = real_url


def _tag_attrs(tag: str) -> dict[str, str]:
    """
    An HTML tag's attributes, in whatever order they were written.

    One definition, because every caller that re-derived it got it slightly
    differently and one of those variants — `name="X"\\s+value="Y"` — cost four
    applications a working sign-in by demanding an attribute order no renderer
    guarantees.
    """
    return dict(re.findall(r"""([\w:-]+)\s*=\s*["']([^"']*)["']""", tag))


class CheckError(Exception):
    """An expectation did not hold. Carries an operator-readable explanation."""


class BrowserRequired(Exception):  # ruff: ignore[error-suffix-on-exception-name] — a signal, not an error
    """
    This application's sign-in cannot be driven over plain HTTP.

    Some admin interfaces are rendered by JavaScript: LimeSurvey answers a
    form POST with "LimeSurvey does not work without Javascript being activated
    in the browser", and Easy!Appointments serves a page containing no form
    inputs at all. No token handling or URL fixes those — there is nothing to
    post until a script has run.

    Raising this is NOT a failure and NOT a pass. It records that the sign-in is
    verified by the browser harness instead (`shoot-catalog.py`, which drives a
    real browser and refuses to photograph a page that still shows a login
    form), so the two halves together cover what neither can alone.
    """


@dataclass(frozen=True)
class Admin:
    """The credential Hop3 generated for this app (ADR 056)."""

    username: str
    email: str
    password: str

    @property
    def identity(self) -> str:
        """Whichever identifier the app signs in with, preferring the username."""
        return self.username or self.email


class Check:
    """
    One app's smoke-test session: a client bound to the app's vhost.

    The client addresses the app by its REAL hostname; the socket goes to
    loopback (see ``LoopbackTransport``), because the script runs on the server
    where that reaches nginx and needs neither DNS nor egress. Cookies persist
    across calls, so a sign-in carries into the requests that follow it.
    """

    def __init__(self, host: str, port: int = 443) -> None:
        self.host = host
        self.port = port
        # HTTPS, always. Two reasons this is not a preference:
        #   1. Hop3 redirects HTTP to HTTPS by default, so a plain-HTTP check
        #      would be testing the redirect rather than the app.
        #   2. An app served over HTTPS issues Secure session cookies, which a
        #      client never sends back over HTTP — so a sign-in over HTTP fails
        #      no matter how correct the credential is. Testing there would
        #      report every app as broken.
        # The certificate is not verified: these are self-signed or per-host
        # certs and the connection never leaves the server (localhost).
        # The app's REAL hostname, not "localhost". Cookies are scoped by the
        # request's host, so addressing the app as localhost made every
        # domain-scoped session cookie unstorable — see LoopbackTransport.
        self.base_url = f"https://{host}"
        #: The step being attempted; failures quote it so a report says where.
        self.current_step = "starting"
        self._auth_path = ""
        self._auth_marker = ""
        #: (path, status, location) of the most recent POST — the sign-in's own
        #: response, which the session assertion otherwise throws away.
        self._last_post: tuple[str, int, str] | None = None
        #: Body of the last POST when it came back 200 — the re-rendered
        #: form, which normally carries the reason for the refusal.
        self._last_post_body = ""
        #: The last page fetched, used as the Referer for a subsequent POST —
        #: the form's own page, as a browser would report it.
        self._last_get = "/"
        self.client = httpx.Client(
            base_url=self.base_url,
            transport=LoopbackTransport(host, port, verify=False),
            timeout=TIMEOUT,
            follow_redirects=False,
        )

    # -- credentials ------------------------------------------------------

    @property
    def connect_origin(self) -> str:
        """
        An origin an *external* tool can actually connect to.

        :attr:`base_url` names the app by its real hostname, which is right for
        the Python client: cookies are scoped by the request host, and
        :class:`LoopbackTransport` rewrites only the socket. A subprocess gets no
        such rewrite. Handed ``https://<app>.test.local`` it asks DNS, finds
        nothing, and fails — which is how uptime-kuma's socket.io probe reported
        ``connect_error: websocket error`` against an app that was serving fine.

        So a check that shells out passes this, plus :attr:`host` for the ``Host``
        header and the TLS server name. That is the same split the transport does
        internally: connect to loopback, address the app by name.
        """
        return f"https://127.0.0.1:{self.port}"

    @property
    def admin(self) -> Admin:
        """
        The app's generated admin credential, or FAIL.

        The harness injects these; their absence means the app declares no
        ``[admin]`` or the credential was never provisioned. Either way the
        login cannot be tested, and saying so beats passing a test that never
        signed in.
        """
        password = os.environ.get("HOP3_ADMIN_PASSWORD", "")
        if not password:
            msg = (
                "no admin credential was provided (HOP3_ADMIN_PASSWORD is unset), "
                "so the sign-in cannot be tested. Declare [admin] in hop3.toml, or "
                "check that the credential was provisioned for this app."
            )
            raise CheckError(msg)
        return Admin(
            username=os.environ.get("HOP3_ADMIN_USER", ""),
            email=os.environ.get("HOP3_ADMIN_EMAIL", ""),
            password=password,
        )

    @property
    def probe(self) -> Admin:
        """
        Hop3's OWN account for this app, or FAIL.

        Present only when the recipe declares [probe]. Unlike ``admin``, nobody
        else uses it and its password is Hop3's to rotate — so a refused
        sign-in here means the app broke, not that someone changed a password.
        """
        password = os.environ.get("HOP3_PROBE_PASSWORD", "")
        if not password:
            msg = (
                "this app declares no [probe] account, so there is no credential "
                "Hop3 still owns to sign in with"
            )
            raise CheckError(msg)
        return Admin(
            username=os.environ.get("HOP3_PROBE_USER", ""),
            email=os.environ.get("HOP3_PROBE_EMAIL", ""),
            password=password,
        )

    @property
    def has_probe(self) -> bool:
        """Does this app have a Hop3-owned account to sign in as?"""
        return bool(os.environ.get("HOP3_PROBE_PASSWORD"))

    @property
    def login(self) -> Admin:
        """
        The credential to sign in with: the probe when there is one.

        Falling back to the admin is deliberate but weaker — that credential
        belongs to the operator, so it verifies the HANDOVER and stops being
        Hop3's to assert once they change the password. Checks say which they
        used, so a green result is never more confident than it earned.
        """
        return self.probe if self.has_probe else self.admin

    # -- narration --------------------------------------------------------

    def step(self, name: str) -> None:
        """Name the step being attempted; failures quote it."""
        self.current_step = name
        print(f"  - {name}", flush=True)

    # -- requests ---------------------------------------------------------

    def get(self, path: str, **kwargs: Unpack[RequestOptions]) -> httpx.Response:
        return self._request("GET", path, **kwargs)

    def post(
        self, path: str, data: dict | None = None, **kwargs: Unpack[RequestOptions]
    ) -> httpx.Response:
        return self._request("POST", path, data=data, **kwargs)

    def _request(
        self,
        method: str,
        path: str,
        data: dict | None = None,
        **kwargs: Unpack[RequestOptions],
    ) -> httpx.Response:
        # SNI is set by LoopbackTransport, which is the layer that knows the URL
        # was rewritten. Setting it here as well meant two places had to agree
        # about a vhost-selection invariant, and only one of them was reached by
        # the tests.
        try:
            # `data` is passed explicitly, NOT left to ride in **kwargs. Naming
            # it in this signature takes it out of kwargs, and for a while it
            # was named here and then not forwarded — so every form sign-in
            # POSTed an empty body, the credentials never left the process, and
            # eighteen of the twenty catalog checks failed at once. They failed
            # invisibly too, because the CLI was exiting 0 on a reported
            # failure, so the runs kept printing PASS.
            if method == "POST":
                # Browsers send a Referer with a form submission, and CSRF
                # implementations check it: Django REJECTS a POST it considers
                # secure when the header is absent ("Referer checking failed"),
                # which is a 403 indistinguishable from a bad token. httpx sends
                # none, so a check that fetched a form and posted it back looked
                # to the app like a cross-site attack. Send the page the form
                # came from, which is what a browser would have sent.
                headers = dict(kwargs.get("headers") or {})
                headers.setdefault("Referer", f"https://{self.host}{self._last_get}")
                kwargs["headers"] = headers
            response = self.client.request(method, path, data=data, **kwargs)
            if method == "GET":
                self._last_get = path
            if method == "POST":
                # Kept for the failure message below. `expect_signed_in` proves
                # the SESSION by fetching a protected page, which is the right
                # assertion — but when it fails it could only report that later
                # GET, so a CSRF rejection (403), a re-rendered form (200) and a
                # redirect back to the login page were indistinguishable. The
                # sign-in's own response is the first thing anyone diagnosing
                # this wants, and it was being discarded.
                self._last_post = (
                    path,
                    response.status_code,
                    response.headers.get("location", ""),
                )
                self._last_post_body = (
                    response.text if response.status_code == 200 else ""
                )
            return response
        except httpx.HTTPError as e:
            msg = f"{method} {path} failed to complete: {e}"
            raise CheckError(msg) from e

    # -- extraction -------------------------------------------------------

    def extract(
        self, source: httpx.Response | str, pattern: str, what: str = "token"
    ) -> str:
        """
        Pull the first capture group of ``pattern`` out of a response body.

        Used for CSRF tokens, which nearly every form login requires. A missing
        one FAILS rather than posting without it: an empty token turns a real
        credential check into a token-rejection, which looks identical from the
        outside and would hide a genuine sign-in failure.
        """
        text = source.text if isinstance(source, httpx.Response) else source
        match = re.search(pattern, text)
        if not match:
            msg = (
                f"could not find the {what} in the page (pattern {pattern!r}). "
                f"The page may be an error or install screen rather than the "
                f"expected form; it began: {text[:200]!r}"
            )
            raise CheckError(msg)
        return match.group(1)

    # -- expectations -----------------------------------------------------

    def expect(self, condition: object, message: str) -> None:
        """Assert an app-specific condition, with an explanation on failure."""
        if not condition:
            raise CheckError(message)

    def requires_browser(self, reason: str) -> None:
        """
        Declare that this app's sign-in can only be driven by a real browser.

        Call after asserting whatever IS reachable over HTTP, so the check still
        proves the app is serving its own login surface.
        """
        raise BrowserRequired(reason)

    def form_token(self, source: httpx.Response | str, name: str) -> str:
        r"""
        The value of a hidden form input, whatever order its attributes are in.

        Every check used to spell this as `name="X"\s+value="([^"]+)"`, which
        demands that `name` come immediately before `value` with only whitespace
        between. Real markup does not oblige: attributes appear in any order,
        an `id` or `type` often sits between the two, and single quotes are
        legal. Four applications failed on exactly that — their sign-in page
        rendered perfectly and carried the token, and the pattern could not see
        it, so the check reported the page "may be an error or install screen".

        Parsing `<input>` attributes properly costs a few lines and removes a
        whole class of false failures, so it lives here rather than being
        re-derived, slightly differently, in twenty recipes.
        """
        html = source if isinstance(source, str) else source.text
        for tag in re.finditer(r"<input\b[^>]*>", html, re.IGNORECASE):
            attrs = _tag_attrs(tag.group(0))
            if attrs.get("name") == name and "value" in attrs:
                return attrs["value"]

        # Not every application puts its token in the form. Forgejo and Gitea
        # set a cookie of the same name and require the submitted field to match
        # it; Django and Laravel do the same under their own names. Verified on
        # a live Forgejo: its sign-in page carries no `_csrf` input at all —
        # `grep -c _csrf` over that page returns 0 through the check's transport
        # AND through a browser's, so this is how the token travels, not a
        # parsing failure on our side.
        cookie = self.client.cookies.get(name)
        if cookie:
            return cookie

        # Some frameworks expose it in a meta tag for their own JavaScript to
        # read; Forgejo does exactly this, and its sign-in form carries no token
        # input at all (verified: inputs present are user_name, password,
        # remember). Attributes are parsed rather than matched in order, for the
        # same reason as above.
        for tag in re.finditer(r"<meta\b[^>]*>", html, re.IGNORECASE):
            attrs = _tag_attrs(tag.group(0))
            if attrs.get("name") == name and attrs.get("content"):
                return attrs["content"]

        # Say what IS there. "Not found" sends the reader to fetch the page by
        # hand; the available field names usually identify the problem outright
        # — a renamed token, a token that moved into a <meta> tag, or a page
        # that is not the form at all.
        available = sorted({
            m.group(1)
            for tag in re.finditer(r"<input\b[^>]*>", html, re.IGNORECASE)
            for m in [re.search(r"""name\s*=\s*["']([^"']+)["']""", tag.group(0))]
            if m
        })
        meta = re.search(
            r"""<meta[^>]*name\s*=\s*["']([^"']*csrf[^"']*)["'][^>]*"""
            r"""content\s*=\s*["']([^"']+)["']""",
            html,
            re.IGNORECASE,
        )
        detail = f" Inputs present: {available or 'none'}."
        if meta:
            detail += (
                f" The page carries <meta name={meta.group(1)!r}> — this app puts "
                f"its token in a meta tag, not a form field."
            )
        msg = (
            f"no <input name={name!r}> with a value was found on the page.{detail} "
            f"The page began: {html[:160]!r}"
        )
        raise CheckError(msg)

    def form_action(self, source: httpx.Response | str, default: str = "") -> str:
        """
        Where the page's form actually posts.

        A check that hardcodes the POST path is guessing, and a wrong guess
        shows up as a 405 rather than as a failed sign-in: Isso serves its
        moderation login at ``/admin/`` but posts elsewhere, so posting back to
        ``/admin/`` returned Method Not Allowed. The page already says where it
        goes; asking it is both shorter and correct when the app changes.

        An empty or missing action means "post to this same URL", which is what
        ``default`` is for.
        """
        html = source if isinstance(source, str) else source.text
        match = re.search(r"<form\b[^>]*>", html, re.IGNORECASE)
        if match:
            action = re.search(
                r"""action\s*=\s*["']([^"']*)["']""", match.group(0), re.IGNORECASE
            )
            if action and action.group(1).strip():
                return action.group(1).strip()
        return default

    def form_fields(self, source: httpx.Response | str) -> dict[str, str]:
        """
        Every hidden field on the page, as a browser would resubmit them.

        A browser posts the WHOLE form; a check that hand-lists three fields
        posts three. Applications that carry state in additional hidden inputs —
        an action discriminator, a form id, a stage marker — then receive a
        request they treat as incomplete and answer by re-rendering the login
        page with HTTP 200, which is indistinguishable from a rejected password.

        Merge the credentials over the result::

            form = c.form_fields(page) | {"username": ..., "password": ...}

        Hidden fields, PLUS the submit control — because a browser sends the
        button it clicked, and some frameworks route on nothing else. Paheko's
        handler is `$form->runIf('login', ...)`: with no `login` key in the body
        it never runs, so the page came back 200 with the submitted email echoed
        into it and no error anywhere. Right password, wrong password and a
        deliberately OMITTED CSRF token all produced byte-identical responses —
        the signature of a form that was never processed rather than one that
        was rejected. Nothing about the credential was wrong.

        Other visible inputs are left out: they are the credentials themselves,
        and copying their (empty) rendered values back would overwrite what the
        caller is trying to send.
        """
        html = source if isinstance(source, str) else source.text
        fields: dict[str, str] = {}
        for tag in re.finditer(r"<input\b[^>]*>", html, re.IGNORECASE):
            attrs = _tag_attrs(tag.group(0))
            if attrs.get("type", "").lower() != "hidden":
                continue
            name = attrs.get("name")
            if name:
                fields[name] = attrs.get("value", "")

        submit = self._submit_control(html)
        if submit:
            fields.setdefault(*submit)
        return fields

    @staticmethod
    def _submit_control(html: str) -> tuple[str, str] | None:
        """
        The named submit control a browser would send, or None if it has no name.

        The FIRST one only. A browser sends exactly the control the user
        clicked, never all of them, and a form's later buttons are usually the
        ones you least want to trigger — cancel, delete, "reset password".
        `<button>` with no `type` is a submit button per the HTML spec, which is
        how paheko's is written.
        """
        for tag in re.finditer(r"<input\b[^>]*>|<button\b[^>]*>", html, re.IGNORECASE):
            attrs = _tag_attrs(tag.group(0))
            kind = attrs.get("type", "").lower()
            is_button = tag.group(0).lower().startswith("<button")
            if kind != "submit" and not (is_button and not kind):
                continue
            name = attrs.get("name")
            if name:
                return name, attrs.get("value", "")
        return None

    def expect_status(self, response: httpx.Response, *allowed: int) -> httpx.Response:
        if response.status_code not in allowed:
            expected = " or ".join(str(code) for code in allowed)
            msg = (
                f"{response.request.method} {response.request.url.path} returned "
                f"{response.status_code}, expected {expected}"
            )
            raise CheckError(msg)
        return response

    def signed_in_looks_like(self, path: str, contains: str) -> None:
        """
        Declare the page, and the marker on it, that proves a session is real.

        Declared once and used by BOTH the positive and negative assertions, so
        the two cannot drift apart. ``contains`` must appear ONLY when signed in
        — a logout link, the account name — never the app's title, which the
        login page carries too.
        """
        self._auth_path = path
        self._auth_marker = contains

    def _require_auth_page(self) -> tuple[str, str]:
        if not self._auth_path:
            msg = (
                "the check never declared what a signed-in session looks like; "
                "call c.signed_in_looks_like(path, contains) first"
            )
            raise CheckError(msg)
        return self._auth_path, self._auth_marker

    def _reaches_authenticated_page(self) -> tuple[bool, httpx.Response]:
        """Does THIS session reach the declared signed-in page?"""
        path, marker = self._require_auth_page()
        response = self.client.get(path, follow_redirects=True)
        return (response.status_code == 200 and marker in response.text), response

    def expect_signed_in(self) -> httpx.Response:
        """
        Prove the session is real by fetching a page only a signed-in user sees.

        This is the assertion that matters. A sign-in POST returning a redirect
        proves very little — apps redirect back to the login form on failure too
        — so the test is whether the session now reaches authenticated content.
        """
        path, marker = self._require_auth_page()
        reached, response = self._reaches_authenticated_page()
        if not reached:
            msg = (
                f"the sign-in did not establish a session: {path} returned "
                f"{response.status_code} and did not contain {marker!r}. Landed "
                f"on {response.url.path!r}, body began: {response.text[:200]!r}"
                f"{self._sign_in_post_summary()}"
                f"{self._cookie_summary()}"
            )
            raise CheckError(msg)
        return response

    def _cookie_summary(self) -> str:
        """
        Which cookies the session is holding, by name.

        The difference between "the app refused the credential" and "the app
        accepted it and we failed to keep the session" is invisible from the
        response alone, and the two need completely different fixes. Naming the
        jar's contents separates them in one line: no cookies after a 302 means
        the session was never stored, which is a transport problem, not an
        authentication one.
        """
        names = sorted(self.client.cookies.keys())
        if not names:
            return (
                " The session holds NO cookies — if the sign-in was accepted, "
                "they were not stored (check Domain/Path/Secure on Set-Cookie)."
            )
        return f" Session cookies held: {names}."

    def _sign_in_post_summary(self) -> str:
        """What the sign-in POST itself returned, for the failure message."""
        if not self._last_post:
            return ""
        path, status, location = self._last_post
        detail = f" The sign-in POST to {path!r} returned {status}"
        if location:
            detail += f" -> {location!r}"
        if status == 403:
            detail += " (403 usually means the CSRF token or Referer was rejected)"
        elif status == 200:
            detail += (
                " (200 on a login POST usually means the form came back with an error)"
            )
            detail += self._post_body_hint()
        return detail + "."

    def _post_body_hint(self) -> str:
        """
        Any error text the re-rendered form came back with.

        A login form returned at 200 has almost always re-rendered with the
        reason on it — "Wrong username or password", "CSRF token invalid", a
        missing-field notice. That sentence is the answer, and it was being
        discarded in favour of a later and less informative GET.
        """
        body = self._last_post_body
        if not body:
            return ""
        text = re.sub(
            r"<script\b.*?</script>", " ", body, flags=re.DOTALL | re.IGNORECASE
        )
        text = re.sub(r"<[^>]+>", " ", text)
        text = " ".join(text.split())
        for cue in ("error", "invalid", "incorrect", "wrong", "failed", "required"):
            index = text.lower().find(cue)
            if index != -1:
                excerpt = text[max(0, index - 80) : index + 120]
                return f" Response text near {cue!r}: {excerpt!r}"
        return f" Response text began: {text[:160]!r}"

    def expect_sign_in_refused(self, attempt: Callable[[Check], object]) -> None:
        """
        A deliberately wrong password must be REFUSED.

        Without this a smoke test cannot tell a working login from one that
        accepts anything, or from a success signal we have misread. ``attempt``
        performs the sign-in with a bad password on a FRESH session.

        The test is the same one used positively — can this session reach the
        declared signed-in page? — because weaker signals lie. Looking for a
        session cookie does NOT work: apps set one on the login page itself,
        before anyone has authenticated, so every attempt looks successful.
        """
        path, marker = self._require_auth_page()
        fresh = Check(self.host, self.port)
        fresh.current_step = self.current_step
        fresh.signed_in_looks_like(path, marker)
        try:
            try:
                attempt(fresh)
            except CheckError:
                return  # refused before it could even post — still a refusal
            reached, _ = fresh._reaches_authenticated_page()
            if reached:
                msg = (
                    f"a WRONG password reached {path} as a signed-in user, so "
                    f"the sign-in check proves nothing about the real credential"
                )
                raise CheckError(msg)
        finally:
            fresh.close()

    def close(self) -> None:
        self.client.close()


def run(check_fn: Callable[[Check], None]) -> None:
    """
    Entry point every ``check.py`` ends with: ``run(check)``.

    Parses the harness's ``<host> <port>`` arguments, runs the check, and maps
    the outcome to an exit code — 0 pass, 1 fail — printing an explanation the
    operator can act on without reading the script.
    """
    if len(sys.argv) < 2:
        print("usage: check.py <hostname> [port]", file=sys.stderr)
        sys.exit(2)

    host = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 443

    check = Check(host, port)
    print(f"check: {host} (via {check.base_url})", flush=True)
    try:
        check_fn(check)
    except BrowserRequired as e:
        # Exit 0: nothing failed. The marker line is what the harness keys on,
        # so this can never be silently read as a full pass.
        print(f"\n{BROWSER_REQUIRED_MARKER}: {e}", flush=True)
        sys.exit(0)
    except CheckError as e:
        print(f"\nFAILED during '{check.current_step}': {e}", file=sys.stderr)
        sys.exit(1)
    except Exception:
        # An unexpected error is a failure, never a pass; show the traceback so
        # a broken check is distinguishable from a broken app.
        print(f"\nERROR during '{check.current_step}':", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
    finally:
        check.close()

    print("OK", flush=True)
    sys.exit(0)
