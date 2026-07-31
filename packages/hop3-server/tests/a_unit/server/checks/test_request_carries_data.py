# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
A form POST from a check must actually carry the form.

Regression, and an expensive one. `Check._request` was given an explicit
`data` parameter while tightening its type annotations. Naming a parameter in
the signature takes it *out* of `**kwargs`, and the call underneath still
forwarded only `**kwargs` — so every form sign-in POSTed an **empty body**. The
credentials never left the process.

Eighteen of the twenty catalog applications failed their smoke test at once.
The two that passed were the two that do not post a form: Radicale (HTTP Basic)
and Vikunja (a JSON API, whose payload rides in `json=` and so stayed in
`**kwargs`). Nothing about the applications had changed.

It was invisible for a day because the CLI exited 0 on a reported failure, so
the runs went on printing PASS. Two defects, one in the checking library and one
in the tool reading it, and each hid the other.

The assertion is therefore about the bytes on the wire, not about the call
signature: what makes this test worth having is that it fails if the payload
stops arriving, whatever the reason.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

from hop3.server.checks._helper import (
    BrowserRequired,
    Check,
    CheckError,
    LoopbackTransport,
)


@pytest.fixture
def check(monkeypatch) -> Check:
    monkeypatch.setenv("HOP3_ADMIN_USER", "admin")
    monkeypatch.setenv("HOP3_ADMIN_PASSWORD", "s3cret")
    monkeypatch.delenv("HOP3_PROBE_PASSWORD", raising=False)
    return Check("app.example.com", 443)


class Wire:
    """
    The socket layer, stubbed ONE LEVEL BELOW ``LoopbackTransport``.

    This file used to swap ``check.client`` for a ``MockTransport`` client,
    which removed ``LoopbackTransport`` — the class most of these tests are
    about — from every one of them. The transport then shipped a defect that
    lost the session cookie of every application that has one, with this file
    green, including a test named for that exact cookie.

    Stubbing ``httpx.HTTPTransport.handle_request`` instead keeps the real
    client and the real transport, and replaces only the socket. The assertions
    are then about what would go on the wire, which is the only thing worth
    pinning.
    """

    def __init__(self) -> None:
        self.seen: list[httpx.Request] = []
        #: The URL at the moment of the send. The transport rewrites it to
        #: loopback and restores it afterwards, so the live request no longer
        #: carries it — capture it here or it cannot be asserted on.
        self.dialled: list[httpx.URL] = []
        self.respond: Callable[[httpx.Request], httpx.Response] = _ok

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        self.dialled.append(request.url)
        return self.respond(request)


def _ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, text="ok")


@pytest.fixture
def wire(monkeypatch) -> Wire:
    """Record what reaches the socket, without opening one."""
    recorder = Wire()
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", recorder.handle_request)
    return recorder


def test_a_form_post_sends_its_fields(check: Check, wire: Wire) -> None:
    """The defect: this body was empty."""
    check.post("/login", {"username": "admin", "password": "s3cret"})

    assert len(wire.seen) == 1
    body = wire.seen[0].content.decode()
    assert "username=admin" in body, f"form fields missing from the body: {body!r}"
    assert "password=s3cret" in body
    assert (
        wire
        .seen[0]
        .headers["content-type"]
        .startswith("application/x-www-form-urlencoded")
    )


def test_a_post_with_no_data_still_works(check: Check, wire: Wire) -> None:
    """Some sign-ins carry everything in the URL or a header."""
    check.post("/login")

    assert len(wire.seen) == 1
    assert wire.seen[0].content == b""


def test_extra_options_survive_alongside_the_form(check: Check, wire: Wire) -> None:
    """A check may send headers with its form; neither may displace the other."""
    check.post("/login", {"user": "a"}, headers={"X-Requested-With": "XMLHttpRequest"})

    assert "user=a" in wire.seen[0].content.decode()
    assert wire.seen[0].headers["X-Requested-With"] == "XMLHttpRequest"


def test_the_sni_hostname_is_still_set(check: Check, wire: Wire) -> None:
    """
    The vhost is selected by SNI, not the Host header.

    Over TLS nginx picks the certificate — and so the server block — from the
    SNI name. The URL says 127.0.0.1 by the time it reaches the socket, so
    without this every check would land on the platform's default vhost and get
    a 404 for an application that is running perfectly.
    """
    check.get("/")

    assert wire.seen[0].extensions.get("sni_hostname") == "app.example.com"


