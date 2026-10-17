# The Catalog Lifecycle

A catalog recipe travels a fixed loop: it is written, validated, published, verified against what was published, and promoted. This page describes that loop. [Publishing a Catalog](catalog-publishing.md) covers the signing and distribution mechanics it relies on; [ADR 049](adrs/049-catalog-distribution.md) and [ADR 059](adrs/059-catalog-maturity-status.md) record why the design is what it is.

One distinction runs through everything below: `hop3-test run` deploys a recipe from a local directory; `hop3-test run --recipes published` installs it from the catalog the server publishes. They exercise different things, and only the second can promote an app. A run of the first that passes every app proves the recipes work; it says nothing about what operators can actually install.

## Where a recipe lives

Recipes live in the catalog repository, under the maturity status that admits them:

```
apps/<status>/<app-id>/
```

The directory **is** the status. Nothing else records it, because a `status` field beside a `status/` directory is two sources of truth for one fact, and they drift. The published `index.json` carries a `status` field derived at publish time. That value crosses into the artifact the node can read.

| Status | Admitted when | Published |
|---|---|---|
| `golden` | It installs **from the published catalog** and signs in through the application's own authentication with the credential Hop3 generated. A wrong password is refused. Carries `[admin]`, and `[probe]` where the application has accounts. Presentation metadata complete. | yes |
| `beta` | It deploys and serves its own content: readiness passes a `[healthcheck].contains` assertion on the body. The sign-in bar is unmet or does not apply. | yes, marked |
| `alpha` | It deploys. Verification is status-only or unproven. | no |
| `broken` | A recorded failure, with the reason written down. Kept: the failure names a platform gap. | no |
| `retired` | Withdrawn for a reason upstream of the platform: archived project, incompatible licence, superseded by another variant. | no |

An application packaged several ways has one entry carrying its name (the native build path, the default an operator gets) and suffixed variants at their own status: `gitea`, `gitea-nix`, `gitea-nixgen`.

The published tree stays **flat**. Publish walks the hierarchy and emits the same `<app-id>/…` layout it always has, so a deployed node's loader is untouched.

## What a recipe directory holds

```
apps/golden/gitea/
├── hop3.toml        # the deployable recipe, plus [test], [admin], [probe], [healthcheck]
├── catalog.toml     # presentation metadata, plus the server version it needs
├── check.py         # the sign-in smoke test
├── readme.md
├── icon.webp
└── screenshots/
```

`check.py` separates "starts" from "works". Apps repeatedly served a perfect login page while rejecting every credential, so the check signs in with the credential Hop3 generated and confirms a wrong password is refused. It runs at the end of **every** deploy, the dashboard included.

## Two sources of recipes

`hop3-test run` runs each app's validations and `check.py` on both. The source of the recipe decides which question a green run answers.

| | `--recipes local` (default) | `--recipes published` |
|---|---|---|
| Installs from | the sibling catalog checkout, uploaded with `hop3 deploy` | the catalog the server publishes, with `hop3 catalog install` |
| The test read from | the checkout's `hop3.toml` | the server's verified copy of the recipe |
| Selects with | `--status` (any), `--covers` | `--status golden`/`beta`, `--covers`, explicit ids |
| Answers | "does this recipe work?" | "does the published catalog work?" |
| Use it when | editing a recipe | promoting an app, or gating a release |

```bash
# Editing recipes: deploy from the working tree
hop3-test run --docker --status beta
hop3-test run --docker --status alpha --covers nix     # the two axes compose

# Promoting: install what the server actually publishes
hop3-test run --host <server> --recipes published --with all
hop3-test run --host <server> --recipes published gitea-nixgen   # one app
```

A published run refreshes the server's catalog first and fails if the refresh does. Alpha is refused: the catalog does not publish it. Each app is installed, validated, upgraded with `hop3 app upgrade` and validated again, then destroyed. Installing builds each app from source, so budget generously: a single Rust-heavy app can take twenty minutes. `scripts/check-catalog.py`, in the catalog repository, still takes the screenshots (`--screenshots`).

## The loop

### 1. Edit and validate

```bash
cd hop3-catalog
make validate            # coexistence gate + recipe lint + presentation lint
```

