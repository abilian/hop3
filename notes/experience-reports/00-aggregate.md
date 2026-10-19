# Aggregate Experience Report: Packaging 20 Applications for Hop3

**Status:** Final (0.7): the per-app reports are `report_status: final`; corrections continue against a published baseline.
**Last updated:** 2026-10-18

## Overview

Twenty open-source applications are packaged for Hop3 and published in the signed catalog. Each is packaged for up to three build paths (native, hand-written Nix, and Nix generated from a template). Each has a `check.py` that signs in through the application's own authentication and confirms a wrong password is refused.

Packaging is system-validation work. Every application was chosen to stress a different edge of the platform. The per-app reports record which edge. Where an app merely confirmed existing behaviour, its report says so without inventing a contribution.

The instrument matters more than the count. "Passing" here means an authenticated sign-in through the application's own surface, with a wrong password refused. That bar was adopted only after a majority of the corpus was found to clear the previous one (HTTP 200) while being impossible to log into. Read against that bar, five of these twenty were at one point serving with no usable credential at all. Every instrument the project then had reported them working.

## Application coverage

The table is derived from the reports' own headers, which `hop3-tools catalog reports` checks against the recipes, so it cannot drift from them silently. `n/a` means there is no recipe for that variant. Docker is not listed: recipes exist for most of these applications and none has been measured at this bar, so the report does not claim the variant.

| App | Language | Database | Native | Nix | Nix-gen |
|-----|----------|----------|--------|-----|---------|
| BookStack | php | mysql | pass | pass | pass |
| Bugsink | python | postgres | pass | pass | pass |
| Dolibarr | php | postgres | pass | pass | pass |
| Easy!Appointments | php | mysql | pass | n/a | pass |
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

## What the numbers mean and what they do not

**Update, 2026-10-18.** A run of the published catalog on a server passed every golden and beta entry, 54 of 54, each installed with `hop3 catalog install`, upgraded and checked again. A browser signed in to 48 of them. The six without a signed-in image are the variants of the three applications listed under Open. Easy!Appointments' template variant, the single nix-gen failure below, is among the 48. The run before it found two faults that no earlier instrument had caught. WordPress's template variant had never created its probe account. Mattermost's two Nix variants had served no web client since their import, while the REST check passed. Both are fixed, as their reports record. The paragraphs below describe the 2026-08-01 runs.

**Native, the variant the catalog publishes, is 20 of 20** on a complete recorded run (2026-08-01). Earlier drafts of this report declined to claim it. The runs before this one topped out at 19 of 20. Every application had been seen green at some point, but no single run had been all-green *and* recorded. A claim resting on "each of them passed at some point" is a weaker object than one resting on a run that can be pointed at, so the number waited for the run. This is that run.

**Nix-gen is 18 of 19** on that run. Easy!Appointments is its single failure: it builds its login form in JavaScript, so neither the HTTP check nor the browser harness can complete a sign-in. Its report records the failure. That failure is stable and understood.

**Hand-written Nix is 16 of 16** on a complete recorded run of its own (2026-08-01, browser harness). It read 15 of 16 earlier the same day. The intervening hour is the more useful part of the record.

Bugsink had not installed. The reading that had gone unchallenged for weeks was that it was slow: three successive `start-timeout` increases across the three variants (120 → 180 → 240) had been spent on a failure whose headline was "did not start within Ns". It was not slow. Its gunicorn master bound the port eight seconds in. No worker ever booted after that. The log showed neither a "Booting worker" line nor a traceback while the process hung for the remaining 232 seconds. The platform had diagnosed it correctly at every occurrence, in the line under the headline: *"the app's port is listening but it did not answer an HTTP request: the server bound its socket but no worker is serving."*

