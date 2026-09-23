# ADR 062: Authenticated Access Gate

- **Status**: Proposed
- **Type**: Feature
- **Created**: 2026-09-22
- **Related-ADRs**: [050](./050-waf-l7-lewaf.md) (WAF; this ADR replaces its deferred `auth` gate condition), [061](./061-standard-roles-and-rpc-authorization.md) (the roles a gate admits), [021](./021-proxy-plugin-system.md) (proxy plugins), [014](./014-authentication-bootstrap.md) (authentication bootstrap)

## Context

An app is reachable from the internet the moment it deploys. That is right for an application with accounts of its own. It is wrong for a large class of what people actually deploy: notebooks, coding agents, remote desktops, internal dashboards, generated tools, staging copies. None of these has a login. Several hand a shell to whoever reaches them.

The only access control Hop3 offers today is the WAF gate ([ADR 050](./050-waf-l7-lewaf.md) §2), which admits a request by its source network. That covers a LAN or a VPN. It does not cover the common case, "the people I choose, from anywhere". The safe way to deploy a login-less app has been not to deploy it. ADR 050 reserved `require = "auth"` for this and made it a validation error until forward-auth existed.

Two properties of the platform shape the design:

- **The Hop3 session cookie is host-only on the admin domain**, while an app's hostname is arbitrary. A browser never sends the admin cookie to an app. Widening it with a `Domain` attribute would reach only subdomains of the admin domain while handing a full control-plane credential to every app backend on them.
- **Hop3 supports three reverse proxies** (nginx, Caddy, Traefik). Each has a native forward-auth primitive: `auth_request`, `forward_auth` and `ForwardAuth`. All three consult an HTTP endpoint before proxying and act on its status code.

## Decision

### 1. `[access]` in `hop3.toml`

```toml
[access]
require = "auth"                         # "auth" | "none" (default)
role = "member"                          # minimum standard role; default "member"
public-paths = ["/webhook", "/api/public/.*"]
```

- `require = "auth"` puts the whole app behind a Hop3 sign-in. `"none"` is the default today and the explicit opt-out once a server-level default exists (§8).
- `role` is the minimum standard role ([ADR 061](./061-standard-roles-and-rpc-authorization.md) §1) the gate admits. The default, `member`, admits any active account.
- `public-paths` are Python regexes full-matched against the normalized path, the same grammar and normalization as ADR 050 §2. They are reachable anonymously. A health check path an external monitor calls belongs here.

`[access]` is the only way to express authentication-based access. ADR 050's gate keeps its one condition, a named network, and `[[waf.gate]] require = "auth"` is refused with a message pointing at `[access]`. The two are different mechanisms and compose: a network gate is a per-path source-address rule evaluated by the WAF; the access gate is an app-wide identity check evaluated by the proxy before the WAF sees the request.

### 2. One check endpoint, three proxies

hop3-server serves `GET /auth/check` on loopback. The proxy calls it for every request to a gated app outside `public-paths`, passing the original host, path and cookies. The endpoint answers:

- **200** with `X-Hop3-User` and `X-Hop3-Role` when the gate cookie is valid for this app and the user's current role meets the app's minimum;
- **401** when there is no valid gate cookie;
- **403** when the user is signed in and their role is too low.

The proxy passes 200 through to the app, turns 401 into a redirect to the Hop3 sign-in (§3), and returns 403 as a page. WebSocket upgrades go through the same check, because each proxy runs forward-auth before the upgrade.

The role is read from the database on every check, as ADR 061 §3 requires for the control plane. A demoted or disabled account loses access on its next request.

### 3. Signing in: a handshake per app

The gate cannot use the admin cookie (§Context), so each gated app gets its own session through a redirect handshake:

1. An anonymous request to `https://app.example.org/page` gets a 302 to `https://<admin-domain>/auth/login?next=https://app.example.org/page`.
2. The user signs in to Hop3 as usual (password or magic link). If they already hold an admin-domain session, this step is invisible.
3. hop3-server mints a **one-time code**, bound to the app and the user, valid for a minute, and redirects to `https://app.example.org/_hop3/auth/callback?code=…&next=/page`.
4. The proxy routes `/_hop3/auth/*` on every gated vhost to hop3-server, never to the app. The callback redeems the code and sets the **gate cookie** on the app's host, then redirects to `next`.

The gate cookie is `__Host-hop3_gate`: host-only, `Secure`, `HttpOnly`, `SameSite=Lax`, `Path=/`. It is a signed token whose audience is the app, so a cookie minted for one app is rejected by every other. It carries the identifier of the admin-domain session that minted it. Once that session is revoked, the check rejects the cookie. Signing out of Hop3 therefore signs the user out of every app.

