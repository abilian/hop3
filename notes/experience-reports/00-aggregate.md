# Aggregate Experience Report: Packaging 20 Applications for Hop3

**Status:** Final (0.7) — the per-app reports are `report_status: final`; corrections continue against a published baseline rather than an open draft.
**Last updated:** 2026-07-31

## Overview

Twenty open-source applications are packaged for Hop3 and published in the signed catalog. Each is packaged for up to three build paths (native, hand-written Nix, and Nix generated from a template) and each carries a `check.py` that signs in through the application's own authentication and confirms a wrong password is refused.

Packaging is system-validation work. Every application was chosen to stress a different edge of the platform, and the per-app reports record which edge; where an app merely confirmed existing behaviour, its report says so without inventing a contribution.

The instrument matters more than the count. "Passing" here means an authenticated sign-in through the application's own surface, with a wrong password refused. That bar was adopted only after a majority of the corpus was found to clear the previous one (HTTP 200) while being impossible to log into. Read against that bar, five of these twenty were at one point serving with no usable credential at all, and every instrument the project then had reported them working.

## Application coverage

The table is derived from the reports' own headers, which `hop3-tools catalog reports` checks against the recipes, so it cannot drift from them silently. `n/a` means there is no recipe for that variant. Docker is not listed: recipes exist for most of these applications and none has been measured at this bar, so the report does not claim the variant.

| App | Language | Database | Native | Nix | Nix-gen |
|-----|----------|----------|--------|-----|---------|
| BookStack | php | mysql | pass | pass | pass |
| Bugsink | python | postgres | pass | pass | pass |
| Dolibarr | php | postgres | pass | pass | pass |
| Easy!Appointments | php | mysql | pass | n/a | **fail** |
| Forgejo | go | postgres | pass | pass | pass |
| Gitea | go | postgres | pass | pass | pass |
| Invoice Ninja | php | mysql | pass | pass | pass |
| Isso | python | none | pass | pass | pass |
| Kanboard | php | mysql | pass | pass | pass |
| Keycloak | java | postgres | pass | pass | pass |
| LimeSurvey | php | postgres | pass | pass | pass |
| Matomo | php | mysql | pass | pass | pass |
| Mattermost | go | postgres | pass | pass | pass |
| Miniflux | go | postgres | pass | pass | pass |
| Nextcloud | php | mysql | pass | n/a | pass |
| Paheko | php | none | pass | pass | pass |
| Radicale | python | none | pass | pass | pass |
| Uptime Kuma | node | none | pass | n/a | n/a |
| Vikunja | go | postgres | pass | pass | pass |
| WordPress | php | mysql | pass | n/a | pass |

**Languages:** php (10), go (5), python (3), java (1), node (1)
**Databases:** postgres (9), mysql (7), none (4)

Five applications were packaged, reported, and later dropped from the corpus: Adminer, Focalboard, Grafana, Jenkins and Wiki.js. Their reports are kept under `withdrawn/`, marked `report_status: withdrawn`, because the packaging work was real even though the applications are no longer advertised.

## What the numbers mean, and what they do not

**Native is the variant the catalog publishes, and it is 20 of 20** on a complete recorded run (2026-08-01). Earlier drafts of this report declined to claim it: the runs before this one topped out at 19 of 20, every application had been seen green at some point, and no single run had been all-green *and* recorded. A claim resting on "each of them passed at some point" is a weaker object than one resting on a run that can be pointed at, so the number waited for the run. This is that run.

**Nix-gen is 18 of 19** and **hand-written Nix is 15 of 16**, on the same run. Two failures, and they are not the same kind of thing.

Easy!Appointments (nix-gen) builds its login form in JavaScript, so neither the HTTP check nor the browser harness can complete a sign-in; its report says so instead of passing it on the strength of a bootstrap that reports success. That failure is stable and understood.

Bugsink (hand-written) did not install, and the reason is a recipe defect rather than a timing one. Its gunicorn master bound the port eight seconds in and then no worker ever booted — no "Booting worker" line, no traceback, a silent hang for the remaining 232 seconds. The platform's own diagnostic said as much at the point of failure ("the server bound its socket but no worker is serving"), which is why the three successive start-timeout increases this recipe has accumulated never helped: the timeout was never what was wrong.