The cause was structural. **The hand-written recipe ran Bugsink as one process, but Bugsink is two.** Its two siblings each migrate a second database (`migrate --database=snappea`) and declare a second worker (`[run.workers] snappea = "bugsink-runsnappea"`), each with a comment saying the application does not work without them. The hand-written recipe did neither, while generating its config from the same `--template docker` that assumes both. It could not have done otherwise. Its setup lived inside the *web* start wrapper, where everything runs only for gunicorn, so no second process could share it. Moving it to `before-run` and declaring the worker took the application from a 245-second hang to a 40-second pass.

Native holds the corpus's only *20-application* all-green run; both figures now rest on complete recorded runs.

Both families were measured for the first time that week. The first measurement of the hand-written corpus **failed all sixteen applications**, three days after a deploy-oriented matrix scored the recipes in its scope 15 ok, 0 fail. Two instruments read one corpus and gave opposite verdicts. That is the result the sign-in bar exists to produce. The older instrument could not see what it was reporting green; the same corpus reached 16 of 16 within a day.

### What the first measurement found

**Five of the sixteen were serving with no usable credential**, in five different ways. Radicale's `[auth] type` defaulted to `none` and nothing set it, so every calendar and address book was public. Isso's config had no `[admin]` section, so its moderation dashboard was served disabled. Miniflux and Keycloak each shipped a literal `changeme` (an identity provider among them), so the deployed instance had an administrator whose password is in this repository while the operator held one that did not work. LimeSurvey installed itself as `console.php install admin password123` with the result discarded by `2>/dev/null || true`: a published password *and* a failed install reported as success, in one line.

No status assertion and no content assertion can distinguish any of those from a working deployment. The argument is not hypothetical.

The remainder divide cleanly. Two forges had a *native* `create` command naming `./gitea`, a path with no meaning in a Nix layout. Three held secrets minted by a wrapper that re-evaluates them on every start. Three were served straight out of the read-only store and so could never be installed at all. The rest had no first-run bootstrap, because these recipes predate ADR 056 and the variant generator grafts an identity they cannot honour.

### One methodological finding

Every application in this corpus exists in two to four packagings. The fastest route to a defect in one of them is a diff against a packaging that already passes. The last four hand-written failures each took a single attempt once that was the method, having resisted several rounds of reasoning from symptoms.

The wrong theories are kept because each would have sent someone into the platform after a defect that is not there. Matomo looked like a reverse-proxy misconfiguration, where it needed the `core:update` both working variants run. Vikunja looked like a version skew, where `nix eval` says nixpkgs ships the *same* Vikunja the template variant compiles. A third theory blamed PHP's built-in server for mismatching responses under concurrency, which every working variant also uses. Reading the redirect target, the log line, and the working recipe would each have been quicker than any of them.

**Docker is out of scope for this report.** Recipes exist for most of these applications and no run has ever measured one at the sign-in bar, so the corpus has nothing to say about them. Earlier versions of these reports recorded Docker as "Passing", which is the specific rot this format exists to prevent: that status was recorded without observation. The variant is not claimed; on the evidence above, whoever measures it first should expect to find things.

## The bar, and why it moved

For most of this corpus's life, "passing" meant the application deployed and answered HTTP 200. That bar was retired after a majority of the catalog was found to clear it while being impossible to log into: apps served their login page perfectly and rejected every credential. Some of those failures were the platform's, some the recipes', and one was the checking library posting an empty form body: the same symptom for all three.

Reports now name the bar they were verified at, in a header field the checker reads:

| Bar | Meaning |
|-----|---------|
| `http-status` | returned 200; **not sufficient** for a catalog app |
| `http-content` | served its own content (a `contains` assertion) |
| `authenticated` | signed in through the app's own auth; a wrong password was refused |

An advertised application may not be reported `final` on anything less than `authenticated`, and the checker enforces it.

A deploy's own report of success was a weaker claim than these reports until every recipe declared `[healthcheck].contains`. Without it, a deploy treats any status line as "serving", so the "App is now running" it prints is satisfied by a 500. Every published recipe now declares one (2026-10-18), so a deploy reports an app running only once it serves that content.

