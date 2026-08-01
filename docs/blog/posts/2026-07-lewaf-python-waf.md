---
date: 2026-07-03
template: blog_post.html
description: Hop3 0.7 puts a Layer-7 firewall in front of your apps. The engine behind it is LeWAF, a pure-Python OWASP Core Rule Set implementation we wrote and released standalone.
tags:
  - Security
  - Engineering
  - Architecture
---

# We Wrote a Web Application Firewall in Python

Hop3 0.7 can put a Web Application Firewall in front of any app you deploy: OWASP Core Rule Set, per-app policy, automatic bans. Turn it on with two lines of `hop3.toml`.

The engine behind it is **[LeWAF](https://pypi.org/project/lewaf/)**, a pure-Python, ModSecurity-compatible WAF engine we wrote and released standalone on PyPI under Apache-2.0.

Writing your own security engine is normally a bad idea. This is the case for why it was the right call here, and what it cost.

## The two layers

The firewall and the WAF answer different questions, and they compose.

The **network firewall** ([ADR 045](/developers/adrs/045-fixed-port-registry/)) decides whether a packet may reach a port at all. You declare `[[ports]]`, Hop3 translates that into `nft` rules, and the privileged daemon applies them. It has no idea what HTTP is.

The **WAF** decides whether an HTTP request that reached the app's port is acceptable: SQL injection, cross-site scripting, path traversal, remote code execution, and a per-app access policy. It reads the request; it knows nothing about packets.

An app can use either, both, or neither. This post is about the second one.

## Choosing an engine

The rules were never in question. The OWASP Core Rule Set is the standard answer for Layer 7, it is expressed in SecLang, and any engine worth using speaks that dialect. The question was which engine.

The mature options are [Coraza](https://coraza.io/), which is Go, and libmodsecurity, which is C. Both are good software, and either would have worked. Two things decided it against them.

**The process model.** Hop3 is Python end to end: the server, the CLI, the toolchains, and an installer written against the standard library alone so it can bootstrap a machine with nothing on it. Introducing a Go binary or a C library means a second build and runtime story running alongside the first: cross-compilation for every architecture, a packaging path per distribution, an independent upgrade cadence, and a failure mode ("the binary won't load on this host") that none of our existing diagnostics understand. That is a real, permanent tax on a platform whose selling point is that one command installs it anywhere.

**Ownership.** Hop3 exists so people can own their infrastructure, and a platform that cannot fix its own security engine has a soft spot in that argument. Rule engines have bugs, CRS integrations drift, and false positives block legitimate requests to somebody's production app. We wanted a bug we could fix the same morning, without waiting on an upstream issue tracker.

So we wrote LeWAF, and released it on its own as a standalone project. It speaks SecLang and ships the CRS's 681 rules, so nothing about the protection changes.

Coraza remains available. It sits behind the same `WafEngine` interface ([ADR 050](/developers/adrs/050-waf-l7-lewaf/) §6) as a future alternative for operators who want a non-Python engine at higher throughput. The plugin seam exists so that choice stays open rather than being made once, by us, for everyone.

## What LeWAF is

A standalone project, usable outside Hop3:

- a **SecLang parser**, so existing ModSecurity rule sets load;
- the **OWASP Core Rule Set**, bundled;
- **framework integrations** for Flask, FastAPI, Starlette and Django, if you want it in-process;
- a **standalone reverse-proxy mode** (`lewaf-proxy`), which is how Hop3 uses it.

Python ≥ 3.12, Apache-2.0, on PyPI. If you run a Python web app and want CRS in front of it without introducing a second runtime, it works on its own.

## How Hop3 deploys it

Turning the WAF on for an app is a `hop3.toml` section:

```toml
[waf]
enabled = true
```

On deploy, Hop3 puts a per-app WAF proxy in the request path:

```
nginx  →  lewaf-proxy  →  uWSGI (your app)
```

The proxy runs as a uWSGI Emperor vassal, supervised like any other app process: started when the app deploys, reaped when it is destroyed. The app itself stays bound to loopback, so there is no route around the WAF; you cannot reach the application except through it.

The engine ships as the `hop3-server[waf]` extra and is imported lazily, so a server that runs no WAF-enabled apps pays nothing for it.

## Declarative policy, compiled

SecLang is a real language and writing it by hand is how a WAF ends up misconfigured. So the app-facing surface is declarative, and Hop3 compiles it:

```toml
[waf]
enabled = true

[[waf.gate]]
path = "/admin"
allow = ["office"]
```

Named networks (`hop3 network`) resolve to addresses, the gates become SecLang, and the result is validated **before** it is committed. A policy that would not compile is rejected at deploy time with the offending rule named. It is never accepted silently.

## Bans, without a cron job

Blocking a single malicious request is the easy half. An attacker who is probing will send thousands, and answering each one with a 403 is a lot of work for no benefit.

LeWAF's audit stream feeds a scorer inside hop3-server. Requests that trip rules accumulate a score against their source; past a threshold, the source is banned and the ban is recorded in the database. Reconciliation runs in-process roughly every minute: no external scheduler, no state that survives only in memory. You can see and clear bans:

```bash
hop3 waf bans list
hop3 waf bans clear <ip>
```

Bans are currently Layer 7: the request is rejected by the proxy. Pushing them down to `nft`, so a banned address never completes a TCP handshake, is a deliberate later step: it means handing ban decisions to the privileged daemon, and that deserves its own design round.

## How we know it works

Two Docker end-to-end tests that exercise the full proxy chain (nginx → lewaf-proxy → uWSGI):

- **CRS blocking**: SQL injection, XSS, path traversal and RCE payloads through `nginx → lewaf-proxy → uWSGI`, asserting each is rejected.
- **The ban loop**: enough tripping requests to cross the threshold, then asserting the source is banned, the ban is recorded, and reconciliation applies it.

There is also a false-positive pass. It matters more: a WAF that blocks legitimate traffic gets switched off, and then protects nothing. File uploads and JSON bodies are the usual casualties, which is why body inspection can be skipped per route.

## What this costs

Pure Python is slower than Go or C. For a single-server PaaS running self-hosted applications (the workload Hop3 is built for), request rates sit far below where that difference decides anything. If your traffic profile says otherwise, the engine interface is there so Coraza can be plugged in behind it.

The trade we made: a component we can read, debug, and fix in the same language as the rest of the platform, against throughput we do not need. For a project whose premise is that you should be able to own your stack, that is the right way round. And if it ever stops being right for your workload, the engine interface is how you change it.

---

*Details in [ADR 050](/developers/adrs/050-waf-l7-lewaf/). The `[waf]` schema is in the [configuration reference](/reference/config/), and the CLI in the [command reference](/reference/cli/).*
