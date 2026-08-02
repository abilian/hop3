# Parked: directions that are deliberately not scheduled

**Created:** 2026-08-01. **Owner:** SF. **Status:** none of this is booked, and none of it should be started without talking to SF first.

## What this file is

Five architectural directions that Hop3 has designed, argued for in its own records, and chosen not to build yet. Each is real work with a real justification. Without this file, each gets rediscovered every few months, looks obviously worth doing, and consumes a week before anyone asks whether it was the right week.

They are not in [`plan-0.8.md`](plan-0.8.md) or [`plan-0.9-plus.md`](plan-0.9-plus.md) because each would reshape the platform, and because starting one casually is the expensive mistake. **The default answer is "not yet", and the way to change it is a conversation.**

Everything here is public design already: the ADRs are published, and TR-03 §9 sets out most of it as future work.

## A. The agent model and a distributed control plane

*ADR 017 (Draft), ADR 029 (Accepted, unimplemented).*

**Single-node self-healing** is the first phase and the one with standalone value: a reconciliation loop with health probes and restart policies (`WatchdogService`, `HealthChecker`, `RestartPolicy`, `AppEvent`). Today nothing watches a deployed application: a process that dies stays dead until somebody looks. This is worth having on one machine, and it is also the doorway to everything else in this section, which is why it is not simply a 0.8 item.

**Beyond it:** turning the local privileged helper into a node agent (authenticated remote transport, node identity and enrolment, an unprivileged multi-node scheduler), and extending the fixed-port registry (ADR 045) from single-host arbitration to a fleet. The helper's typed operation allowlist already exists and is tested. The new work is transport, identity and dispatch, as TR-03 §9.1 observes.

If configuration is ever applied without a full rebuild, the criterion should be mechanical. State that was never an input to the derivation may change without re-deriving; anything touching a package, a module option or the closure hash may not.

> **Not parked:** ADR 045's other open item (a Docker app's declared port is conflict-checked but never opened in the generated compose file) is single-host work and can be picked up any time.

## B. Multi-component applications

*ADR 038, accepted at schema-design stage only.*

A component schema in which an application declares its web, worker, queue and companion processes as one unit, with declared start ordering, per-component health checks and per-component resource limits.

Three catalog applications want it today: Bugsink (a `snappea` worker with its own queue database), Nextcloud (cron) and Invoice Ninja (queue). All three work now through `[run.workers]` plus `before-run`, so the need is real but not urgent.

TR-03 §9.7 records the trap: the corpus is the wrong shape to validate this, having been assembled from applications that fit the single-process-tree assumption. Testing a component model means first packaging applications chosen because they *don't* fit.

> Extending `[run.workers]` with per-process environment, ports and limits looks like a small schema tweak and is the component model in embryo. It belongs to this item.

## C. A second output target for the generator

*TR-03 §9.7 names this as future work.*

The templates today emit a Nix expression plus a runtime description for Hop3's own deployer. The parked direction emits a **system-closure module for a declarative Linux distribution**, with hardening directives as attributes on units it is producing anyway.

Two emitters fall out of the same machinery: a **backup and restore declaration** derived from a statement of where an application's durable state lives, and a **configuration schema** derived from the module's option set, carrying option identity so upstream renames can be tracked across versions.

TR-03 §9.7 also records the hard part, which is why this is not a weekend: the vendoring pattern, lockfile handling and hash pinning have to survive the translation in each ecosystem, and that is where such translations usually fail.

> **Not parked:** teaching the *existing* templates to build first-party source (`src = ./.`) targets Hop3's own runtime, closes a limitation TR-03 §7.1 states outright, and is a 0.8 headline item.

## D. The diagnosis classifier as a standalone library

The classifier ships today (ADR 043): it sorts deployment failures into a fixed verdict set (proxy misconfiguration, build failure, unreachable backing service, application crash, timeout) and reports the decisive signal ahead of the raw logs. The motivating case is a healthy process behind a proxy pointed at the wrong port, which returns a 502 indistinguishable from a crash.

The parked direction extracts and packages it as a library usable outside Hop3. The idea generalises past this platform; the work is packaging, API design and documentation.

## E. Portability as a standing regression test

Backup, restore and cross-server migration ship today with an automated test (ADR 024). The parked direction turns that demonstration into a **nightly property across the whole application set**, between two different infrastructure providers, with authentication and state verified intact after each move.

The by-product is the more interesting half: base URL rewriting, identity-client re-registration and object-storage reference rewriting are per-application concerns with no standard home. A corpus this size is a large enough sample to propose one with evidence behind it.

## If one of these gets unparked

Take A first: self-healing has the clearest standalone justification and is the smallest. B is next, and needs corpus work before it can be validated at all. C, D and E are independent of each other and of the rest.