## Recurring technical findings

The per-app reports hold the detail; these are the patterns that showed up in more than one.

**An app's binary is rarely named after the app, and never the same in two packagings.** `buildGoModule` names it after the module path element, so a source build gives `forgejo.org`, `miniflux.app`, `api`. nixpkgs names the same three `gitea`, `miniflux`, `vikunja`; its Mattermost derivation ships no `mmctl` at all, though every `mmctl --local` in that app's documentation assumes one. `$out/bin` holds only the generated wrapper, which execs one fixed subcommand, so putting it on `PATH` does not help; `${pkg}` is the stable binding for the application's own derivation. A command copied from a sibling recipe fails differently, without working, and `nix eval` on the pinned nixpkgs settles the question in seconds.

**A credential is not injected until something maps it.** Hop3 generates an administrator password, stores it encrypted, and injects `HOP3_ADMIN_*`. An application reads whatever *it* reads. The mapping is the recipe's job (`[env.computed]`). Where the mapping was missing, the recipe usually still had a literal default, so the deployed application had an administrator whose password was published in the repository, while the operator was handed one that did not work. The smoke test reported only the second half of that. Four recipes were in this state.

**A secret evaluated by the wrapper is a secret that rotates.** Values in `[nix.env-exports]` are shell expressions re-evaluated on every start. Several recipes minted signing keys there with `$(head -c 32 /dev/urandom | base64)`, which silently invalidates every session on restart and, for the forges, makes 2FA secrets and stored credentials undecryptable. Generated-once `[env]` secrets are the mechanism; the shell is not.

**The generated wrapper is not the only thing that runs the app's code.** `[run] before-run` and the `[admin]`/`[probe]` create commands execute directly. Anything that lives only in the wrapper (`LD_LIBRARY_PATH` from `nix-runtime-libs`, a composed `DATABASE_URL`) is absent there. The failure then looks like a broken application, though what is missing is the environment.

**PHP `__DIR__` resolves symlinks**, so a Nix store path reached through one lands back in the read-only store. `needs-writable-dir` copies the tree instead. The copy's *timing* was the single largest cause of nix-gen failure. It happened when the app started, which is after `before-run`, so any application whose bootstrap needs its own code found an empty directory. Materialising it at deploy time, ahead of the first `before-run` command, moved six applications at once.

**An application's public address is not the address it binds.** Four recipes pinned theirs to `http://localhost:8080` (three in `[nix.runtime-env]`, baked into the wrapper at build time) and one built it by hand as `http://${HOST_NAME}`, right host, wrong scheme. The consequences differ: a Vue frontend calling the visitor's own machine, a Laravel redirect loop, a Keycloak console whose sign-in redirect points nowhere, a JavaScript form posting over http from an https page. The shape is identical. The server side is unaffected, so every status and content check passes while a browser is shown nothing usable. `HOP3_PUBLIC_URL` is injected once the hostname is settled and reaches config files, `before-run` and `create`; `make validate` now rejects a hand-built public URL in any build-time table.

**A git tag is not a release.** Paheko vendors the KD2 framework into its release tarball without committing it; Easy!Appointments' tag omits both its minified assets and its `vendor/` tree. `fetchFromGitHub` on the tag produces a package missing part of the application, and the failure surfaces at runtime as a missing `require_once`, not at build time.

**A setting that lives in a shell script is lost in repackaging.** `DISABLE_REGISTRATION = true` sat in the native recipes' `scripts/setup-config.sh`. No Nix variant has a `scripts/` directory, so all four Nix forge builds put an internet-facing Gitea or Forgejo online on which the first visitor could register. It shipped for as long as those variants existed. **The sign-in bar does not catch it**: an application with open registration signs in perfectly and refuses a wrong password. The bar is a floor. A security posture that lives only in a file one packaging happens to include is not a posture.