def test_a_failed_sign_in_reports_what_the_post_returned(
    check: Check, wire: Wire
) -> None:
    """
    The session assertion must say what the SIGN-IN did, not only what came after.

    `expect_signed_in` proves a session by fetching a protected page — the right
    assertion, but on failure it could only describe that later GET. A CSRF
    rejection (403), a re-rendered form (200) and a redirect back to the login
    page all produced the same message, so diagnosing bugsink and dolibarr meant
    guessing between them.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(403, text="CSRF verification failed")
        return httpx.Response(200, text="<html>login form</html>")

    wire.respond = handler
    check.signed_in_looks_like("/", contains="/logout")

    check.post("/accounts/login/", {"username": "admin", "password": "s3cret"})
    with pytest.raises(CheckError) as excinfo:
        check.expect_signed_in()

    message = str(excinfo.value)
    assert "'/accounts/login/'" in message, "the sign-in path must be named"
    assert "403" in message, "the sign-in POST's status must be reported"
    assert "CSRF" in message, "a 403 should hint at the usual cause"


class TestFormToken:
    """
    Hidden-input extraction, independent of attribute order.

    Four applications failed their check because the shared idiom
    `name="X"\\s+value="..."` demands `name` immediately before `value`. Their
    sign-in pages rendered correctly and carried the token; the pattern could
    not see it. Each case below is markup a real application emits.
    """

    def test_name_then_value(self, check: Check) -> None:
        html = '<input type="hidden" name="_csrf" value="abc123">'
        assert check.form_token(html, "_csrf") == "abc123"

    def test_value_then_name(self, check: Check) -> None:
        """Attribute order is not guaranteed by anything."""
        html = '<input type="hidden" value="abc123" name="_csrf">'
        assert check.form_token(html, "_csrf") == "abc123"

    def test_an_attribute_in_between(self, check: Check) -> None:
        html = '<input name="_csrf" id="csrf-token" value="abc123">'
        assert check.form_token(html, "_csrf") == "abc123"

    def test_single_quotes(self, check: Check) -> None:
        html = "<input name='YII_CSRF_TOKEN' value='abc123'>"
        assert check.form_token(html, "YII_CSRF_TOKEN") == "abc123"

    def test_the_right_input_among_several(self, check: Check) -> None:
        html = (
            '<input name="username" value="admin">'
            '<input name="_c" value="the-token">'
            '<input name="password" value="">'
        )
        assert check.form_token(html, "_c") == "the-token"

    def test_a_response_works_as_well_as_a_string(self, check: Check) -> None:
        response = httpx.Response(200, text='<input name="t" value="v">')
        assert check.form_token(response, "t") == "v"

    def test_a_missing_token_fails_with_the_page(self, check: Check) -> None:
        with pytest.raises(CheckError) as excinfo:
            check.form_token("<html>install wizard</html>", "_csrf")
        assert "install wizard" in str(excinfo.value)


def test_a_form_post_sends_a_referer(check: Check, wire: Wire) -> None:
    """
    Django rejects a secure POST with no Referer, which reads as a bad token.

    bugsink's sign-in returned 403 for exactly this reason: httpx sends no
    Referer, so fetching a form and posting it back looked like a cross-site
    request.
    """
    check.get("/accounts/login/")
    check.post("/accounts/login/", {"username": "admin"})

    assert wire.seen[-1].headers["Referer"] == (
        "https://app.example.com/accounts/login/"
    ), "the POST must name the page the form came from"


def test_an_explicit_referer_is_not_overridden(check: Check, wire: Wire) -> None:
    """A check that knows better keeps control."""
    check.post("/login", {"a": "b"}, headers={"Referer": "https://elsewhere/"})

    assert wire.seen[-1].headers["Referer"] == "https://elsewhere/"


class TestFormFields:
    """
    Resubmitting the whole form, as a browser does.

    dolibarr's sign-in POST returned 200 with the login page rendered again —
    the signature of a form the application considered incomplete rather than a
    rejected password. Its form carries an action discriminator the check never
    sent, because the check hand-listed three fields.
    """

    def test_hidden_fields_are_collected(self, check: Check) -> None:
        html = (
            '<input type="hidden" name="token" value="abc">'
            '<input type="hidden" name="actionlogin" value="login">'
            '<input type="text" name="username" value="">'
            '<input type="password" name="password" value="">'
        )
        assert check.form_fields(html) == {"token": "abc", "actionlogin": "login"}

    def test_visible_inputs_are_left_out(self, check: Check) -> None:
        """Copying a rendered empty value back would overwrite the credential."""
        html = '<input type="text" name="username" value="">'
        assert check.form_fields(html) == {}

    def test_credentials_merge_over_the_hidden_fields(self, check: Check) -> None:
        html = '<input type="hidden" name="token" value="abc">'
        form = check.form_fields(html) | {"username": "admin", "password": "s3cret"}
        assert form == {"token": "abc", "username": "admin", "password": "s3cret"}

    def test_a_page_with_no_hidden_fields_is_empty_not_an_error(
        self, check: Check
    ) -> None:
        assert check.form_fields("<html>nothing here</html>") == {}


class TestTokenNotInTheForm:
    """
    Applications that carry the CSRF token outside the form.

    Verified on a live Forgejo: its sign-in page contains no `_csrf` input —
    `grep -c _csrf` returns 0 both through the check's transport and through a
    browser's. Forgejo and Gitea set a cookie of that name and require the
    submitted field to equal it.
    """

    def test_the_cookie_is_used_when_the_form_has_no_input(self, check: Check) -> None:
        check.client.cookies.set("_csrf", "from-the-cookie")
        html = '<input type="text" name="user_name"><input type="password" name="password">'

        assert check.form_token(html, "_csrf") == "from-the-cookie"

    def test_a_form_input_still_wins_over_a_cookie(self, check: Check) -> None:
        """The rendered form is the more specific answer where it exists."""
        check.client.cookies.set("_csrf", "from-the-cookie")
        html = '<input type="hidden" name="_csrf" value="from-the-form">'

        assert check.form_token(html, "_csrf") == "from-the-form"

    def test_a_meta_tag_is_used_as_a_last_resort(self, check: Check) -> None:
        html = '<meta name="csrf-token" content="from-the-meta">'

        assert check.form_token(html, "csrf-token") == "from-the-meta"

    def test_the_failure_lists_what_the_page_did_contain(self, check: Check) -> None:
        """'Not found' alone sends the reader to fetch the page by hand."""
        html = '<input type="text" name="user_name"><input type="password" name="pwd">'

        with pytest.raises(CheckError) as excinfo:
            check.form_token(html, "_csrf")

        message = str(excinfo.value)
        assert "user_name" in message
        assert "pwd" in message


def test_a_re_rendered_form_reports_its_error_text(check: Check, wire: Wire) -> None:
    """
    A login POST answered with 200 carries the reason; report it.

    limesurvey and matomo both failed this way, and the message described only
    a later GET — so the application's own explanation, which was sitting in the
    POST response, never reached the operator.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                200,
                text="<html><div class='alert'>Wrong username or password</div></html>",
            )
        return httpx.Response(200, text="<html>login</html>")

    wire.respond = handler
    check.signed_in_looks_like("/", contains="/logout")
    check.post("/login", {"user": "admin", "password": "nope"})

    with pytest.raises(CheckError) as excinfo:
        check.expect_signed_in()

    assert "Wrong username or password" in str(excinfo.value)


