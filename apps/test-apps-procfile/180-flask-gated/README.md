# flask-gated — the access gate on a real server

A Flask app behind `[access] require = "auth"` (ADR 062), with `/public/.*` left open. Each page prints the `X-Hop3-User` the proxy passed on.

`check.py` goes through the server's own proxy, which is where the gate is:

- an anonymous request is redirected to `https://<admin-domain>/auth/login`, with `next` pointing back at the app, a `state` parameter, and the `__Host-hop3_state` cookie that binds the sign-in to one browser;
- the admin domain serves the sign-in form;
- `/public/ping` is served, and an `X-Hop3-User` header the client forges never reaches the app;
- the same forged header does not get a request past the gate.

The gate refuses to deploy on a server with no admin domain, so the harness leaves this test out on one and says so. A server addressed by a hostname gets that hostname as its admin domain; one addressed by IP needs `--admin-domain`. The Docker target has none: the gate's Docker coverage is `c_e2e/test_gate.py`, on nginx, Caddy and Traefik.
