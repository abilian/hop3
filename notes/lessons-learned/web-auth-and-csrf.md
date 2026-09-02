# Lessons Learned: Web Auth, CSRF & Cookie Secrets

**Updated**: 2026-06-25 - from the hop3-testlab "can't log in / `CSRF token verification failed`" investigation.

Cookie-based CSRF and session auth (Litestar's CSRF middleware, used by **hop3-testlab**) has two sharp edges that combine into a permanent, self-inflicted lockout. Both are platform bugs.

> **Scope.** This is about hop3-testlab. **hop3-server has no CSRF middleware and never has** — see [security-model.md §3.7](../security/security-model.md). Its posture rests on `samesite=lax` plus the invariant that every state-changing route is a POST, which `tests/b_integration/server/test_auth_transport_and_logout.py::test_no_mutating_get_routes_remain` enforces by walking the route map. A double-submit token for hop3-server is tracked there as a separate hardening item. Don't read the lockout below as describing hop3-server.

## Don't derive the CSRF/session secret from a rotatable credential

hop3-testlab's `SECRET_KEY` falls back to a value derived from `TESTLAB_PASSWORD` (`config.py`): convenient - CSRF works out of the box with no extra config - but it couples two things that should be independent. Rotating the admin password silently rotates the CSRF/session secret. Every session cookie and every CSRF token minted under the old password instantly becomes invalid. For a single-admin app, "you changed the password, please log in again" is acceptable for *sessions* - but for CSRF it's worse than that (next section).

Pin an explicit secret in production so the two are decoupled:

```bash
hop3 env set --app <app> TESTLAB_SECRET_KEY="$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')"
```

After that, a password change never touches the CSRF/session secret. A derived-from-a-mutable-thing default is a trap; make the stable, explicit secret the documented prod path.

## A cookie-reuse CSRF middleware turns a stale token into a *permanent* 403

Litestar's token is `random + HMAC(token, secret)`, and verification re-checks the HMAC **under the current secret** (`litestar/middleware/csrf.py`). The trap is on safe requests:

```python
# safe (GET) branch - reuses an existing cookie, only mints one when ABSENT
token = connection_state.csrf_token = csrf_cookie or generate_csrf_token(secret=...)
# and the Set-Cookie is only emitted when csrf_cookie is None
```

So a browser holding a `csrftoken` cookie minted under the **old** secret never recovers by reloading the login page. The middleware **reuses** the stale cookie, the page renders a token equal to that stale cookie, and the POST fails the HMAC under the **new** secret, every single time. The only client-side cure is *deleting* the cookie (a brand-new incognito window, or DevTools → Cookies → delete `csrftoken`). "Clear your cache / hard refresh" does **not** work, because the cookie is what's wedged, and a GET won't replace it.

This is why a fresh `curl` (empty cookie jar → mints a valid token under the current secret) succeeds while the user's browser stays stuck - a discrepancy that's baffling until you read the middleware.

## The fix: self-heal on failure, and never show raw JSON

A CSRF failure should not dead-end. Handle the exception so it (a) **expires the wedged cookie** and (b) **redirects to a fresh login** - the next GET then mints a valid token and the retry just works:

```python
def _handle_csrf(_request, _exc) -> Redirect:
    return Redirect(
        path="/auth/login?retry=1",
        status_code=HTTP_303_SEE_OTHER,
        cookies=[Cookie(key="csrftoken", value="", max_age=0, path="/")],  # break the loop
    )
# registered as exception_handlers={PermissionDeniedException: _handle_csrf}
```

Clearing the cookie is the essential step - without it the redirect just loops. Two general rules fall out:

- **A framework default 403/JSON in front of a human is a UX bug.** A browser hitting CSRF/auth failure must get HTML (a redirect to login with a notice). Register exception handlers for the auth/permission exceptions.
- **Verify the handler actually catches the *middleware-raised* exception.** CSRF is raised in middleware, outside the route handler; whether app-level `exception_handlers` catch it depends on middleware order. Don't assume - assert it in a test (POST with a bad token → expect the redirect).

## Read the framework source directly

The first explanation offered ("stale browser state, clear cookies") was only half-right and couldn't explain *why a hard refresh still failed* while a fresh incognito window worked. Reading the ~40 lines of dispatch in `litestar/middleware/csrf.py` settled it in one pass: the cookie-reuse on GET + HMAC-under-current-secret is the whole story. For a "this should work but doesn't" auth bug, read the middleware - it's short and authoritative.

---

*The sections below come from the August 2026 remediation round (see `notes/security/`).*

## A rate limit belongs to the operation, not to the entry point

The web login form had been capped at 5 attempts per IP per minute since 0.5. The same password check was also reachable through `hop3 auth get-token` over JSON-RPC, which applied no limit at all - so an attacker who chose the second door could guess roughly a hundred times faster, and the mitigation on the first door bought nothing.

Two things follow, and the second is the subtler one:

- **Enumerate every path that reaches a sensitive operation before believing it is protected.** "The login form is throttled" was true and irrelevant. Password verification was the asset; the form was one of its two callers.
- **Share the limiter *instance*, not the configuration.** Giving the RPC path its own `RateLimiter(5, 60)` would look identical in review and would *double* the real ceiling, because an attacker alternating between the two doors draws from two budgets. One module-level instance, imported by both callers, is the control. A comment saying so belongs next to it, because the next person to add a third caller will otherwise construct a third limiter.

## Make the three login failures indistinguishable, including in time

A login can fail because the username does not exist, because the account is disabled, or because the password is wrong. Ours answered differently in all three cases: disabled accounts got their own message, and unknown usernames answered *faster*, because a real user's stored hash was verified with bcrypt while an unknown one returned before any hashing happened. The timing difference alone is a usable account oracle (CWE-204), and bcrypt's cost is exactly what makes it measurable.

The fix has two halves and both are needed: one identical error string for all three, and a **deliberate dummy bcrypt verification** on the paths that would otherwise return early, so the response time does not encode the answer.

```python
_DUMMY_PASSWORD_HASH = bcrypt_lib.hashpw(b"...placeholder", bcrypt_lib.gensalt())

def burn_password_check(password: str) -> None:
    """Spend the same bcrypt time a real verification would."""
    bcrypt_lib.checkpw(password.encode("utf-8"), _DUMMY_PASSWORD_HASH)
```

The regression test asserts the *responses are equal*. The formulation fails when someone later adds a helpful "this account is disabled" message.

## A `Secure` cookie over plain HTTP is a silent infinite loop

Sign-in over plain HTTP looped back to the login form forever, with no error anywhere. The session cookie is `Secure`, so the browser accepted the redirect and discarded the cookie, and the next request arrived unauthenticated. Every component behaved correctly and the sum was unusable.

The user-visible symptom is indistinguishable from a wrong password, so it sends you to look at credentials. Detect the condition up front and refuse with an explanation. Development over HTTP stays possible behind an explicit debug flag.

This is the same shape as the app-level failures in [`verifying-an-app-works.md`](./verifying-an-app-works.md): a transport-level fault reported as an authentication error.

## If you have no CSRF tokens, "every mutation is a POST" carries the whole defence

Hop3 ships no CSRF middleware on the dashboard. What stands in for it is `samesite=lax` plus the invariant that every state-changing route is a POST: `lax` withholds the cookie on a cross-site POST but *sends* it on a cross-site GET, so a single state-changing GET falsifies the whole argument.

`GET /auth/logout` was exactly that exception, and it survived from May to August 2026 because the invariant was documented; nothing enforced it.

**A documented invariant carries no force.** The repair is converting the route and writing the check that fails when the next one appears. Three came out of this round, and the shape generalises:

| Invariant | Enforcement |
|---|---|
| No cookie-authenticated route changes state on a GET | Route-map test listing every GET the app serves; a new route fails until someone declares it a read |
| No credential reaches a subprocess through argv | Repo-wide scan of `packages/*/src` for the interpolation patterns (`-p{`, `--password=`, …) |
| Every pre-auth command is rate limited | Test over the command registry: a command with `requires_auth=False` must set `rate_limited` or be explicitly exempted |

These three tests share two properties. Each **fails closed on new code** - the route test breaks the moment a route is added, before any human review. And each was **verified against a planted regression** before being trusted, because a scan that matches nothing looks exactly like a scan that passes. The rate-limit test found a real gap on its first run.