`lint-recipes` rejects an app that hard-codes its public address in place of `HOP3_PUBLIC_URL`. Four recipes pinned a loopback address; all four passed their own checks while showing a browser nothing. `lint-presentation` rejects an entry unfit to show an operator: one missing its title, real category, memory estimate, icon or screenshot, or carrying an id another entry claims. `validate` also names every recipe it will **not** publish, grouped by status.

### 2. Publish

```bash
make publish CONTEXT=<ctx>     # validate → build → verify → site → stage → deploy
```

Then confirm the live artifact matches what you signed, because a successful upload does not guarantee a served file:

```bash
curl -fsSL https://apps.hop3.cloud/catalog/v1/catalog.tar.gz | sha256sum
sha256sum dist/catalog.tar.gz            # the two must match
```

### 3. Refresh the server

A node caches the catalog it verified, so publishing alone does not change what it installs:

```bash
hop3 catalog refresh     # fetch → verify signature → anti-rollback → publish → reload
hop3 catalog list        # confirm the entry count and statuses are what you just signed
```

### 4. Check, then promote

```bash
hop3-test run --host <server> --recipes published --covers nix
```

For each app that passes, move it and re-publish so the artifact carries the new status:

```bash
git mv apps/beta/<app> apps/golden/<app>
make validate && make publish CONTEXT=<ctx>
```

A status can also go **backwards**. A `golden` recipe whose next verification fails is demoted. Demotion is the normal outcome of a failing run.

## Recipes that need a newer server

One catalog serves every server that refreshes from it, and servers upgrade on their own schedule. A recipe that depends on a platform feature an older server lacks (a new `[nix]` key, a template capability, a nixpkgs pin its recorded hashes were taken against) says so in its overlay:

```toml
[catalog]
requires_hop3 = "0.8"
```

A server older than that refuses `hop3 catalog install` by name ("needs Hop3 0.8 or newer, and this server runs 0.7.5") before it creates anything, instead of staging the recipe and failing in the middle of the build. The value is a plain release number; the publish step refuses anything else. A development build counts as its release, so a `0.8.0.dev` server installs a recipe that needs 0.8.

Servers released before the key existed ignore it. They still fail on such a recipe, at build time, so a recipe that needs a new server is published only once that server is released.

The publish step also works out what a recipe needs. Each platform feature a recipe can depend on has a rule over its `hop3.toml` (`server/catalog/features.py`): `php-fpm` for a PHP recipe with no start command, `scratch-volumes`, `proxy-deny`, `access-gate`, `nix-github-source` and others. The names a recipe matches go into its entry in the signed index as `requires`, and a server lacking one refuses the install, naming it. The publish refuses a recipe whose `requires_hop3` is missing or lower than the release that introduced its features, and says which value to write; a higher value is kept, for a need no rule detects.

## The ordering trap

A published run installs from the published catalog. Edit a recipe, skip the publish, re-run it, and you have re-tested the **old** recipe, with nothing in the output saying so. Five apps were recorded as "verified fixed" against recipes that still carried the bug, twice, before the missing `make publish` was noticed.

Publishing belongs inside the edit-test loop.

Nothing in a published run compares the server's recipes with your working tree: publish, then refresh, then run.

## Limits of each check

- `check.py` verifies the application's **web** authentication. A two-process application whose background worker never started can pass it, sign in perfectly, and fail on the first task that needs its queue.
- `[healthcheck].contains` checks for a substring of the body at one path. It catches a placeholder page or another app behind the proxy; it does not exercise the application.
- A green `hop3-test` run says the recipe works from the working tree. Only a published run says an operator can install it.

## See also

- [Publishing a Catalog](catalog-publishing.md): signing keys, serials, staging, key rotation
- [Staging a Catalog](catalog-staging.md): sideloading a signed catalog onto your own box
- [Testing Cheat Sheet](testing-cheat-sheet.md): the pytest layers and the rest of `hop3-test`
- [ADR 049](adrs/049-catalog-distribution.md): signed distribution and the artifact shape
- [ADR 059](adrs/059-catalog-maturity-status.md): the statuses and why the directory is the truth
