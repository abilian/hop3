# ADR 054: Email — transport, identity, and operator notifications

- **Status**: Accepted
- **Type**: Architecture
- **Created**: 2026-07-06
- **Related-ADRs**: 051 (config-injection — how these variables reach apps that don't read the environment), 048 (server config and secret storage), 041 (privileged-operations-agent — the relay's privileged setup), 036 (CLI argument consistency — secret input)

## Context

Real applications send email — password resets, invitations, notifications — and a platform that can't wire that up leaves an app half-deployed. But running a mail *server* is a losing game: deliverability, IP reputation, and abuse handling are full-time work, and most clouds block outbound port 25 outright. So Hop3 never runs an MTA. It relays through the operator's existing provider (Resend, SES, Postmark, Brevo, a corporate relay, …), and it deals only in **outbound transactional email** — no inbound, no IMAP, no MX.

Wiring a provider into an app splits into two concerns that change independently:

- **Transport** — *how* mail leaves the box: an SMTP submission endpoint and credentials. One generic SMTP path covers every provider, and one provider typically serves many of an operator's domains.
- **Identity** — the verified *From* domain: once a domain publishes SPF, DKIM, and DMARC, any address on it (`noreply@`, `support@`, `billing@`) can send. One domain typically covers many apps.

The forces this model has to answer: an operator should not paste the same SMTP credentials into every app; an app should send under its own From address without re-declaring the transport; deliverability is gated by DNS the operator controls, not by Hop3, so the platform must report it truthfully rather than imply mail will arrive; and the platform must be able to tell the operator when its *own* maintenance — a certificate that stops renewing — is about to cause an outage, using the transport it already has.

Getting the injected variables *into* an app that reads its configuration from a file or its own database, rather than from the environment, is a separate mechanism covered by ADR 051; this ADR is about the transport and identity model that produces those variables, and the operator-facing surface around it.

## Decision

**Hop3 stores and relays; it never accepts or delivers.** The email addon holds the operator's SMTP submission credentials and renders them for apps. Only submission ports are valid — 587 (STARTTLS) or 465 (implicit TLS); port 25 is not a submission target and is rejected. There is no inbound path.

**Transport and identity stay separate.** The addon wires the transport (submission credentials) and reports on the identity (the verified sending domain) as distinct things. Verifying a domain is not the same as hosting a mailbox on it: sending *as* `support@example.com` does not mean replies land at Hop3 — they follow the domain's existing MX.

**One transport, every spelling.** Because no two frameworks read the same variable names, the addon emits a single transport under every common convention at once — neutral `SMTP_*` plus an `SMTP_URL`, Django `EMAIL_*`, Flask-Mail `MAIL_*` — so a stock Django, Flask, or Node app sends with no code change and no per-app remap. This is the same multi-alias precedent the S3 addon sets with its `S3_*`/`AWS_*` names. Apps that read no environment at all are reached through the `before-run` config-injection path of ADR 051.

**The transport exists at two levels, and inheritance is by reference.** An operator can set the transport once at the **server level** — a root-owned singleton — and per-app addons created without their own `--smtp-*` **inherit** it. Inheritance stores a *reference*, not a copy: an inheriting addon keeps only its own From address and resolves the server transport at attach time, so rotating the server transport propagates to every app that inherits it. A per-app addon that supplies its own `--smtp-*` **overrides** the server transport for that app (a partial override — some but not all credentials — is refused). An inheriting app may send only on the server's verified sending domain; a From on another domain must bring its own transport.

**Validation lives at the domain boundary.** The transport value object enforces its invariants in construction — a submission port, a well-formed From, no control characters — so that no path (the CLI, a hand-edited secrets file, a future declarative block) can store a transport that would forge a sender or inject mail headers. A reader that encounters a stored transport violating these invariants treats it as absent and fails loud, rather than trusting it.

**Deliverability is checked, and never faked.** At create and status the platform verifies SPF and DMARC — and DKIM once its selector is known — against DNS on the sending domain. The result is three-state: present, a loud and actionable *missing* (with the record to publish), or *unverified* when no resolver is reachable. Hop3 never reports "ready" over unpublished DNS. Crucially, it also never reports a fake *missing*: DKIM lives at a provider- or account-specific `<selector>._domainkey` name that cannot be guessed, so DKIM is auto-verified **only** when the selector is known — from a provider profile that carries a fixed selector, or from an explicit operator-supplied selector — and otherwise stays guidance. A wrong "missing" that tells an operator to republish records that already work is worse than an honest "unverified".

**Provider profiles are data, not code.** A named-provider registry fills the SMTP endpoint (and, for the rare provider with a fixed DKIM selector, that selector) so an operator names a provider instead of typing a hostname. The registry is pure data; a provider earns code only when it needs real logic that data cannot express (a region-templated endpoint, a credential derivation), and such a provider is the exception the registry is designed to keep out of the common path.

