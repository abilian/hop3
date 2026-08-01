---
# Machine-checked. `hop3-tools catalog reports` validates every field below
# against the actual recipes and against git history, so a report that has gone
# stale fails a check instead of waiting to be noticed by a reader.
app: example-app                  # must match the recipe directory name
title: Example App
version: "1.2.3"                  # the application version this report describes
upstream: https://example.org/
languages: [php]                  # php | python | go | node | ruby | java | rust | ...
databases: [mysql]                # [] if none
in_catalog: true                  # published in the signed catalog?
report_status: draft              # draft | final | withdrawn

# The date the statuses below were last established BY A RUN. Not the date the
# prose was edited. If a recipe changed after this date, the report is stale and
# the check says so.
last_verified: 2026-07-28

# What "pass" was measured against. This is the field that stops a report
# certifying a bar the project no longer accepts:
#   authenticated:  signed in through the app's own auth, wrong password refused
#   http-content:   served its own content (a `contains` assertion)
#   http-status:    returned 200 (NOT sufficient for a catalog app)
verified_bar: authenticated

variants:
  native:  {status: pass}
  nix:     {status: no-recipe, reason: "superseded by the template variant"}
  nix-gen: {status: pass, template: php-app}
---

# Experience Report: Example App

One paragraph: what the application is, who runs it, and why it was packaged:
*which edge of the platform it was chosen to probe*. Packaging is
system-validation work; say what this app was expected to stress.

## What this app exercised

The platform capabilities this application depended on, and which of them it was
the first or hardest consumer of. Be specific: a toolchain, an addon, a template
field, an installer step, a runtime behaviour.

> Required, and it may not be empty. If an app exercised nothing new, that is
> itself the finding: say so, and say what it confirmed instead.

## What broke

Every failure worth another packager's time: the symptom, the error as it
actually appeared, how it was diagnosed, and what resolved it. Include failures
that turned out to be our own misreading; they cost the most
time and are least likely to be written down elsewhere.

> Required. "Nothing broke" is a legitimate answer for a genuinely clean app and
> must be stated explicitly, with what was attempted, so that a reader can tell
> it apart from an unfinished section.

## What the platform gained

The changes to Hop3 this application forced, with links (ADR, commit, template
field). This is the section that makes the corpus an instrument.

> If the answer is "nothing", the app was a confirmation.
> Say that.

## Deployment variants

One short subsection per variant that has a recipe, covering what is specific to
it. Do not restate the metadata block above; statuses live there and are
checked. Explain the *shape*: what the build does, what the runtime needs, what
had to be worked around and why.

### Native

### Nix (hand-crafted)

### Nix (template-generated)

## Verification

What was checked and how, at the bar named in the metadata. For a catalog app
this is its `check.py`: which account it signs in as, what it asserts once
signed in, and anything it deliberately does not cover.

## Reproduce

The exact commands a reader runs to see this for themselves.

```bash
hop3 catalog install example-app --app example-app
hop3 app check --app example-app
```

## Open

What remains unresolved, deferred, or untested, with the reason and a pointer
to where it is tracked. A report with nothing open should say so; a report with
an empty section reads as unfinished.

## Screenshots

![Sign-in page](images/example-app-01-login.png)
![After signing in](images/example-app-02-signed-in.png)