The structural difference from the two variants that pass is that **the hand-written recipe runs Bugsink as one process, and Bugsink is two.** Its siblings each migrate a second database (`migrate --database=snappea`) and declare a second worker (`[run.workers] snappea = "bugsink-runsnappea"`), both carrying comments explaining that the application does not work without them. The hand-written recipe does neither, while generating its configuration from the same `--template docker` that assumes them. That is a defect whether or not it proves to be this hang's mechanism, and it is the only structural difference between the recipe that hangs and the one that starts in 28 seconds.

The hand-written family held the corpus's only all-green artefact until this run; native holds it now.

Both families were measured for the first time that week, and the first measurement of the hand-written corpus **failed all sixteen applications**, three days after a deploy-oriented matrix scored the recipes in its scope 15 ok, 0 fail. Two instruments, one corpus, opposite verdicts. That is the result the sign-in bar exists to produce. The older instrument could not see what it was reporting green; the same corpus reached 16 of 16 within a day.

### What the first measurement found

**Five of the sixteen were serving with no usable credential**, in five different ways. Radicale's `[auth] type` defaulted to `none` and nothing set it, so every calendar and address book was public. Isso's config had no `[admin]` section, so its moderation dashboard was served disabled. Miniflux and Keycloak each shipped a literal `changeme` (an identity provider among them), so the deployed instance had an administrator whose password is in this repository while the operator held one that did not work. LimeSurvey installed itself as `console.php install admin password123` with the result discarded by `2>/dev/null || true`: a published password *and* a failed install reported as success, in one line.

No status assertion and no content assertion can distinguish any of those from a working deployment. The argument is not hypothetical.

The remainder divide cleanly: two forges carried a *native* `create` command naming `./gitea`, a path with no meaning in a Nix layout; three carried secrets minted by a wrapper that re-evaluates them on every start; three were served straight out of the read-only store and so could never be installed at all; and the rest had no first-run bootstrap, because these recipes predate ADR 056 and the variant generator grafts an identity they cannot honour.

### One methodological finding

Every application in this corpus exists in two to four packagings, and the fastest route to a defect in one of them is a diff against a packaging that already passes. The last four hand-written failures each took a single attempt once that was the method, having resisted several rounds of reasoning from symptoms.

The wrong theories are kept because each would have sent someone into the platform after a defect that is not there: a reverse-proxy misconfiguration (Matomo actually needed the `core:update` both working variants run), a version skew (`nix eval` says nixpkgs ships the *same* Vikunja the template variant compiles), and PHP's built-in server mismatching responses under concurrency (every working variant uses `php -S` too). Reading the redirect target, the log line, and the working recipe would each have been quicker than any of them.

**Docker is out of scope for this report.** Recipes exist for most of these applications and no run has ever measured one at the sign-in bar, so the corpus has nothing to say about them. Earlier versions of these reports recorded Docker as "Passing", which is the specific rot this format exists to prevent: that status was asserted, not observed. Rather than carry an empty column, the variant is not claimed at all — and on the evidence above, whoever measures it first should expect to find things rather than confirm them.

## The bar, and why it moved

For most of this corpus's life, "passing" meant the application deployed and answered HTTP 200. That bar was retired after a majority of the catalog was found to clear it while being impossible to log into: apps served their login page perfectly and rejected every credential. Some of those failures were the platform's, some the recipes', and one was the checking library posting an empty form body: the same symptom for all three.

Reports now name the bar they were verified at, in a header field the checker reads:

| Bar | Meaning |
|-----|---------|
| `http-status` | returned 200; **not sufficient** for a catalog app |
| `http-content` | served its own content (a `contains` assertion) |
| `authenticated` | signed in through the app's own auth; a wrong password was refused |

An advertised application may not be reported `final` on anything less than `authenticated`, and the checker enforces it.

One gap remains open at the platform level: `[healthcheck].contains` is declared by no recipe in the corpus, and a deploy currently treats any status line as "serving". So the "App is now running" a deploy prints is satisfied by a 500. Until that changes, a deploy's own report of success is a weaker claim than these reports are.

