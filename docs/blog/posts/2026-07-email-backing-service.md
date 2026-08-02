---
date: 2026-07-10
template: blog_post.html
description: "Run a mail server or offload to a provider? The question picks the wrong axis: email is a backing service with a swappable backend, exactly like your database."
tags:
  - Architecture
  - Operations
  - Engineering
---

# Email Is a Backing Service

Real applications send email. Password resets, invitations, notifications, the digest nobody reads. A platform that cannot wire that up leaves every app it deploys half-finished. Hop3 stood there until recently: closing that gap forced a better question.

The question everyone asks about email is the wrong one.

## The wrong question

Ask how a self-hosted platform should handle email and the debate arrives pre-shaped: **do you run a mail server, or do you offload to a provider?**

Both answers are defensible. Running your own MTA means no third party sees your mail. It also means DKIM keys, SPF records, a PTR record your hosting provider may not let you set, a fresh IP with no sending reputation, and blocklists that will treat you as guilty until proven otherwise. Offloading means deliverability that works on day one, and a provider holding your mail and your credential.

The trouble is that this framing makes the choice architectural: as though it belongs in the platform's design, permanently, for everyone.

Hop3 already answers the same shape of question for databases, and nobody argues about it.

## The question we already answered

When an app needs PostgreSQL, Hop3 provisions an addon, attaches it, and injects `DATABASE_URL`. The app opens a connection. It has no idea whether the server on the other end is a PostgreSQL that Hop3 installed on the same box or a managed instance somewhere else, and it does not need to.

That indifference is the point, and it is not our invention. The Twelve-Factor methodology's fourth factor is **backing services**, and it names *"SMTP services for outbound email (such as Postfix)"* in the same breath as datastores and caches. It is explicit that the app "makes no distinction between local and third-party services."

Email is a backing service. Whether the thing behind it is first-party or third-party is an implementation detail the addon interface is supposed to hide. The real question is narrower and much easier to answer: *what backends should the email addon support, and how does an operator pick one?*

[ADR 054](/developers/adrs/054-email-transport-and-notifications/) settles that.

## How it works

The operator chooses a backend **once, at the server level**:

```bash
hop3 server email backend relay --provider resend --from-domain example.com
```

An app opts in by declaring an email addon, and inherits whatever backend the server is set to:

```toml
[[addons]]
type = "email"
```

The app is injected `SMTP_HOST`, `SMTP_PORT` and friends, pointing at a **loopback SMTP endpoint on `127.0.0.1:25`**, and sends mail the way it always has.

## Why loopback matters

The loopback hop looks like an extra moving part. It buys two things that are hard to get otherwise.

**The provider credential never enters an app's environment.** Without it, every app that sends mail holds your Resend or Postmark API key in its env, which means every app compromise is a credential compromise, and rotating that key means touching every app. With it, the app authenticates to nothing: it hands the message to a local relay, and the relay holds the credential.

**The backend becomes swappable without touching apps.** Start on a dev sink, move to a provider, later move to your own MTA, and no application configuration changes. The contract the app sees (an SMTP server on loopback) is stable across all three.

There is a third benefit that only shows up on a bad day: a local relay **queues**. When the provider is unreachable, mail waits and is retried without raising an exception inside a password-reset request.

## The three backends

**`relay`**: a provider or a corporate smarthost. Hop3 ships profiles for Resend, Postmark, Brevo, Mailgun, Mailgun EU and Scaleway TEM, so `--provider resend` fills in the host and port without asking you to look them up. EU-hosted providers are flagged as such: for many Hop3 users, that is a hard constraint.

Before reporting itself ready, the relay backend runs a deliverability pre-flight: it checks SPF and DMARC, and verifies DKIM once the selector is known. If the DNS is not published, it says so. It does not report "configured" over records that do not exist: a "ready" that means "we wrote a config file" is how you find out about your mail six weeks later, from a customer.

**`catch`**: a development sink that captures mail and never sends it. This is the one to use while building. It is validated end to end in CI: a dev sink that silently drops messages is worse than no sink, because it teaches you the code path works.

**`direct`**: the box becomes its own MTA. Postfix delivers straight to recipients' MX, opendkim signs outbound mail, no third party. Hop3 generates the DKIM keypair and prints the exact SPF, DKIM and DMARC records to publish, plus a reminder about the PTR record you probably need your hosting provider to set. It runs the same pre-flight, and it probes outbound port 25: many providers block this by default. Catching it during setup prevents a production outage.

`direct` ships in 0.7 as a **preview**: the code is there and fails loudly where it cannot run. It has no end-to-end test yet, a gap under supervisor-based targets, and the fresh-IP reputation caveat that no amount of code fixes. Full support is 0.8.

## Notifications ride the same channel

Once the platform can send mail, it can tell you things. Two are wired up in 0.7:

- **Certificate renewal failures**: a certificate that has stopped renewing reaches you before expiry, while there is still time to act.
- **Failed deploys**: best-effort, and never in a way that masks the failure itself.

Both go through whatever backend is active. Turn them on with `hop3 server email notifications on`; `status` will tell you whether the channel is actually deliverable.

## Apps that ignore the environment

The clean design above assumes an app reads `SMTP_HOST` from its environment. Plenty do not: WordPress is the obvious example, where mail settings live in the database or a plugin.

That calls for a translation layer, which Hop3 already has for the same problem elsewhere ([ADR 051](/developers/adrs/051-config-injection/)): the injected variables are written into whatever form the app actually reads. For WordPress that is a self-guarding mu-plugin, installed at deploy time, which configures SMTP from the injected values and gets out of the way if you have already set up something else.

## What is deferred

0.7 is not the end of this. Per-app backend override through the loopback, sub-credentials so each app gets its own provider identity, SES and the other providers with real API logic, outage and health notifications, and encryption at rest for stored credentials are all 0.8 or later. None of them are needed for the 0.7 story to hold: an app declares that it sends mail, and mail gets sent.

---

*Design record: [ADR 054](/developers/adrs/054-email-transport-and-notifications/). Setup lives in the [addons guide](/guides/addons/).*
