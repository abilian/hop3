# ADR 064: HTTP-SASL at the Access Gate

- **Status**: Deferred (2026-10-28)
- **Type**: Feature
- **Created**: 2026-10-13
- **Related-ADRs**: [062](./062-authenticated-access-gate.md) (extended here; this ADR answers its open question 1), [063](./063-identity-layer.md) (the mechanisms and the sign-in budgets), [021](./021-proxy-plugin-system.md) (proxy plugins)

> **Deferred.** The Internet-Draft this design rests on (draft-vanrein-httpauth-sasl) stopped at revision -08 in November 2022 and expired in May 2023; its author has not answered our contact, and no other implementation is in sight. [ADR 063](./063-identity-layer.md) §5 gives scripts tokens instead: the OAuth device authorization grant, exchanged at the gate for a session, which also answers ADR 062's open question 1. This record is kept for the day the draft revives; the mechanisms of ADR 063 §3 would serve it unchanged.

## Context

The access gate (ADR 062) admits a browser after a redirect through Hop3's sign-in page. A script or a command-line client cannot follow that flow, and should not send a password at all if a mechanism can prove it instead. ADR 062 left this open: accepting `Authorization: Bearer` there collides with apps that use the header for their own tokens.

A machine API (a webhook, an app's API keys) is a different case: it belongs on the public paths of ADR 062, behind the app's mechanism. This ADR covers a client acting for a person on the paths ADR 062 protects for people.

HTTP-SASL is an Internet-Draft that transports any SASL mechanism over `WWW-Authenticate` and `Authorization`. With SCRAM the password stays off the wire. With SCRAM's `-PLUS` variants the exchange is bound to the TLS channel, so a site that relays it through its own TLS connection fails. We propose to use it for script access to gated apps only. We do not propose to revive or extend the draft.

Three properties of the access check constrain the design:

- **Each step of an exchange is a forward-auth call.** The proxy consults the check and acts on its status; the check sees only the headers.
- **The check is stateless.** The steps of one exchange may arrive on different connections and proxy workers.
- **TLS terminates in the proxy** on the primary, for apps on every server, and for most hosts Hop3 installed the certificate itself.

## Decision

### 1. The offer rides on the sign-in redirect

The gate should add a `WWW-Authenticate: SASL` offer to each anonymous response, beside the redirect to the sign-in page. A browser follows the redirect and ignores the offer; a SASL client takes it up. A plain 401 goes only to a client that has started an exchange, so browsers keep ADR 062's flow. The offer lists the mechanisms the active backend supports (ADR 063 §4): `-PLUS` variants only where channel binding can work (§4), `PLAIN` over TLS only.

### 2. Rounds through the check

A round is a request to the app with `Authorization: SASL …`. The check runs the mechanism's step (ADR 063 §3). It returns 401 with the next challenge while the exchange continues, and 200 once the mechanism succeeds, admitting the request like a signed-in one.

The state of the exchange travels with the client, signed by the server: the mechanism's state, the app as audience, a single-use identifier and a short expiry. The check keeps only the identifiers already used, until they expire, so a captured request cannot be replayed. A cached check (ADR 062's question 2) must not cache these requests. A mechanism's state is visible to the client, so it must hold nothing secret.

Each failure (a wrong proof, an unknown account, a forged or expired state, a replayed request) gets a fresh offer and nothing else; the reason goes to the server log. A client over either sign-in budget (ADR 063 §5) gets the same response with `Retry-After`.

### 3. Headers passed to the app

`Authorization: SASL` stops at the check; any other `Authorization` reaches the app unchanged, so an app's API tokens keep working behind the check. The identity headers are ADR 062's, set from the authenticated account.

### 4. Channel binding

`tls-server-end-point` (RFC 5929) is the default binding. Its value is a hash of the server's certificate, so the check can compute it from the certificates Hop3 installed for the host, with no help from the proxy, whichever connection each step arrives on. During a renewal both certificates must be accepted.

`-PLUS` is offered only where Hop3 terminates TLS. Behind a CDN or a load balancer that terminates it, the client's binding cannot match, so the offer leaves `-PLUS` out and exchanges do not fail for that reason. `tls-exporter` (RFC 9266) is an option where a proxy can export keying material; a proxy must then strip any client-supplied value first, so a misconfiguration fails closed.

### 5. A session after success

Success creates a Hop3 session for the account and the app, delivered as the access cookie of ADR 062 and as the draft's session token. It ends when it expires, is revoked, or the account is disabled. The final server message, which proves to the client that the server held the account's keys, is returned with it.

### 6. One behaviour behind three proxies

nginx, Caddy and Traefik each pass a different part of the check's response back to the client. Some proxies cannot add headers to a successful forward-auth response. The access capability of the proxy plugins (ADR 062) must therefore pass four things for each proxy with its stock build. The client's `Authorization` goes to the check, the challenge and `Retry-After` go back to the client, the app's `Authorization` replaces the client's, and the session reaches the client on completion. Where a proxy cannot return headers on success, the check may respond to the final request with a redirect to the same URL that holds the session, at the cost of one more round trip.

### 7. Clients

Hop3 should provide the client side for programs: a library, a small `curl`-like helper, and the `hop3` command-line client calling a gated app's API as a Hop3 account. A browser keeps the sign-in page.

## Acceptance

On each of the three proxies, on a gated app:

1. an anonymous request gets the sign-in redirect and a SASL offer on the same response, and a browser still lands on the sign-in page;
2. a script signs in with SCRAM-SHA-256, and with SCRAM-SHA-256-PLUS, and gets the app's authenticated content and a session;
3. the `-PLUS` exchange relayed through another TLS terminator fails, and so does a downgrade;
4. a wrong password, a replayed request and a state forged or minted for another app are refused, each with a fresh offer;
5. the session admits later requests for that app only, and revoking it or disabling the account ends it;
6. `Authorization: SASL` never reaches the app; the app's own `Authorization` does;
7. each password proof takes from the per-account sign-in budget.

## Consequences

### Positive

- Scripts reach gated apps with a Hop3 account and no form, and the password never crosses the wire.
- With `-PLUS`, a phishing site that relays the exchange fails.
- All gated apps get this at once, with no change to the app.

### Negative

- The check does more work per anonymous request. Each step of an exchange runs a mechanism.
- Some proxies need one more round trip to complete an exchange.
- Used identifiers are held in memory, which works while hop3-server runs as one process on the primary, as it does today; several hop3-server processes would need a shared record of them.
- Few clients speak HTTP-SASL today: Hop3 must ship one.

## Alternatives considered

- **A 401 for every anonymous request.** Closer to the draft's examples; breaks the browser flow of ADR 062.
- **A bearer token at the gate.** Simple for scripts. It takes over the app's `Authorization`. A stolen token works as a password until it expires.
- **Exchange state on the server.** Simpler tokens; costs a store written at each step and shared by all workers.
- **No script access at all.** Scripts would use each app's API keys, one per app and per user, which is what a single identity is meant to end.

## Open questions

1. **Interoperability.** Where the draft and RFC 7615 differ on the success header, we follow the RFC. Decided by other implementations, if any appear.
2. **A terminator Hop3 does not know about.** An operator who puts a CDN in front of a host breaks all binding clients. Candidates: a per-app setting that turns binding off, or a server setting naming such hosts. Decided by the first operator deployment behind a CDN.
3. **Whether HTTP-SASL stays** if a better standard for non-browser sign-in to web apps emerges; the mechanisms (ADR 063) would remain usable.
