# Hop3 0.7 — deck source (editable content)

This is the plain-content source for `notes/slides/hop3-0.7-release.html`. Edit the text here for accuracy; I regenerate the slides from it faithfully.

- Correct any wording, number, command, or claim directly in place.
- Delete anything wrong; add anything missing. Whole slides can be cut or added.
- Terminal blocks (```…```) become the on-slide terminals; the commands must be real.
- The word/phrase after "→ highlight:" is the part rendered in the green accent colour on a title line.
- "Status:" tags become the coloured pills (supported / preview / landing).

Prose rules: no em-dash incises, no balanced "X, not Y" contrasts, no narrator.

---

## Resolved decisions (from your review)

1. **Framing / date.** 0.7 ships next week (not yet tagged). 0.8 follows by the end of July and completes the NGI grant. The deck now says "ships next week" and frames 0.8 as the NGI finale. I mapped the old "0.7.x tail" items to 0.8 for consistency; correct me if some are truly 0.7.x point releases.
2. **Toolchains: 10, verified.** Python, Node, Ruby, Go, Rust, Java, PHP, Elixir, Clojure, .NET, plus static sites.
3. **Apps: 20+ across four variants** (native / Docker / Nix hand-crafted / Nix-from-template). Kept.
4. **Email providers:** reframed as "bring your own TEM"; no provider names on the slide.
5. **Web UI stack:** dropped (a detail).
6. **Milestone table:** replaced with a positive "what NGI delivered" slide; the remaining finale work is framed as "completing in 0.8", with no partial/not-started counts.
7. **Upgrade demo:** uses `myapp` (the docs' own example) for the rollback story and real backup-id format; `edrix` stays for the happy-path status.
8. **Author:** Stefane Fermigier.

---

## 1 · Title

- Terminal top line: hop3@your-server:~   ·   release 0.7.0
- Terminal command shown: `$ hop3 deploy --app nextcloud   ✓ built · ✓ migrated · ✓ healthy · ✓ TLS`
- Badge: Ships next week
- Big title: Hop3 0.7        → highlight: 0.7
- Lede: The self-hosted PaaS that makes your deployments dependable. Release 0.7 adds safe upgrades with automatic rollback, email as a swappable backing service, reproducible Nix builds, and more. All on a single server.
- Footer left: Abilian · Apache-2.0 · hop3.cloud
- Footer right: NGI Zero Commons · github.com/abilian/hop3

---

## 2 · What Hop3 is

- Section tag: The platform
- Title: A sovereign PaaS on a single server        → highlight: on a single server
- Lede: Hop3 deploys and manages web apps the 12-factor way (build, deploy, secure, back up, upgrade) without a DevOps team, and without handing your data to a hyperscaler.

Four cards:
1. deploy — "git push or one command": Native, Docker, or Nix builds across ten language toolchains. No YAML.
2. services — "Backing services, attached": PostgreSQL, MySQL, Redis, and now email, provisioned and injected.
3. operate — "Automatic everything": Let's Encrypt TLS, backups, health checks, reverse proxy, resource limits.
4. control — "CLI · TUI · Web UI": A JSON-RPC core with a privileged-ops daemon at the root boundary.

Side panel ("since 0.6"):
- 0.7 is a robustness release in the NGI Zero Commons line; 0.8 completes the grant this month.
- The theme is trust. The platform verifies before it claims success, fails loud when something breaks, and never leaves a half-broken box behind a green checkmark.
- Pills: Simple · Secure · Sovereign

---

## 3 · Hop3 0.7 at a glance

- Section tag: What's new
- Title: Hop3 0.7 at a glance        → highlight: at a glance
- Lede: Six headline changes, each closing the gap between "it deployed" and "it actually works."

Six cards (number / label / title / text):
1. upgrades — Safe upgrades + rollback: Snapshot → redeploy → verify → auto-rollback on any failure.
2. email — Email backing service: One server backend (relay / catch / direct) that every app inherits.
3. alerts — Operator notifications: Emailed when a cert stops renewing or a deploy fails.
4. health — Content-aware checks: `[healthcheck].contains`, so a 200 alone is no longer "healthy".
5. diagnosis — Real failure cause: Failed deploys surface the actual error line, once, with a pointer to the full log.
6. reproducible — Pinned, reproducible Nix: nixpkgs pinned to a commit across every recipe, so the same toolchain resolves on any host.

- Footer: Full changelog: CHANGES.md → [0.7.0]   ·   email ships experimental

---

## 4 · Safe upgrades + rollback

- Section tag: Resilience · M3.2
- Title: Upgrade without holding your breath        → highlight: holding your breath
- Lede: Every app upgrade is a transaction: it snapshots first, verifies health after, and restores the snapshot itself if the build, a migration, or the health check fails.

Terminal (hop3 · app upgrade):
```
$ hop3 app upgrade --app myapp
✓ snapshot 20260707_120000_ab12cd created
✓ rebuilt · ran before-run migrations
✗ health check failed, rolling back…
✓ restored to 20260707_120000_ab12cd. App is up.

$ hop3 app rollback --app myapp --to 20260706_090000_9f3ac1
# a foreign backup id is refused (app-scoped only)
```

Three cards:
1. the app — "upgrade & rollback": upgrade is the safe redeploy a plain deploy lacks; rollback restores the most recent app backup on demand.
2. the server — "can't fake complete": The deployer confirms hop3-server actually answers before reporting success; otherwise it fails loud with the exact revert command.
3. proven — "upgrade-chain e2e": Install a baseline, then hop a version chain: green on Docker and a fresh Hetzner VPS, each version by its own installer.

---

## 5 · Email is a swappable backing service

- Section tag: Backing services · M3.1
- Title: Email is a swappable backing service        → highlight: swappable backing service
- Lede: Symmetric with the database addon: the operator picks a backend once, an app opts in by attaching an email addon, and apps always talk to a loopback SMTP endpoint, never the provider directly. Swap the backend without re-touching a single app.

Three backend cards:
1. relay — Status: supported — "Provider or smarthost": Point Hop3 at any transactional-email provider or corporate smarthost (bring your own). SASL+TLS to the submission port, DKIM auto-verify, and a deliverability pre-flight.
2. catch — Status: supported — "Dev sink": Captures every message and never sends it. Validated end-to-end: the safe default for staging and demos.
3. direct — Status: preview — "Your own MTA": Postfix delivers to recipients' MX and opendkim signs. Hop3 prints the SPF/DKIM/DMARC records to publish and never fakes "ready" over unpublished DNS.

Terminal (one line):
```
$ hop3 server email backend relay --smtp-host smtp.your-provider.com --from-domain example.com
# → 127.0.0.1:25 null-client queues and forwards; apps only ever see SMTP_HOST=127.0.0.1
```

- Footer: New in 0.7 · relay + catch validated end-to-end, direct in preview

---

## 6 · Fail loud, never lie

- Section tag: Ethos · robustness
- Title: Fail loud. Never lie.        → highlight: Never lie.
- Lede: The through-line of 0.7: a success message is a promise. When Hop3 can't keep it, the failure shows up where you look. A green checkmark never covers a broken box.

Four cards:
1. health — "A 200 alone isn't healthy": Content-aware checks (`contains`) mark a deploy healthy only when the app serves its own page. A placeholder or an error page fails the check.
2. alerts — "Broken things reach you": Opt in and get emailed on cert-renewal failures (before expiry) and failed deploys. Best-effort, and never masking the failure itself.
3. proxy — "No silent nginx reload": Admin-domain and TLS setup stop the deploy when nginx can't reload. A "complete" deploy never hides a domain nginx never picked up.
4. ops — "The right restart, every target": Restart and nginx reload pick the mechanism the target actually uses (systemd or supervisor), so a deploy can't silently keep serving old code.

- Footer: Errors are never silent   ·   no fake success · no silent skip

---

## 7 · One consistent surface, CLI to dashboard

- Section tag: Experience · M3.6 / M3.7
- Title: One consistent surface, CLI to dashboard        → highlight: CLI to dashboard
- Lede: A consistency pass gave every tool one set of verbs and flags. Unknown input now fails loud; the parser no longer drops what it doesn't recognize.

Cards:
1. cli — "Predictable by design": Space-separated commands, an implicit current app, the --app flag everywhere, aliases, did-you-mean, categorized help with an example on every command.
2. naming — "hop3-deploy-server": The developer deploy tool is renamed for consistency; follow-up hints now remember the selectors you typed, and unknown flags are rejected.
3. web ui — "Basic, clean, usable": The dashboard covers the core flows: app list, status, logs, addons, backups, env. Git-URL deploy and log streaming ride to 0.8.

Terminal (small):
```
$ hop3 app status --app edrix
RUNNING · 1 instance · https://edrix.example.com
# the deploy host doubles as the admin domain
```

---

## 8 · Security by boundary and design

- Section tag: Security · architecture
- Title: Security by boundary and design        → highlight: boundary and design
- Lede: A narrow root boundary, a firewall roadmap, and a plugin core: the machinery that lets many real apps share one server without stepping on each other.

Four cards:
1. rootd · ADR 041 — "Privileged-ops daemon": The operations that need root run through one small, audited daemon. The privilege boundary is a single narrow, reviewable seam (no broad sudoers).
2. LeWAF · ADR 050 — "Pure-Python WAF" — Status: landing: An OWASP-CRS engine: schema, SecLang compiler, engine plugin, and named networks are merged. The proxy-running slice lands in 0.8.
3. ADR 045 / auth — "Hardened and isolated": Fixed-port registry and network firewall; the June 2026 auth audit remediated; hop3.toml holds zero secrets.
4. Pluggy + Dishka — "Everything is a plugin": Builders, language toolchains, deployers, addons, proxies, and OS support: extend the platform without forking it.

---

## 9 · What NGI Zero Commons delivered

- Section tag: NGI Zero · deliverables
- Title: What NGI Zero Commons delivered        → highlight: delivered
- Lede: Five workstreams over the grant. Here is what 0.7 puts in your hands.

Six capability cards (each shipped, shown with a check):
1. Reproducible Nix: native and template builders across the toolchains, pinned to a commit; the runtime beta.
2. Email backing service: relay, catch, and direct backends behind one loopback endpoint, with operator notifications.
3. Safe upgrades: transactional app upgrade and rollback, plus a verified server upgrade that can't fake success.
4. Data safety: backups, restore, and cross-instance backup migration.
5. Security: the rootd root boundary, the June 2026 auth-audit fixes, and the OWASP-CRS WAF engine.
6. DX and reach: a consistent CLI, a usable Web UI, the nightly Test Lab, docs, 23 blog posts, and 68 screencasts.

- Footer: Completing in 0.8 by end of July (still NGI): WAF proxy activation, external security audit, and the benchmark paper.

---

## 10 · Real apps are the stress test

- Section tag: Proof · T4 / M1
- Title: Real apps are the stress test        → highlight: the stress test
- Lede: Every packaged app probes a different edge of the platform. We package them in four variants precisely because each one exercises a different layer.

Four stat cards:
1. 20+ — apps packaged across four variants: native, Docker, Nix, Nix-from-template.
2. 68 — screencasts recorded (33 demos + 35 tutorials), each a real run.
3. 10 — language toolchains, plus static sites and a signed app catalog.
4. 2× — reproducibility goal: rebuild to identical store paths (CI gate in 0.8).

Two cards:
1. reproducible — "Pinned today, hermetic next": nixpkgs is pinned to a commit across all recipes, so builds resolve the same toolchain on any host. Hermetic builds and a CI reproducibility gate land in 0.8.
2. coexistence — "Apps coexist, cleanly": Installing or destroying one app never touches another, and teardown leaves no leftover port, process, or config behind.

---

## 11 · The road to the NGI finish line

- Section tag: What's next
- Title: The road to the NGI finish line        → highlight: NGI finish line
- Lede: 0.7 ships next week. 0.8 completes the NGI Zero Commons grant by the end of July.

Left card — 0.8 · end of July (pill: completes NGI):
- WAF proxy activation: route app traffic through LeWAF, with OWASP Top-10 coverage.
- External security audit and an accessibility pass.
- Benchmark paper: control-plane memory, deploy latency, closure vs image size, cold-start, reproducibility.
- Nix runtime 1.0 and hermetic builds; an application gallery on hop3.cloud.
- The direct email backend promoted to supported.

Right card — Beyond NGI:
- Per-app email override; SES and provider sub-credentials.
- Encryption at rest across the addon secret stores.
- Agent model, SSO and identity, a monitoring dashboard, multi-server orchestration (JumpGATE), community marketplaces, and more.
- Pills: relay · catch · direct →

---

## 12 · Get Hop3

- Section tag: Get started
- Title: Run it on your own server        → highlight: your own server
- Lede: One command installs the server; one installs the CLI. Apache-2.0, all the way down.

Terminal (install):
```
# install the server (Debian/Ubuntu/Fedora/Rocky/Alma)
$ curl -LsSf https://hop3.cloud/install-server.py | sudo python3 -

# and the CLI on your laptop
$ hop3-install cli   → then   hop3 login --host your-server
```

Three cards:
1. docs — "hop3.cloud": Guides, CLI reference, tutorials by language, and the full ADR collection.
2. source — "github.com/abilian/hop3": Apache-2.0. Contribute code, docs, tests, or app packaging.
3. waf — "github.com/abilian/lewaf": The pure-Python OWASP-CRS WAF, a byproduct of the NGI0 work.

---

## 13 · Closing

- Terminal top line: hop3@your-server:~   ·   thank you
- Terminal command shown: `$ hop3 --version   Hop3 0.7.0: sovereign, reproducible, dependable`
- Badge: Digital sovereignty, made practical
- Big title: Self-host without the DevOps team.        → highlight: without the
- Lede: Built by Abilian · funded in part by the NGI Zero Commons Fund (NLnet and the European Union).
- Footer left: Stefane Fermigier · sf@abilian.com
- Footer right: hop3.cloud · github.com/abilian/hop3 · Apache-2.0