## Recurring technical findings

The per-app reports carry the detail; these are the patterns that showed up in more than one.

**An app's binary is rarely named after the app, and never the same in two packagings.** `buildGoModule` names it after the module path element, so a source build gives `forgejo.org`, `miniflux.app`, `api`. nixpkgs names the same three `gitea`, `miniflux`, `vikunja`; its Mattermost derivation ships no `mmctl` at all, though every `mmctl --local` in that app's documentation assumes one. `$out/bin` holds only the generated wrapper, which execs one fixed subcommand, so putting it on `PATH` does not help; `${pkg}` is the stable binding for the application's own derivation. A command copied from a sibling recipe fails differently, without working, and `nix eval` on the pinned nixpkgs settles the question in seconds.

**A credential is not injected until something maps it.** Hop3 generates an administrator password, stores it encrypted, and injects `HOP3_ADMIN_*`. An application reads whatever *it* reads, and the mapping is the recipe's job (`[env.computed]`). Where the mapping was missing, the recipe usually still carried a literal default, so the deployed application had an administrator whose password was published in the repository, while the operator was handed one that did not work. The smoke test reported only the second half of that. Four recipes were in this state.

**A secret evaluated by the wrapper is a secret that rotates.** Values in `[nix.env-exports]` are shell expressions re-evaluated on every start. Several recipes minted signing keys there with `$(head -c 32 /dev/urandom | base64)`, which silently invalidates every session on restart and, for the forges, makes 2FA secrets and stored credentials undecryptable. Generated-once `[env]` secrets are the mechanism; the shell is not.

**The generated wrapper is not the only thing that runs the app's code.** `[run] before-run` and the `[admin]`/`[probe]` create commands execute directly. Anything that lives only in the wrapper (`LD_LIBRARY_PATH` from `nix-runtime-libs`, a composed `DATABASE_URL`) is absent there, and the failure looks like a broken application, not a missing environment.

**PHP `__DIR__` resolves symlinks**, so a Nix store path reached through one lands back in the read-only store. `needs-writable-dir` copies the tree instead, and the copy's *timing* was the single largest cause of nix-gen failure. It happened when the app started, which is after `before-run`, so any application whose bootstrap needs its own code found an empty directory. Materialising it at deploy time, ahead of the first `before-run` command, moved six applications at once.

**An application's public address is not the address it binds.** Four recipes pinned theirs to `http://localhost:8080` (three in `[nix.runtime-env]`, baked into the wrapper at build time) and one built it by hand as `http://${HOST_NAME}`, right host, wrong scheme. The consequences differ (a Vue frontend calling the visitor's own machine; a Laravel redirect loop; a Keycloak console whose sign-in redirect points nowhere; a JavaScript form posting over http from an https page) and the shape is identical: the server side is unaffected, so every status and content assertion passes while a browser is shown nothing usable. `HOP3_PUBLIC_URL` is injected once the hostname is settled and reaches config files, `before-run` and `create`; `make validate` now rejects a hand-built public URL in any build-time table.

**A git tag is not a release.** Paheko vendors the KD2 framework into its release tarball without committing it; Easy!Appointments' tag omits both its minified assets and its `vendor/` tree. `fetchFromGitHub` on the tag produces a package missing part of the application, and the failure surfaces at runtime as a missing `require_once`, not at build time.

**A setting that lives in a shell script does not survive repackaging.** `DISABLE_REGISTRATION = true` sat in the native recipes' `scripts/setup-config.sh`, and no Nix variant carries a `scripts/` directory, so all four Nix forge builds put an internet-facing Gitea or Forgejo online on which the first visitor could register. It shipped for as long as those variants existed. **The sign-in bar does not catch it**: an application with open registration signs in perfectly and refuses a wrong password. The bar is a floor, and a security posture that lives only in a file one packaging happens to carry is not a posture.

**A bootstrap CLI's exit code is not its outcome.** Gitea and Forgejo print `admin user create`'s refusal and exit 0; Dolibarr's install steps do the same; Vikunja's `user` command answers an unknown subcommand with usage text and exit 0, so calling one that does not exist is a silent no-op. Every `create` in this corpus now verifies the account exists (by listing it, or by querying the row), because the platform's own "admin created" message is a promise it cannot otherwise keep.