def test_requires_browser_is_neither_a_pass_nor_a_failure(check: Check) -> None:
    """
    An app whose sign-in needs JavaScript must not report a full pass.

    LimeSurvey answers a form POST with its "JavaScript deactivated" notice and
    Easy!Appointments serves a page with no inputs at all, so no HTTP sign-in
    exists to make. The check verifies what it can and defers the sign-in — but
    it must SAY so, or a weaker claim is filed as the strong one.
    """
    with pytest.raises(BrowserRequired) as excinfo:
        check.requires_browser("its admin UI is rendered by JavaScript")

    assert "JavaScript" in str(excinfo.value)


class TestCookieScoping:
    """
    A domain-scoped session cookie must survive the loopback transport.

    The check runs on the server and reaches apps over 127.0.0.1. Expressing
    that as "connect to localhost, override the Host header" silently broke
    every application that scopes its session cookie to its own domain: httpx
    stores cookies against the host in the request URL, so a client that
    believes it is talking to `localhost` DISCARDS `Domain=app.example.com`.

    Matomo showed the shape: its sign-in POST returned 302 — the credentials
    were accepted — and every request afterwards was anonymous, which reads
    exactly like a refused password. Applications whose cookies carry no
    `Domain` were unaffected, so it looked app-specific for a long time.
    """

    def test_a_domain_scoped_cookie_is_kept_and_resent(
        self, check: Check, wire: Wire
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/login":
                return httpx.Response(
                    200,
                    headers={
                        "set-cookie": (
                            f"session=abc; Domain={check.host}; Path=/; Secure"
                        )
                    },
                )
            return httpx.Response(200, text="ok")

        wire.respond = handler

        check.post("/login", {"u": "a"})
        assert dict(check.client.cookies) == {"session": "abc"}, (
            "the app's session cookie was discarded"
        )

        check.get("/dashboard")
        assert wire.seen[-1].headers.get("cookie") == "session=abc", (
            "the session was not carried into the next request"
        )

    def test_a_host_only_cookie_survives_too(self, check: Check, wire: Wire) -> None:
        """
        The regression the domain-scoped fix caused, and the reason for both.

        Rewriting `request.url` and leaving it rewritten put every cookie in the
        jar under `127.0.0.1` — including the plain ones that had always worked
        — while outgoing headers were still built against the real hostname. So
        nothing was ever sent back, and eleven applications went from passing to
        "the sign-in did not establish a session" in one run.
        """

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/login":
                return httpx.Response(200, headers={"set-cookie": "sess=abc; Path=/"})
            return httpx.Response(200, text="ok")

        wire.respond = handler

        check.post("/login", {"u": "a"})
        check.get("/dashboard")

        assert wire.seen[-1].headers.get("cookie") == "sess=abc", (
            "a cookie with no Domain must be stored against the app's hostname"
        )


def _dial(wire: Wire, url: str, *, port: int = 443) -> tuple[httpx.Request, httpx.URL]:
    """
    Send one request through the REAL transport; report what the socket saw.

    Returns the request as it looks afterwards, and the URL as it looked at the
    moment of the send — the two differ, and the difference is the contract.
    Only the socket beneath the transport is stubbed, so a change to
    `handle_request` is a change to what these tests observe. Rebuilding its
    body in the test instead is what let the URL-restore defect through.
    """
    request = httpx.Request("GET", url)
    LoopbackTransport("app.example.com", port).handle_request(request)
    return request, wire.dialled[0]


def test_the_transport_connects_to_loopback_but_names_the_app(wire: Wire) -> None:
    """
    The socket goes to 127.0.0.1; the vhost is still selected by the app's name.

    Both halves matter: without the rewrite the check would need DNS and egress,
    and without Host/SNI it would land on the platform's default vhost.
    """
    request, dialled = _dial(wire, "https://app.example.com/dashboard")

    assert dialled.host == "127.0.0.1", "the socket must not need DNS"
    assert request.headers["Host"] == "app.example.com"
    assert request.extensions["sni_hostname"] == "app.example.com"


def test_the_request_keeps_its_real_url_after_the_transport_runs(wire: Wire) -> None:
    """
    The rewrite is for the socket only — httpx scopes cookies off this URL.

    `Client._send_single_request` sets `response.request = request` and THEN
    calls `cookies.extract_cookies(response)`, which reads `request.url`. A
    transport that leaves loopback in place therefore files every cookie under
    127.0.0.1 and never sends one back. This is the assertion that fails if the
    restore is ever removed again.
    """
    request, dialled = _dial(wire, "https://app.example.com/dashboard")

    assert dialled.host == "127.0.0.1"
    assert request.url.host == "app.example.com", (
        "the cookie jar reads this URL after the transport returns"
    )
    assert str(request.url) == "https://app.example.com/dashboard"


class TestLoopbackPort:
    """
    The rewritten port must follow the scheme.

    Forcing the TLS port onto every request broke the moment an app redirected
    to an `http://` URL of itself: nginx answered "400 The plain HTTP request
    was sent to HTTPS port". Paheko hit exactly that following its post-login
    redirect, and the check reported it as a failed sign-in.
    """

    @staticmethod
    def _effective_port(wire: Wire, url: str, *, port: int = 443) -> int:
        # httpx normalises a default port to None, so ask for the effective one.
        _, dialled = _dial(wire, url, port=port)
        return dialled.port or (443 if dialled.scheme == "https" else 80)

    def test_https_goes_to_the_tls_port(self, wire: Wire) -> None:
        assert self._effective_port(wire, "https://app.example.com/x") == 443

    def test_http_does_not_go_to_the_tls_port(self, wire: Wire) -> None:
        assert self._effective_port(wire, "http://app.example.com/x") == 80, (
            "a plain-HTTP request sent to 443 is answered with nginx's 400"
        )

    def test_a_non_default_tls_port_is_honoured(self, wire: Wire) -> None:
        """The observable case: the transport's port is used, not a constant."""
        assert (
            self._effective_port(wire, "https://app.example.com/x", port=8443) == 8443
        )


class TestFormAction:
    """Where a form posts, read from the page rather than guessed."""

    def test_an_explicit_action_is_used(self, check: Check) -> None:
        html = '<form action="/login" method="post"><input name="password"></form>'
        assert check.form_action(html, default="/admin/") == "/login"

    def test_an_empty_action_means_this_page(self, check: Check) -> None:
        html = '<form action="" method="post"></form>'
        assert check.form_action(html, default="/admin/") == "/admin/"

    def test_no_form_falls_back_to_the_default(self, check: Check) -> None:
        assert check.form_action("<html>nothing</html>", default="/x") == "/x"

    def test_attribute_order_does_not_matter(self, check: Check) -> None:
        html = "<form method='post' action='/login'></form>"
        assert check.form_action(html, default="/") == "/login"


class TestCookieDiagnostic:
    """
    A failed session assertion must say whether any cookies were kept.

    "The app refused the credential" and "the app accepted it and we lost the
    session" look identical in the response, and need completely different
    fixes. This distinguished them in one line — matomo and wordpress both
    turned out to be the second kind.
    """

    def test_an_empty_jar_is_called_out(self, check: Check, wire: Wire) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="<html>login</html>")

        wire.respond = handler
        check.signed_in_looks_like("/", contains="/logout")

        with pytest.raises(CheckError) as excinfo:
            check.expect_signed_in()

        assert "NO cookies" in str(excinfo.value)

    def test_held_cookies_are_named(self, check: Check, wire: Wire) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="<html>login</html>")

        wire.respond = handler
        check.client.cookies.set("session", "abc")
        check.signed_in_looks_like("/", contains="/logout")

        with pytest.raises(CheckError) as excinfo:
            check.expect_signed_in()

        assert "'session'" in str(excinfo.value)


