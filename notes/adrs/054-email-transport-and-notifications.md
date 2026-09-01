# ADR 054: Email: a backing service with a swappable backend

- **Status**: Accepted
- **Type**: Architecture
- **Created**: 2026-07-06
- **Related-ADRs**: [051](./051-config-injection.md) (config-injection (how the connection variables reach apps that don't read the environment), [048](./048-server-config-and-secret-storage.md) (server config and secret storage), [041](./041-privileged-operations-agent.md) (privileged-operations-agent) the MTA's privileged setup), [036](./036-cli-ergonomics.md) (CLI argument consistency: secret input)

## Context

Real applications send email (password resets, invitations, notifications) and a platform that can't wire that up leaves an app half-deployed. Hop3 already answers the equivalent need for databases and caches: a **backing service**, provisioned as an addon, attached to an app, and consumed through injected connection variables. Email is the same kind of object, and the design gains its coherence from treating it that way.

The framing this ADR settles is what "provide email" means for a single-server PaaS. Stating the question as a binary (*run a mail server* versus *offload to a third party*) picks the wrong axis. Whether the service behind an addon is operated by Hop3 or by a third party is an **implementation detail hidden by the addon interface**: the database addon provisions a Hop3-run PostgreSQL and exposes it as `DATABASE_URL`. The Twelve-Factor "backing services" principle (factor IV, which names *"SMTP services for outbound email (such as Postfix)"* as a normal backing service) is explicit that an app "makes no distinction between local and third-party services." So the real question is *does the email addon have a first-party default backend*, the way the database addon does: and what the space of backends is.

The forces the model must answer are unchanged by this framing and are what make email more than a database:

- **The consumer must be backend-agnostic.** An app sends mail by reading its configuration; swapping the backend behind the addon must change neither the app's code nor the variable names it reads.
- **Transport and identity are separate and independently owned.** *Transport* is how mail leaves the box (a submission endpoint and credentials, or a direct-delivery MTA); *identity* is the verified From-domain (once a domain publishes SPF, DKIM, DMARC, any address on it can send). One transport serves many domains; one domain serves many apps.
- **Deliverability is gated by DNS and IP reputation the platform does not own**, so it must be reported explicitly.
- **Some apps read no SMTP environment** (stock WordPress, PHP `mail()`, cron) and must be pointed at a submission endpoint through their own configuration rather than through injected variables.
- **The platform must be able to tell the operator when its own maintenance** (a certificate that stops renewing) is about to cause an outage, using whatever backend is configured.

Getting the injected variables *into* an app that reads its configuration from a file or its own database is a separate mechanism ([ADR 051](./051-config-injection.md)); this ADR is about the backing-service model, the backends behind it, and the operator-facing surface around it.

## Decision

**Email is a backing service, symmetric with the database addon.** `hop3 addon email create` configures the service; `hop3 addon attach <name> --app <app> --type email` injects the connection variables; the app consumes them exactly as it consumes `DATABASE_URL`. Everything below is about what sits behind that interface.

**The backend is a first-party, swappable implementation.** The email addon ships first-party backends and can also point at an external provider: the same relationship the database addon has to a Hop3-run database versus an external one. Which backend is active is an operator choice made once at the server level; per-app addons inherit it. Three backend kinds span the space:

- **Catcher**: a local dev sink (Mailpit-class). Mail is captured and viewable, never delivered. This is the safe non-production default: the same app code that relays in production is exercised in development and CI without sending anything.
- **Relay**: submission to a provider or a corporate smarthost (Scaleway TEM, SES, SendGrid, Mailgun, Brevo, an in-house MTA). The provider owns deliverability, reputation, and abuse handling. This is the recommended production backend, and the EU-provider variants are the sovereign path the multi-tenant clouds do not offer.
- **Direct**: a Hop3-run MTA that delivers to recipients' MX itself, with no third party. Hop3 generates the DKIM keypair and surfaces the exact records to publish. This is the fully-sovereign backend; its deliverability to large receivers is earned through DNS and IP reputation, and is reported explicitly.

**The app-facing interface is a stable local submission endpoint.** The addon emits one transport under every common spelling at once (neutral `SMTP_*` plus `SMTP_URL`, Django `EMAIL_*`, Flask-Mail `MAIL_*`) all pointing at a loopback SMTP endpoint the platform owns, so a stock Django, Flask, or Node app sends with no code change (the same multi-alias precedent the S3 addon sets). Apps reach the backend by speaking SMTP to that endpoint, never by shelling a local `sendmail` binary. A local-binary side-channel is not a config-driven backing service. An app that reads no environment is pointed at the same endpoint through config-injection ([ADR 051](./051-config-injection.md)). Swapping the backend changes neither the variable names nor the endpoint, so no app is re-touched when the backend changes.

**The local relay queues; it never fire-and-forgets.** The loopback submission endpoint is a queuing MTA that spools and retries. A transient upstream failure must not silently drop mail: silent loss is exactly the failure the platform forbids, which rules out a fire-and-forget forwarder and requires a queue that defers and, on a permanent error, bounces visibly. The relay is a managed shared resource, disciplined like the reverse proxy: it binds loopback only and relays for no one but local processes, so it is never an open relay; each app's outbound mail carries the envelope sender the app presents over SMTP, so bounces route and reputation is attributable per app without depending on the submitting Unix identity; creating or destroying one app never perturbs another's mail; and an app that reaches the endpoint with no backend configured fails loud, refusing to send into a void.

**Transport and identity stay separate.** The addon wires the transport and reports on the identity as distinct things. Only submission ports are valid for a relay: 587 (STARTTLS) or 465 (implicit TLS); port 25 is never a submission target. Verifying a domain is not the same as hosting a mailbox on it: sending *as* `support@example.com` does not mean replies land at Hop3; they follow the domain's existing MX. Inheritance is by reference: a per-app addon created without its own credentials stores a *reference* to the server backend and resolves it at attach time, so rotating the server backend propagates to every inheriting app. A per-app addon that supplies its own credentials overrides for that app (a partial override (some but not all credentials) is refused), and may send only on its own verified domain.

**Validation lives at the domain boundary.** The transport value object enforces its invariants in construction (a submission port, a well-formed From, no control characters) so no path (the CLI, a hand-edited secrets file, a future declarative block) can store a transport that would forge a sender or inject headers. A reader that encounters a stored transport violating these invariants treats it as absent and fails loud. The catcher is the one representation deliberately outside this invariant (a loopback, no-auth, sink-only endpoint that never leaves the box) and is modelled as a distinct dev-mode value, so relaxing it for development never weakens the production submission-port/auth guarantee.

**Deliverability is checked, and never faked.** At create and status the platform verifies SPF and DMARC (and DKIM once its selector is known) against DNS on the sending domain, in three states: present; a loud, actionable *missing* with the record to publish; or *unverified* when no resolver is reachable. Hop3 never reports "ready" over unpublished DNS, and never reports a fake *missing*. DKIM lives at a provider- or account-specific `<selector>._domainkey` name that cannot be guessed, so DKIM is auto-verified only when the selector is known: from a provider profile carrying a fixed selector, from an explicit operator-supplied selector, or, for the direct backend, from the key Hop3 itself generated.

**Provider profiles are data.** A named-provider registry fills the submission endpoint (and, where a provider uses a fixed provider-wide DKIM selector, that selector) so an operator names a provider without typing a hostname. The registry is pure data; a provider earns code only when it needs logic data cannot express (a region-templated endpoint, a credential derivation), and such a provider is the exception the registry is designed to keep out of the common path.

**Server-level backend state is a file-permission-protected singleton, kept out of the addon namespace.** The active backend and the notifications configuration are root-owned `0600` JSON under `HOP3_ROOT/server/`, deliberately not under `HOP3_ROOT/addons/`, so they never surface as phantom addon instances (following [ADR 048](./048-server-config-and-secret-storage.md)). The direct backend's MTA and DKIM setup is privileged and crosses the hop3-rootd boundary ([ADR 041](./041-privileged-operations-agent.md)).

**Platform notifications reuse the active backend, and are best-effort but never silent.** Hop3 sends operator alerts (a certificate that failed to renew, and further maintenance events over time) through whatever backend is configured. The channel is opt-in, and a disabled channel is a legitimate no-op. But an enabled channel that cannot deliver (no backend, no recipient, a corrupt store, a send failure) is surfaced (logged, and reported by the status command) rather than swallowed; and a notification failure never propagates into the operation it was reporting on.

## Rationale

Modelling email as a backing service with a swappable backend makes the design cohere: the platform commits to an interface and a first-party default (exactly as it already does for databases) and the delivery mechanism becomes an implementation detail the app never sees. This also lets the three backends share one app-facing contract and be swapped without touching an app.

The "a PaaS never runs an MTA" reflex is an operational stance inherited from the multi-tenant clouds, where shared egress IPs and blanket port-25 blocks make an in-house MTA a reputation liability, so they push every app to a third-party relay. That stance is about *their* infrastructure rather than the backing-service model, and it does not bind a single-tenant self-hosted server whose operator owns the IP and can deliver directly or run a local relay. Declining to run an MTA is therefore one backend's tradeoff; direct delivery is a first-class backend alongside any relay-based one.

A queuing MTA over a fire-and-forget shim is forced by the same rule as everything else here: dropping mail on a transient upstream outage and reporting nothing is precisely the silent failure the platform refuses. The MTA earns its shared-resource cost by being disciplined like the reverse proxy, which the platform already manages as a shared resource without letting one app perturb another.

Separating transport from identity mirrors how the underlying reality is shaped (credentials and DNS are owned, rotated, and scoped independently). A set-once backend depends on reference inheritance: a copy would leave every existing app on stale credentials when the operator rotates. The no-guess DKIM rule and the never-faked deliverability states are instances of the platform's refusal to state a result it has not verified; a confident wrong answer erodes trust in every other check it makes.

## Consequences

An operator selects a backend once and every app that attaches the email addon sends with no per-app credentials and no code change, through a loopback endpoint that keeps the provider credential out of app environments; legacy apps and stock WordPress send once pointed at that endpoint through config-injection; and the same app code that captures mail in development relays it in production. Rotating a provider credential, or swapping a provider for a sovereign one, is a single server-level operation invisible to apps. Deliverability status is trustworthy enough to gate on, because it never overstates.

The cost is that the platform now optionally runs an MTA (introducing a mail queue and its failure modes into the box) contained behind the queuing and managed-resource discipline above. The direct backend additionally makes Hop3 the custodian of a DKIM key and the author of DNS the operator must publish, and its deliverability to large receivers depends on IP reputation the platform can report on but cannot grant. The two-level inheritance adds a resolution step (an inheriting addon is only as available as the server backend it references) which readers handle by failing loud when the reference cannot be resolved.

## Open questions

- **Per-app sub-credentials.** Where a provider's API can mint a credential scoped to one app (for reputation isolation and single-app revocation) whether Hop3 mints on attach and revokes on detach is open, and depends on the provider-profile framework growing an API surface.
- **Providers that need real logic.** Amazon SES has a region-templated endpoint and per-identity DKIM and can require deriving an SMTP password from an IAM secret key; it does not fit the data-only profile. Whether such providers live as a pluggy provider plugin, and where the region and derivation belong, is open.
- **DKIM key custody and rotation for the direct backend.** Where the generated private key lives, how it is rotated, and how rotation coordinates with the published DNS is open.
- **Encryption at rest.** The server-backend, notifications, and per-app addon stores are protected by file permissions (`0600`, root-owned) but sit in plaintext on disk. Whether to encrypt them, and how to custody the key, is a platform-wide question shared with the other addon secret stores.
- **Atomic writes for the JSON singletons.** The `server/*.json` stores are written non-atomically (write, then set permissions); readers already fail loud on a corrupt store, but a temp-and-rename write across all the JSON stores is unresolved.
- **Notification event coverage and cadence.** Certificate-renewal failure and deploy failure are covered (the deploy path funnels through one orchestration function, which is the choke point the deploy event hooks). Which further events to cover (outage and health signals in particular) and at what cadence, including de-duplication so a recurring condition does not alert every cycle, follows the monitoring work.

## References

- [ADR 051](./051-config-injection.md): Config injection (reaching apps that read a config file or their own database).
- [ADR 048](./048-server-config-and-secret-storage.md): Server config and secret storage (the server-level, permission-protected store direction).
- [ADR 041](./041-privileged-operations-agent.md): Privileged operations agent (the boundary the direct backend's MTA setup crosses).
- [ADR 036](./036-cli-ergonomics.md): CLI argument consistency (the `--smtp-password -` / `@file` secret-input pattern).
- Code: `hop3/plugins/email/` (the addon, the server backend, provider profiles, deliverability checks, the sender, and notifications); `hop3/server/cert_renewal_service.py` (the certificate-renewal notification event source).