**`next` is validated.** The login page accepts a `next` URL only when its host is the admin domain or the hostname of a deployed app with `require = "auth"`, checked against the database. Anything else is dropped; the user lands on the dashboard.

### 4. What reaches the app

- The proxy sets `X-Hop3-User` and `X-Hop3-Role` from the check response, **overwriting** whatever the client sent, on every request including public paths (where they are empty). An app behind the gate can trust them.
- The gate cookie is removed from the `Cookie` header before the request is forwarded. The app never sees a Hop3 credential.
- `/_hop3/auth/*` never reaches the app, so the handshake cannot be intercepted by it.

### 5. Preconditions, refused at deploy

A deploy with `require = "auth"` aborts with a diagnosis when:

- the app has no TLS certificate (the `__Host-` cookie needs HTTPS, as does any gate credential);
- no admin domain is configured (there is nowhere to sign in);
- `role` is not a standard role;
- a `public-paths` entry fails to compile;
- the active proxy plugin does not implement the gate.

### 6. Failure is closed

If hop3-server does not answer the check, the proxy returns an error to the client. It never forwards the request. All three proxies' forward-auth behaves this way natively. The e2e suite checks it on each.

### 7. Proxy plugins

The gate is a capability of the proxy plugin protocol ([ADR 021](./021-proxy-plugin-system.md)): given an app's access policy, emit the forward-auth wiring, the `/_hop3/auth/*` route, the public-path exemptions, the header overwrite and the cookie removal. nginx, Caddy and Traefik each implement it. A deploy aborts when the active plugin lacks this capability, as §5 requires.

### 8. A server-level default, deferred

A `new-apps-private` server setting, making `require = "auth"` the default for apps that declare nothing, is designed-in and not part of this decision. Its opt-out already exists: `require = "none"`. Adding the setting later changes no recipe that states its intent.

## Acceptance

Each proxy gets one e2e test. It deploys a login-less app with `[access] require = "auth"` and checks that:

1. an anonymous request gets a 302 to the Hop3 sign-in;
2. a `member` session completes the handshake and gets the app's own content;
3. with `role = "viewer"`, a `member` gets 403 and a `viewer` gets 200;
4. an anonymous request to a public path gets 200;
5. a client-supplied `X-Hop3-User` never reaches the app;
6. the app never receives the gate cookie;
7. a gate cookie minted for app A is rejected by app B;
8. after signing out of Hop3, the app's gate cookie no longer passes;
9. a `next` pointing at a foreign host is not followed;
10. with hop3-server stopped, the app is not served;
11. a `member` who passes the gate is refused by every mutating RPC command.

## Consequences

### Positive

- A login-less app can be deployed safely, with one section of `hop3.toml` and no change to the app.
- The app learns who is asking through two headers it can trust, which is enough for simple per-user behaviour.
- One sign-in covers every gated app on the server. One sign-out ends them all.
- ADR 050's deferred condition is resolved and its gate keeps a single meaning.

### Negative

- Every request to a gated app costs a round trip to hop3-server, including static assets. The gate's latency and hop3-server's availability become part of every gated app's.
- hop3-server is in the request path of gated apps: if it is down, they are down (§6).
- The handshake adds a reserved path, `/_hop3/`, to every gated vhost. An app that serves that path cannot be gated.

## Alternatives considered

**A parent-domain cookie.** Set the admin cookie with `Domain=<admin-domain>` and let every subdomain app see it. Buys no handshake. Costs the two things that matter: it covers only apps under the admin domain, and it delivers a full control-plane credential to every app backend. Either cost alone rules it out.

**The gate inside the WAF.** Buys one access mechanism. Costs the redirect and cookie exchange, which a request filter cannot perform. It would also tie authentication to enabling the WAF.

**An external identity-aware proxy** (oauth2-proxy, Authelia, Pomerium). Buys a mature implementation. Costs a second account system beside Hop3's, a second service to supervise, and the roles of ADR 061. The choice turns on a need for external identity providers, which this ADR does not address (§Open questions).

## Open questions

1. **Bearer tokens.** Scripts calling a gated API cannot follow a browser redirect. Accepting `Authorization: Bearer` at the gate collides with apps that use that header for their own tokens. A dedicated header, or a per-app gate token, are the candidates.
2. **Caching the check.** A short-lived cache in the proxy, keyed on the gate cookie, would remove most round trips at the cost of delaying a revocation by the cache lifetime. Measure first.
3. **External identity providers.** Signing in through OIDC upstream of Hop3's own accounts is a separate decision.