**A read-only store is not a place an application can be installed.** Three recipes served straight out of `$out`, which means no schema, no config, no uploads and no account: the app deploys, starts, answers HTTP, and cannot be signed into. The failure presents as an application-level message ("please run setup", "the username is required"), which points at the app, not at the filesystem underneath it.

**Multi-process applications are under-served.** Bugsink needs a `snappea` worker and a second `migrate --database=` before any post-login page works; Nextcloud wants a cron worker; Invoice Ninja wants a queue. `[run.workers]` expresses the processes, but not per-process environment, ports, or limits.

## Reproducibility tiers

Every tier builds in a sealed sandbox: the dependency set is vendored into a fixed-output derivation from a committed lockfile, so the package manager runs offline. The tiers rank provenance; hermeticity is not the measure.

| Tier | Method | Rebuilds identically? | Auditable to source? | Multi-arch? |
|------|--------|-----------------------|----------------------|-------------|
| 1 | nixpkgs package | yes | yes | yes |
| 2 | source build against a committed lockfile | yes | yes | one arch per lockfile |
| 3 | pre-built upstream artefact (`fetchurl`) | yes | no | **no** |

The pre-built-binary problem earlier drafts described has largely been worked through: Gitea, Forgejo, Miniflux and Vikunja are compiled from source with `go-source`, and Mattermost and Keycloak are `nixpkgs-wrapper`. Run `hop3-tools nix tiers apps/real-apps-nix-gen` for the current split, and see ADR 008 for the assessment.

Two moved the other way, deliberately. Paheko and Easy!Appointments now fetch the upstream *release* archive instead of building from the git tag, because the tag does not carry the whole application: vendored framework code in one case, built frontend assets and `vendor/` in the other. That is tier 3 by the table above. The alternative is a package that does not run.

## Open

- **Bugsink's hand-written Nix recipe runs a two-process application as one process**, and is the reason this family reads 15 of 16 rather than 16 of 16. It omits the snappea database migration and the snappea worker that the native and nix-gen recipes both carry with comments saying the application does not work without them; the fix is to bring it into line with its siblings. The failure it produces is a silent gunicorn worker-boot hang, not the slow start its accumulated start-timeout increases (120 → 180 → 240) were treating.

  Worth noting how it stayed hidden: the recipe has been failing this way intermittently for weeks, and each time the response was to raise the timeout, because "did not start in time" reads as slowness. The platform had in fact diagnosed it correctly at every failure — "the server bound its socket but no worker is serving" — in a diagnostic block nobody read past the headline of.
- **Docker is unclaimed.** Recipes exist and none has been measured at the sign-in bar; the reports no longer carry the variant rather than carry an empty column for it. Both families that *have* been measured failed comprehensively on first contact, so this is a known unknown, not a safe one.
- **Easy!Appointments cannot be verified by either path.** Its bootstrap runs and reports success; the served page carries no form inputs for `check.py` to post, and the browser harness fills the JavaScript-built form and remains on it. It may need a check that queries the application instead of driving its interface.
- **Two applications are not photographed signed in**: Mattermost's React login is not drivable by the harness, and Easy!Appointments fails outright. Paheko and Bugsink were on this list and have come off it — both now photograph, in every variant that installs. Invoice Ninja (Flutter canvas) and Radicale (HTTP Basic, rendering identically signed in or out) are declared undrivable, not counted as gaps. **Uptime Kuma joins them undeclared**: the 2026-08-01 run captured its sign-in page and no signed-in shot, and nobody has said whether that is a harness gap or another application the harness cannot drive. 50 of 55 variants are photographed.
- **Isso ships no built frontend** under Nix: the `python-venv` template has no frontend build phase, so its admin dashboard serves a 200 whose JavaScript 404s; a `contains` assertion passes on it.
- **`[healthcheck].contains` is declared by no recipe in the corpus**, and a deploy treats any status line as "serving". The "App is now running" a deploy prints is therefore satisfied by a 500, which makes a deploy's own report of success a weaker claim than these reports are.