**A bootstrap CLI's exit code is not its outcome.** Gitea and Forgejo print `admin user create`'s error and exit 0. Dolibarr's install steps do the same. Vikunja's `user` command answers an unknown subcommand with usage text and exit 0, so calling one that does not exist is a silent no-op. Every `create` in this corpus now verifies the account exists (by listing it, or by querying the row), because the platform's own "admin created" message is a promise it cannot otherwise keep.

**A read-only store is not a place an application can be installed.** Three recipes served straight out of `$out`, where nothing can be written: the schema, the config, the uploads and the account have nowhere to go. The app deploys, starts, answers HTTP, and cannot be signed into. The failure presents as an application-level message ("please run setup", "the username is required"), which points at the app, not at the filesystem underneath it.

**Multi-process applications are under-served.** Bugsink needs a `snappea` worker and a second `migrate --database=` before any post-login page works. Nextcloud wants a cron worker. Invoice Ninja wants a queue. `[run.workers]` expresses the processes, but not per-process environment, ports, or limits.

## Reproducibility tiers

Every tier builds in a sealed sandbox: the dependency set is vendored into a fixed-output derivation from a committed lockfile, so the package manager runs offline. The tiers rank provenance; hermeticity is not the measure.

| Tier | Method | Rebuilds identically? | Auditable to source? | Multi-arch? |
|------|--------|-----------------------|----------------------|-------------|
| 1 | nixpkgs package | yes | yes | yes |
| 2 | source build against a committed lockfile | yes | yes | one arch per lockfile |
| 3 | pre-built upstream artefact (`fetchurl`) | yes | no | **no** |

The pre-built-binary problem earlier drafts described has largely been worked through: Gitea, Forgejo, Miniflux and Vikunja are compiled from source with `go-source`. Mattermost and Keycloak use `nixpkgs-wrapper`. Run `hop3-tools nix tiers apps/real-apps-nix-gen` for the current split, and see ADR 008 for the assessment.

Two moved the other way, by choice. Paheko and Easy!Appointments now fetch the upstream *release* archive. Building from the git tag was dropped because the tag does not contain the whole application: vendored framework code in one case, built frontend assets and `vendor/` in the other. That is tier 3 by the table above. The alternative is a package that does not run.

## Open

- **A failure's headline outranked its diagnosis for weeks.** Bugsink's hand-written Nix recipe ran a two-process application as one process (fixed 2026-08-01, §What the numbers mean). Every occurrence printed both "failed to start within 240.0s" and, immediately below it, the correct diagnosis: "the server bound its socket but no worker is serving". Three timeout increases were spent on the first line, while the second went unread. A right diagnostic that goes unread is a harder problem than a missing one. It argues for putting the specific finding *above* the generic timeout headline.
- **Docker is unclaimed.** Recipes exist and none has been measured at the sign-in bar; the reports no longer list the variant. Both families that *have* been measured failed comprehensively on first contact, so this is a known unknown.
- **Easy!Appointments is verified by a browser only.** Its served page has no form inputs for `check.py` to post, so a run without a browser reports it as not verified. Nothing checks that a wrong password is refused.
- **Three applications are not photographed signed in.** Invoice Ninja (Flutter canvas) and Radicale (HTTP Basic, rendering identically signed in or out) are declared undrivable. Uptime Kuma is declared too, as signing in over socket.io, but its sign-in page is an HTML form and a browser speaks socket.io itself, so that declaration is untested. Mattermost and Easy!Appointments came off this list on 2026-10-18: Mattermost's Nix variants had no web client. A fresh browser also meets Mattermost's desktop-app page before the form, which the harness now clicks through. 48 of the 54 published variants are photographed signed in.
- **Isso ships no built frontend** under Nix: the `python-venv` template has no frontend build phase, so its admin dashboard serves a 200 whose JavaScript 404s; a `contains` assertion passes on it.
