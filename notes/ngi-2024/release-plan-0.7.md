# Hop3 0.7.0 Release Plan — Final NGI Version

**Target:** 0.7 cut the week of 2026-06-22; the remaining NGI deliverables land in 0.7.x point releases over the following weeks.
**Theme:** Ship the remaining subsystem features in the 0.7 cut (WAF, email, a basic Web UI, Nix beta gaps, pinned-nixpkgs reproducibility); finish the longer-tail deliverables (benchmarks + paper, Nix runtime 1.0, app validation, external security review) as 0.7.x.
**Depends on:** 0.6.0 released (2026-06-20)
**Last updated:** 2026-06-22 — reconciled against the full annex (T1–T5); scope split into the 0.7 cut and 0.7.x point releases.

## Goals

0.7 is the final NGI deliverable release. Every milestone from the project plan (#2024-04-365) is either complete, scheduled into the 0.7 cut, or carried into a 0.7.x point release with a documented, NGI-agreed disposition. The 0.5 cycle made the platform operable; 0.6 published the documentation and design record; 0.7 (this week) closes the remaining subsystem features, and the 0.7.x series finishes the deliverables that have a genuine longer tail — quantitative benchmarks + the paper (M5.3), the Nix runtime 1.0 cut (M2.3), production-traffic app validation (M4), and the external security review (M3.8). None of those four blocks the 0.7 tag; together with the 0.7 cut they complete the NGI commitment.

This plan deliberately does not pretend ~40 person-days of remaining work fit into the cut week. It separates what ships now from what ships in the following weeks, so the NGI reviewers see an honest, sequenced completion rather than a slip.

## Scope split

**In the 0.7 cut (this week):** WAF (M3.5), email addon (M3.1), a basic/clean/usable Web UI (M3.7), one or two internal security-audit rounds + engaging the audit firm (M3.8), the actual Nix-runtime-beta gaps (M2.2), the upgrade-command scope once confirmed (M3.2), publishing the 68 screencasts (M5.6), and pinning nixpkgs (the high-value, low-effort reproducibility win, M1/M2).

**Deferred to 0.7.x (following weeks):** benchmarks + final paper (M5.3, next week), the Nix runtime 1.0 cut after the 20-app testing pass (M2.3 → 0.7.x or 0.8), the last manual app testing/cleanup pass + production-traffic validation and report finalisation (M4), the external security review itself (M3.8, after the internal rounds), and the full hermetic-build reproducibility work (M1/M2).

## NGI Milestone Completion Matrix (full annex, T1–T5)

Every annex milestone, with status and where it lands, so a reviewer can reconcile the whole project plan (#2024-04-365). Status as of the 0.6 cut.

| Task | Milestone | Status | Lands in |
|------|-----------|--------|----------|
| **T1** Nix builders | M1.1 Native Nix builder | ✅ done (0.5) | shipped; pin-nixpkgs in 0.7, hermetic in 0.7.x |
| | M1.2 Nix template builders (Py/Node/Ruby/Go/Rust/Java) | ✅ done (0.5) | shipped; reproducibility as above |
| **T2** Nix runtime | M2.1 Spec & PoC | ✅ done (0.5) | shipped |
| | M2.2 Beta implementation | ◐ partial | **0.7** — close the actual remaining gaps |
| | M2.3 Final "1.0" | ○ not started | **0.7.x / 0.8** — after the 20-app testing pass |
| **T3** Security & resilience | M3.1 Backing services | ◐ partial | **0.7** — email/SMTP addon (storage/DB/cache shipped) |
| | M3.2 Upgrades + migrations | ◐ partial | **0.7** — scope to confirm (Alembic works) |
| | M3.3 Backups + migration tests | ✅ done (0.6) | shipped |
| | M3.4 Testing framework + canary | ✅ done | shipped |
| | M3.5 Firewalls + WAF | ◐ partial | **0.7** — WAF (ADR 050, LeWAF): compile slice merged; proxy/nginx/bans/tests remain |
| | M3.6 CLI | ✅ done (0.5–0.6) | shipped |
| | M3.7 Web UI | ◐ partial | **0.7** — basic, clean, usable (not production-grade) |
| | M3.8 Security audit + a11y scan | ◐ partial | **0.7** internal rounds + engage firm; **0.7.x** external review |
| **T4** Packaged apps | M4.1–M4.4 (20 apps + reports) | ◐ partial | **0.7.x** — 20+ apps done; last test/cleanup + production validation |
| **T5** Dissemination | M5.1 Website/blog | ✅ done | shipped (23 posts) |
| | M5.2 Documentation | ✅ done (0.6) | shipped |
| | M5.3 Technical report / paper | ◐ partial | **0.7.x** — benchmarks + paper next week |
| | M5.4 Conference | ✅ done | shipped (OW2Con 2025/2026, OSXP 2025) |
| | M5.6 Videos/screencasts | ◐ partial (nearly done) | **0.7** — 68 recorded, in review; publish this week |

Tally: **9 done, 10 partial, 1 not-started** of the 20 named milestones (the annex skips M5.5).

## In the 0.7 cut (this week)

### Firewall / WAF integration (M3.5)

The network-level firewall and fixed-port registry shipped (ADR 045, Final). The L7 WAF design is **ADR 050 (LeWAF)** — Abilian's pure-Python, OWASP-CRS engine (Coraza kept as a future alternative behind the same `WafEngine` interface). The **policy-compilation slice is merged** (branch `feat/waf-integration`); what remains for the cut is the **proxy-running slice** plus end-to-end wiring. Still the largest single item in the cut, but the foundation is in.

Done (merged):

- [x] ADR 050 written (design + deliberately-minimal v1 scope)
- [x] `[waf]` / `[[waf.gate]]` / `[[waf.tuning]]` hop3.toml schema, with compile-before-commit validation
- [x] Declarative-policy → SecLang compiler (`hop3/waf/compiler.py`); pluggable `WafEngine` protocol + `get_waf_engines()` hook
- [x] LeWAF engine plugin writing a per-app `<app>.conf` (`plugins/waf/lewaf/`); unit tests
- [x] Named networks for gate conditions: `orm/network.py` + `hop3 network list/add/rm` + Alembic migration

Remaining (the proxy-running slice):

- [ ] LeWAF proxy lifecycle — start/stop/reload `lewaf-proxy` (the `hop3-server[waf]` optional extra; lazy `lewaf` import)
- [ ] nginx integration — route app traffic through the WAF proxy; activate on deploy, remove on destroy
- [ ] L7 bans (detect → score → 403) per ADR 050 §4
- [ ] OWASP Top 10 tests (SQLi, XSS, path traversal at minimum) + a false-positive / per-app-exemption pass
- [ ] Document `[waf]` in the admin guide

### Email addon (M3.1) — experimental

Relay through the operator's existing provider; Hop3 never runs a mail server (deliverability, IP reputation, and abuse make it a losing game, and clouds block outbound port 25). The design separates two concerns: the **transport** (how mail leaves — SMTP submission credentials, which every provider exposes, so one generic SMTP path covers them all without per-provider code) and the **sending identity** (the verified From-domain — once a domain is authenticated with SPF/DKIM/DMARC, any address on it sends for free, so the unit to provision is the domain, not the address). **This surface is experimental: it ships marked as such in the CLI, the changelog, and the docs, and may change after real use** — the transport/identity split, the command shape, and named-provider profiles are all tentative. To deliver for NGI this week the 0.7 cut keeps the smallest useful slice (per-app SMTP credentials, no server-level transport or provider profiles yet); the refinements that the model implies are tracked under 0.7.x below.

Firm 0.7 (the minimal, shippable slice):

_Status (2026-06-22): the full firm-0.7 slice is implemented and tested — the addon, both CLI verbs, the superset injection, the experimental banner, domain-boundary validation, the `--smtp-password` stdin/file input (ADR 036), the SPF/DMARC DNS pre-flight, and the docs (`docs/src/guides/addons.md`) — across `plugins/email/`, `tests/a_unit/test_email_addon.py`, and the `hop3-cli` secret-input tests; full gate green (`make lint` + `make test`). Remaining (not firm-0.7): an optional SMTP-auth pre-flight on `create`, a real-deploy attach test, and per-provider exact-DKIM/SPF auto-verification (rides the 0.7.x provider profiles)._

- [x] `hop3 addon email create <name> --smtp-host <h> --smtp-port <p> --smtp-user <u> --smtp-password <pw> --from <addr>` — per-app SMTP submission credentials (works with any provider), stored in the existing `addons/email/<name>.json` store (0600, then Fernet-encrypted into the per-app credential on `attach`, same as every other addon); `attach`/`promote`/`detach` inherited from the addon model, so no new credential machinery. (A type-scoped verb, like `addon s3 …`, because the generic `addon create` cannot carry type-specific flags; the generic `addon create email` path fails loud and points here.)
- [x] Inject one source of truth in the spellings real frameworks actually read (mirroring the S3 addon's `S3_*`/`AWS_*` aliasing) so it works beyond Node: `SMTP_HOST`/`SMTP_PORT`/`SMTP_USER`/`SMTP_PASSWORD`/`SMTP_FROM`/`SMTP_TLS`, an `SMTP_URL` (`smtp://…:587`, `smtps://…:465`), Django `EMAIL_*`, and Flask `MAIL_*`. Default to 587/STARTTLS. (A bare `SMTP_*` set alone reaches almost no stock framework — Django wants `EMAIL_*`, Flask wants `MAIL_*`, Rails/WordPress read no env at all.)
- [x] Deliverability is a fail-loud pre-flight, never a silent claim: `create` and `addon email status` run a DNS check that auto-verifies SPF and DMARC for the From-domain (via `dig`; a missing resolver reports "unverified", never a fake "OK"), surfaces the missing records to publish, and never reports "ready" over missing/unverified DNS. DKIM and the exact per-provider SPF include are shown as guidance — auto-verifying those needs the named-provider profiles (0.7.x).
- [x] Document in `docs/src/guides/addons.md` with an explicit "experimental, subject to change" note, and the one-line Rails-initializer / WordPress-SMTP-plugin maps that env injection alone cannot cover (Rails and WordPress read no SMTP env).
- [x] On success, `addon email create` (and `addon email status`) print a one-line `⚠ experimental: this command's surface may change` banner, so the caveat appears at the point of use, not only in the docs.

Out of scope (M3.1): inbound / IMAP / MX, and running any MTA-to-the-internet. Sending *as* `support@example.com` never means Hop3 hosts that mailbox — replies follow the domain's existing MX.

### Web UI — basic, clean, usable (M3.7)

The NGI deliverable is a *basic* web UI for non-technical users, not a production-grade dashboard. The dashboard already exists (9 controllers, 17 templates); 0.7 makes it clean and usable — a visual tidy-up and a check that the core flows (app list/status/logs, addon and backup management, env editing) work end to end. Git-URL-deploy, real-time log streaming, the formal a11y scan, and the mobile-responsive pass are nice-to-haves that can ride into 0.7.x if time is short.

- [ ] Visual tidy-up: consistent layout, navigation, and states (loading/empty/error)
- [ ] Verify the core CRUD flows work end to end from the UI
- [ ] (If time allows) wire the Git-URL deploy field that is currently disabled
- [ ] (If time allows) basic in-browser log streaming

### Security — internal audit rounds, engage the firm (M3.8)

The four internal-audit code fixes shipped in 0.5; credential hardening continued through 0.6 (single-source `HOP3_SECRET_KEY`, ADR 048). 0.7 runs one or two more internal rounds before engaging the external firm — so the external review doesn't catch obvious issues. The external review itself is 0.7.x.

- [ ] One or two more internal audit rounds; fix findings
- [ ] Engage the external security-audit firm (the review runs in 0.7.x)
- [ ] Document the security model in the admin guide

### Nix runtime beta — close the real gaps (M2.2)

The beta runs end to end for the 34 + 31 Nix apps. 0.7 closes only what is *actually* missing rather than vague polish.

- [ ] Recover or formally defer the remaining bad apps (HedgeDoc, CryptPad) — with the reason recorded
- [ ] Fix any concrete beta gaps surfaced by the 20-app testing pass

### Upgrade mechanism (M3.2) — confirm scope

Hop3-server's own Alembic schema migrations exist and work (they run on upgrade; the venv is preserved; pre-Alembic databases are adopted). The annex deliverable is "seamless platform *and application* updates with safe data migrations." Open question: what, beyond the working migrations, is genuinely required? Candidate scope below — confirm before building, as part of this may already be satisfied by migrations + redeploy.

- [ ] Confirm whether a production `hop3 server upgrade` (pull + migrate + restart) is needed beyond the current path -> OK for "hop3 server upgrade". This assumes admin right. Non-admin users can't run this command.
- [ ] Confirm whether app-level upgrade orchestration is more than the existing redeploy -> YES. Upgrading could mean: (1) backup data, (2) backup code, (3) upgrade and run the upgrade script (app-specific - like "alembic upgrade head"), (4) rollback in case of an error, (5) allow the operator to rollback to the previous state (using the backups) using the CLI or the Web UI.
- [ ] Rollback-on-failure and an admin-guide upgrade procedure if the above are in scope -> Cf. supra.

### Screencasts — publish (M5.6)

The deliverable was two narrated walkthroughs; it is now massively over-delivered. `scripts/record_screencasts.py` recorded **68 asciinema screencasts** (33 executable demos + 35 tutorials) into `screencasts/`, each a real run of a demo/tutorial. Currently under review; publishing this week.

- [x] Record the demo + tutorial corpus as asciicasts (68 in `screencasts/`)
- [ ] Review pass over the 68 recordings
- [ ] Upload to asciinema.org and capture the URLs for the NGI report (`--upload`)
- [ ] Publish to the website + PeerTube; embed in the getting-started docs
- [ ] (Optional polish) the two narrated walkthroughs — "Zero to Running App in 5 Minutes" and "Dashboard Tour"

### Pin nixpkgs — the reproducibility quick win (M1/M2)

NLNet/NGI fund reproducibility/sovereignty work and will inspect the Nix implementation closely. Today every expression uses the unpinned `import <nixpkgs> {}` against a moving channel, so builds are not reproducible across hosts/dates. Pinning nixpkgs is cheap and is the single highest-value reproducibility win — so it lands in the 0.7 cut; the deeper hermetic-build work is 0.7.x (see below).

- [x] Ship one in-tree pinned nixpkgs input — a pinned rev + sha256 (`fetchTarball`) lives in the nix-gen `templates/base.py` (`NIXPKGS_REV` / `NIXPKGS_SHA256` / `PINNED_NIXPKGS_HEADER`), updatable in one place.
- [x] The generator emits the pinned import — all 9 nix-gen templates render `import (fetchTarball {…}) {}` instead of `<nixpkgs>` (one shared pin in `templates/base.py`), verified via `nix-instantiate`; nix-gen tests + full gate green.
- [x] Hand-crafted expressions pinned — all 34 `apps/real-apps-nix/*/hop3.nix` inline the same pin. Each is its own build context (no shared import possible), so the pin is duplicated per file; updating it means editing `base.py` + a sed across the 34. Verified: all 34 parse, and Python / prebuilt-binary / PHP samples evaluate to a `.drv` with the pinned nixpkgs.
- [ ] Stop the installer relying on `nix-channel --update`

### Release mechanics

- [ ] Add the `[0.7.0]` changelog entry
- [ ] Bump version to 0.7.0; tag v0.7.0
- [ ] Blog post: "Hop3 0.7"

## Deferred to 0.7.x (following weeks)

Each item below is an NGI deliverable that is genuinely not a blocker for the 0.7 tag and finishes in a near-term point release, with a documented disposition.

### Benchmarks + final paper (M5.3) — 0.7.x, next week

Plan at `local-notes/plans/05-paper-benchmarks.md`. This is the longest single chain (harness → measurements → write-up, ~8–9 days) and is explicitly scheduled for the week after the 0.7 cut.

- [ ] Comparison baseline (Dokku + K3s, or Docker Compose + bare uWSGI)
- [ ] B1 control-plane memory (0/10/28 apps); B2 deployment latency by build strategy; B3 Nix closure vs Docker image size; B4 cold-start latency; B5 bit-for-bit reproducibility across rebuilds
- [ ] Integrate results into the paper's evaluation section; submit; archive on HAL regardless of venue outcome

### Nix runtime 1.0 (M2.3) — 0.7.x / 0.8, after app testing

Tweak after the 20-app testing pass, then cut 1.0.

- [ ] Documentation polish: the `hop3.nix` / `[nix]` reference and the reproducibility tiers
- [ ] CI: `make test-nix` in the nightly Test Lab with a persisted `/nix/store`
- [ ] Release notes; the 1.0 cut

### Full Nix reproducibility — hermetic builds (M1/M2) — 0.7.x

Pinning nixpkgs (in 0.7) removes the moving-channel problem. The remaining work makes the dependency builds hermetic so the result is reproducible from source, matching ADR 008's tier table. (Source-build conversion was done earlier; see `plan-source-builds.md`.)

- [ ] Hermetic dependency builds for the flagship apps: convert the `__noChroot` Python/PHP/Node paths to fixed-output derivations (uv2nix / pip FOD, composer2nix, pnpm `fetchDeps`); where infeasible, lock the dep set (exact versions + hashes) and label the app as an explicit non-hermetic tier
- [ ] Fail loud on floating deps: the python-venv/node/php templates refuse to generate when language deps are unversioned (no silent degradation)
- [ ] Reproducibility CI gate: rebuild a representative app twice (ideally on a second arch) and assert identical store paths for the pure-Nix tier; exclude and label the `__noChroot` tier
- [ ] Adopt `nix build` / flakes for a verifiable, lock-pinned input set; declare substituters / trusted keys in-tree
- [ ] Update ADR 008 tiers + per-app tier labels (closing the unchecked DoD items in `plan-source-builds.md`, incl. aarch64)

### Packaged apps — final pass + production validation (M4.1–4) — 0.7.x

20+ apps are already configured and tested across the four variants; 20 standalone experience reports exist under `notes/experience-reports/` (Draft). Not a blocker for 0.7.

- [ ] Last manual testing + cleanup pass over the 20+ apps
- [ ] Deploy several apps to production with real traffic; finalise the experience reports from that experience
- [ ] Application gallery page on hop3.cloud

### External security review (M3.8) — 0.7.x

- [ ] The external firm's review runs; address feedback
- [ ] Accessibility scan (with the M3.7 polish)

### Email addon — refinements (M3.1) — 0.7.x

The 0.7 cut ships a deliberately minimal, experimental email addon (above). The refinements the transport/identity model implies, deferred so the cut ships this week and so the surface can settle after real use:

- [ ] **Server-level shared transport** — set provider credentials once (`hop3 server email …`) and have per-app email addons reference them, instead of repeating SMTP creds per app (mirrors the Postgres admin-config → per-app-resource pattern).
- [ ] **Named-provider profiles** — declarative profiles (SMTP endpoint + API-key var + DNS-record templates) for Resend / Postmark / Brevo / Mailgun / SES / Scaleway TEM, community-extensible; a pluggy plugin only for the few needing real logic (SES IAM→SMTP-password derivation; HTTP-API mode on port 443 for networks that block 587/465). EU-sovereign providers (Brevo, Mailgun-EU, Scaleway TEM) first-class.
- [ ] **Local relay** — an opt-in host Postfix null-client on `localhost:25` + `/usr/sbin/sendmail` forwarding to the configured transport, so WordPress / PHP `mail()` / cron / Rails-without-config work with zero injection. Feasible precisely because Hop3 is no-Docker / single-server (every container-based peer lacks this). Postfix, not msmtp (spool + retry; msmtp drops on a transient outage = silent loss). Treat the shared MTA as a managed coexistence resource: per-app envelope sender, teardown never touches it, fail loud if no transport is configured.
- [ ] **Dev catcher** — a Mailpit backend mode so the same app code captures mail in dev and relays it in prod.
- [ ] **Platform notifications** — reuse the transport for Hop3's own cert / deploy / outage alerts (ties into the TLS + monitoring roadmap).
- [ ] **Per-app sub-credentials** — a distinct provider key per app for reputation isolation and revoke-one-app, where the provider supports it.

### Migration series (T5) — 0.7.x

- [ ] Publish the 21 drafted "migrating from X" posts (`local-notes/blog/`) on a staggered schedule

### Final NGI report

- [ ] The final NGI project report, once the 0.7.x deliverables above are complete

## Out of scope for the NGI project (post-NGI)

Valuable but not NGI commitments: the agent model (ADR 017), SSO / identity management, a monitoring / metrics dashboard, and multi-server / distributed deployment (JumpGATE).

## Effort estimate

**0.7 cut (this week):**

| Area | Days |
|------|------|
| WAF integration (M3.5) | 5-7 |
| Email addon (M3.1) | 2-3 |
| Web UI — basic, clean, usable (M3.7) | 2 |
| Internal audit rounds + engage firm (M3.8) | 2 |
| Nix beta gaps (M2.2) | 1-2 |
| Upgrade scope (M3.2, once confirmed) | 1-3 |
| Screencasts — review + upload + publish (M5.6) | 1-2 |
| Pin nixpkgs (M1/M2) | 1-2 |
| Release mechanics | 1 |
| **0.7 cut total** | **~16-24 days** |

**0.7.x (following weeks):**

| Area | Days |
|------|------|
| Benchmarks + final paper (M5.3) | 8-9 |
| Nix runtime 1.0 (M2.3) | 3 |
| Full Nix reproducibility — hermetic (M1/M2) | 4-6 |
| App final pass + production validation + reports (M4) | 4 |
| External security review (M3.8) | 2 |
| Migration-series publishing (T5) | 1 |
| **0.7.x total** | **~22-25 days** |

## Risk register

| Risk | Mitigation |
|------|------------|
| WAF (the big 0.7 item) overruns the cut week | Ship a conservative default rule set; treat per-app exemption tuning as 0.7.x; the WAF can itself slip to early 0.7.x if needed |
| Benchmarks reveal Hop3 is slower than a baseline | Report accurately; the paper's contribution is the architecture and reproducibility story, not raw speed |
| External review surfaces issues late | The internal rounds before engagement reduce this; address findings in 0.7.x |
| Production deploys uncover blocker bugs | Triage: fix critical, defer the rest with notes |
| Reproducibility claims questioned at review | Pin nixpkgs in 0.7 (removes the worst gap); ADR 008 already documents the tiers honestly; hermetic work + CI gate land in 0.7.x |

## Definition of Done — 0.7 (the cut)

- [ ] WAF integrated with the OWASP Core Rule Set, per-app toggle (M3.5)
- [ ] Email addon shipped (M3.1, experimental — flagged subject-to-change in CLI/docs/changelog)
- [ ] Web UI is basic, clean, and usable; core flows work from the UI (M3.7)
- [ ] One or two internal audit rounds done; the external firm engaged (M3.8)
- [ ] Nix-runtime beta gaps closed or formally deferred (M2.2)
- [ ] Upgrade scope missing pieces shipped (M3.2)
- [ ] The 68 screencasts reviewed, uploaded, and published (M5.6)
- [ ] nixpkgs pinned in-tree; the generator no longer emits unpinned `import <nixpkgs> {}` (M1/M2)
- [ ] v0.7.0 tagged and announced

## Definition of Done — 0.7.x (NGI complete)

- [ ] Quantitative benchmarks run and integrated; paper submitted and archived (M5.3)
- [ ] Nix runtime 1.0 cut (M2.3)
- [ ] Hermetic dependency builds + reproducibility CI gate green; ADR 008 tiers updated (M1/M2)
- [ ] Final app testing/cleanup pass + production deployments with finalised experience reports (M4)
- [ ] External security review addressed; accessibility scan done (M3.8)
- [ ] Migration series published (T5)
- [ ] Final NGI project report submitted
