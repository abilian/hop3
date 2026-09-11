# Readiness when the backend does not speak HTTP

**Status:** decided 2026-09-11, with a stated expiry. **Applies to:** the php-fpm work (platform blocker #16, [`plan-0.8.md`](plans/plan-0.8.md) headline 2) and to any future backend that answers a protocol other than HTTP on its own port.

## The contract today

Hop3 calls an app RUNNING when its port is bound *and* answers HTTP. Both halves are deliberate. `check_actual_status()` flips to RUNNING on the bound socket; `_app_serves_http()` (`deployers/deployer.py:618`) then opens a plain HTTP connection to `app.port` and requires a status line before the deploy is allowed to report success. The docstring says why, and it was written from an incident: gunicorn binds its listen socket in the master before forking, so `connect()` succeeds the instant the master is up, including when every worker is dead or hung. A bound socket is not proof of service.

That contract has an unstated premise: **whatever listens on the app's port speaks HTTP.** Every backend Hop3 has shipped so far does.

## What breaks

php-fpm does not. It speaks FastCGI, and nothing else. Point the existing probe at a php-fpm pool and it gets a protocol error, not a status line — so every PHP app would bind its port, fail the readiness gate, and be reported as a failed deploy while serving correctly through nginx. Not a degradation: a hard failure on all ten PHP applications in the catalog.

So the php-fpm work cannot land without answering a question that predates it: what does "ready" mean for a backend whose protocol is not HTTP?

## The immediate answer: speak FastCGI at it

For an app whose backend protocol is FastCGI, the readiness probe speaks FastCGI. php-fpm pools expose `ping.path`, and the reply comes from a **pool child**, not the master — so it carries the same evidence the HTTP probe was written to demand. A master that has forked no working child does not answer it. The premise the contract actually rests on is "a worker produced this response", and the FastCGI ping satisfies it; it was only ever expressed as "HTTP" because HTTP was the only protocol in the building.

What this buys: the blast radius is the PHP apps. No existing app's gate moves, because the probe is selected by the backend protocol the artifact declares, and everything that is not FastCGI keeps the HTTP path unchanged.

What it costs: a small FastCGI client in the tree (request record, params, read stdout) that exists for one caller. And the ping proves the pool serves, not that *this application's* PHP serves — the same limit the HTTP probe has without `[healthcheck].contains`, and `contains` stays available for apps that want the stronger gate.

The alternative considered and not taken now was probing through the app's nginx vhost, which tests the real request path end to end and would be the better answer on its merits. It was held back because it moves the deploy gate for every application at once — self-signed certificates, the `_` catch-all hostname, and the proxy-before-probe ordering all become load-bearing — and because a change of that size should not ride in on a PHP toolchain feature.

## The proper answer: [ADR 023](adrs/023-runtime-stack-replacement.md)

The reason this is awkward at all is that Hop3 infers readiness by probing from outside, because uWSGI's Emperor does not tell it anything useful. A process manager we own reports what it supervises: it knows a child forked, whether it stayed up, whether it is accepting work, and it can say so without anyone guessing a protocol. ADR 023 already proposes that manager; this is one more argument for it, and one more thing its design has to cover — **the supervisor reports readiness, the platform stops probing for it.**

Until then the probe stays, and it grows one protocol.

## What to check when this is revisited

- Whether any backend has been added whose protocol is neither HTTP nor FastCGI, which would mean a third branch and is the signal that probing from outside has run out.
- Whether `[healthcheck].contains` usage has grown, which would suggest the weak default gate is not carrying its weight for anyone.
- Whether the vhost probe has become cheap for other reasons (a settled certificate story, a stable admin hostname), in which case it displaces both branches rather than joining them.
