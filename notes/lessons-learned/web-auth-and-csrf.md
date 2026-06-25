# Lessons Learned: Web Auth, CSRF & Cookie Secrets

**Updated**: 2026-06-25 — from the hop3-testlab "can't log in / `CSRF token verification failed`" investigation.

Cookie-based CSRF and session auth (Litestar's CSRF middleware, used by both hop3-testlab and hop3-server) has two sharp edges that combine into a permanent, self-inflicted lockout. Both are platform bugs, not user error.

## Don't derive the CSRF/session secret from a rotatable credential

hop3-testlab's `SECRET_KEY` falls back to a value derived from `TESTLAB_PASSWORD` (`config.py`): convenient — CSRF works out of the box with no extra config — but it couples two things that should be independent. **Rotating the admin password silently rotates the CSRF/session secret.** Every session cookie and every CSRF token minted under the old password instantly becomes invalid. For a single-admin app, "you changed the password, please log in again" is acceptable for *sessions* — but for CSRF it's worse than that (next section).

Pin an explicit secret in production so the two are decoupled:

```bash
hop3 env set --app <app> TESTLAB_SECRET_KEY="$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')"
```

After that, a password change never touches the CSRF/session secret. A derived-from-a-mutable-thing default is a trap; make the stable, explicit secret the documented prod path.

## A cookie-reuse CSRF middleware turns a stale token into a *permanent* 403

Litestar's token is `random + HMAC(token, secret)`, and verification re-checks the HMAC **under the current secret** (`litestar/middleware/csrf.py`). The trap is on safe requests:

```python
# safe (GET) branch — reuses an existing cookie, only mints one when ABSENT
token = connection_state.csrf_token = csrf_cookie or generate_csrf_token(secret=...)
# and the Set-Cookie is only emitted when csrf_cookie is None
```

So a browser holding a `csrftoken` cookie minted under the **old** secret never recovers by reloading the login page: the middleware **reuses** the stale cookie instead of regenerating it, the page renders a token equal to that stale cookie, and the POST fails the HMAC under the **new** secret — every single time. The only client-side cure is *deleting* the cookie (a brand-new incognito window, or DevTools → Cookies → delete `csrftoken`). "Clear your cache / hard refresh" does **not** work, because the cookie is what's wedged, and a GET won't replace it.

This is why a fresh `curl` (empty cookie jar → mints a valid token under the current secret) succeeds while the user's browser stays stuck — a discrepancy that's baffling until you read the middleware.

## The fix: self-heal on failure, and never show raw JSON

A CSRF failure should not dead-end. Handle the exception so it (a) **expires the wedged cookie** and (b) **redirects to a fresh login** — the next GET then mints a valid token and the retry just works:

```python
def _handle_csrf(_request, _exc) -> Redirect:
    return Redirect(
        path="/auth/login?retry=1",
        status_code=HTTP_303_SEE_OTHER,
        cookies=[Cookie(key="csrftoken", value="", max_age=0, path="/")],  # break the loop
    )
# registered as exception_handlers={PermissionDeniedException: _handle_csrf}
```

Clearing the cookie is the load-bearing part — without it the redirect just loops. Two general rules fall out:

- **A framework default 403/JSON in front of a human is a UX bug.** A browser hitting CSRF/auth failure must get HTML (a redirect to login with a notice), never a raw `{"status_code":403,...}` blob. Register exception handlers for the auth/permission exceptions.
- **Verify the handler actually catches the *middleware-raised* exception.** CSRF is raised in middleware, not the route handler; whether app-level `exception_handlers` catch it depends on middleware order. Don't assume — assert it in a test (POST with a bad token → expect the redirect, not 403).

## Verify against the framework source, not your memory of it

The first explanation offered ("stale browser state, clear cookies") was only half-right and couldn't explain *why incognito still failed*. Reading the ~40 lines of `litestar/middleware/csrf.py` settled it in one pass: the cookie-reuse on GET + HMAC-under-current-secret is the whole story. For a "this should work but doesn't" auth bug, read the middleware — it's short, and it's authoritative in a way that reasoning from memory is not.