class TestSubmitControlIsPosted:
    """
    A browser sends the button it clicked, and some frameworks route on nothing else.

    Paheko's handler is `$form->runIf('login', ...)`: with no `login` key in the
    body it never runs. The page then came back 200 with the submitted email
    echoed into it and no error anywhere — and a correct password, a wrong
    password and a deliberately OMITTED CSRF token produced identical responses,
    which is the signature of a form that was never processed rather than one
    that was rejected.
    """

    def test_a_named_submit_button_is_sent(self, check: Check) -> None:
        html = (
            '<input type="hidden" name="token" value="abc">'
            '<button type="submit" name="login" value="1">Se connecter</button>'
        )
        assert check.form_fields(html) == {"token": "abc", "login": "1"}

    def test_a_button_without_a_type_is_a_submit_button(self, check: Check) -> None:
        """Per the HTML spec, and it is how paheko's form is written."""
        html = '<button name="login">Se connecter</button>'
        assert check.form_fields(html) == {"login": ""}

    def test_an_input_type_submit_counts_too(self, check: Check) -> None:
        html = '<input type="submit" name="do_login" value="Sign in">'
        assert check.form_fields(html) == {"do_login": "Sign in"}

    def test_only_the_first_control_is_sent(self, check: Check) -> None:
        """
        A browser sends exactly one — the one clicked.

        Sending them all would submit whatever the form's later buttons do, and
        on a sign-in page those are the ones you least want: cancel, reset the
        password, delete the account.
        """
        html = (
            '<button type="submit" name="login" value="1">Sign in</button>'
            '<button type="submit" name="reset" value="1">Reset my password</button>'
        )
        assert check.form_fields(html) == {"login": "1"}

    def test_an_unnamed_button_sends_nothing(self, check: Check) -> None:
        """A control with no name contributes no key, exactly as in a browser."""
        html = (
            '<input type="hidden" name="t" value="1"><button type="submit">Go</button>'
        )
        assert check.form_fields(html) == {"t": "1"}

    def test_a_hidden_field_wins_over_a_button_of_the_same_name(
        self, check: Check
    ) -> None:
        """The form's own value is authoritative; the button only fills a gap."""
        html = (
            '<input type="hidden" name="login" value="from-the-form">'
            '<button type="submit" name="login" value="from-the-button">Go</button>'
        )
        assert check.form_fields(html) == {"login": "from-the-form"}