**Server-level state is a file-permission-protected singleton, kept out of the addon namespace.** The server transport and the notifications configuration are root-owned `0600` JSON under `HOP3_ROOT/server/`, deliberately *not* under `HOP3_ROOT/addons/`, so they never surface as phantom addon instances. This follows the server-config direction of ADR 048.

**Platform notifications reuse the transport, and are best-effort but never silent.** Hop3 sends operator alerts — a certificate that failed to renew, and further maintenance events over time — through the server transport. The channel is opt-in, and a *disabled* channel is a legitimate no-op. But an *enabled* channel that cannot deliver (no transport, no recipient, a corrupt store, an SMTP failure) is surfaced — logged, and reported by the status command — never swallowed; and a notification failure never propagates into the operation it was reporting on. A cert-renewal cycle that already renewed its certs is not aborted because the alert about a *different* cert's failure could not be sent.

## Rationale

Separating transport from identity mirrors how the underlying reality is shaped — credentials and DNS are owned, rotated, and scoped independently — and it is what lets one server-level transport serve many domains while one verified domain serves many apps.

Reference inheritance rather than copy is the whole point of a "set once" transport: if inheritance copied the credentials, rotating the server transport would silently leave every existing app on stale credentials, which is exactly the per-app duplication the server level exists to remove.

The no-guess DKIM rule is a specific instance of the platform's refusal to fake a result. The temptation is to hardcode a "likely" selector per provider and report *missing* when it isn't found; but selectors are per-account for most providers, so that report would be wrong for the common case, and a confident wrong answer erodes trust in every other check the platform makes.

Notifications that can fail silently are worse than no notifications: they give the operator false confidence that they will be told when something breaks. So the design spends its complexity on making the *inability to deliver* loud, in the place the operator looks, rather than on the delivery itself.

## Consequences

An operator configures a provider once and every app inherits it; an app author sends mail by reading the environment, with no knowledge of which provider is behind it. Rotating a provider credential is a single server-level operation. Deliverability status is trustworthy enough to gate on, because it never overstates. The platform gains a delivery channel for its own alerts without a second piece of infrastructure.

The cost is that the platform now *sends* mail (previously it only stored and injected credentials), which introduces an SMTP client and its failure modes into the server process; these are contained behind the best-effort-never-silent contract. And the two-level transport adds a resolution step — an inheriting addon is only as available as the server transport it points at — which the readers handle by failing loud when the reference cannot be resolved.

## Open questions

- **Local relay and per-app envelope sender.** A host-local Postfix null-client (`localhost:25` + `sendmail`) forwarding to the server transport would let apps that read no SMTP configuration at all — stock WordPress, PHP `mail()`, cron — send with zero injection. The unresolved piece is per-app envelope-sender attribution, so that bounces route correctly and reputation is attributable per app: a sender-dependent relay map versus a per-app `sendmail` shim setting `-f`. The privileged Postfix setup would be a hop3-rootd operation (ADR 041). This is the largest open item.
- **Encryption at rest.** The server-transport, notifications, and per-app addon stores are protected by file permissions (`0600`, root-owned) but sit in plaintext on disk. Whether to encrypt the `server/*` and `addons/*` stores, and how to custody the key, is an open platform-wide question — not specific to email, and shared with the other addon secret stores.
- **Atomic writes for the JSON singletons.** The `server/*.json` stores are written non-atomically (write, then set permissions); a crash mid-write can leave invalid JSON. Readers are already defensive — a corrupt store fails loud and never crashes its caller — but a temp-and-rename write across all the JSON stores is unresolved.
- **Providers that need real logic.** Amazon SES has a region-templated endpoint and per-identity DKIM, and can require deriving an SMTP password from an IAM secret key; it does not fit the data-only profile. Whether such providers live as a pluggy provider plugin, and where the region and derivation belong, is open.
- **Per-app sub-credentials.** Where a provider's API can mint a credential scoped to one app — for reputation isolation and single-app revocation — whether Hop3 mints on attach and revokes on detach is open, and depends on the provider-profile framework growing an API surface.
- **Notification event coverage and cadence.** Certificate-renewal failure is the first wired event. Deploy failure has no single internal choke point today and is not yet wired; the broader event catalogue, and any de-duplication so a recurring condition does not alert every cycle, follow the monitoring work.
- **Reading DKIM selectors back from providers.** For the per-account providers, auto-verification depends on the operator supplying the selector. Whether to close that gap by reading the selector from a provider's API, where one exists, is open.

## References

- ADR 051 — Config injection (reaching apps that read a config file or their own database, not the environment).
- ADR 048 — Server config and secret storage (the server-level, permission-protected store direction).
- ADR 041 — Privileged operations agent (the boundary a local relay's Postfix setup would cross).
- ADR 036 — CLI argument consistency (the `--smtp-password -` / `@file` secret-input pattern).
- Code: `hop3/plugins/email/` (the addon, the server transport, provider profiles, deliverability checks, the SMTP sender, and notifications); `hop3/server/cert_renewal_service.py` (the first notification event source).
