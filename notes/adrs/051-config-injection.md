# ADR 051: Config Injection — Wiring config-file and DB apps from the injected environment

**Status**: Draft
**Type**: Architecture
**Created**: 2026-06-22
**Related-ADRs**: 002 (hop3.toml format — the `[run].before-run` hook), 046 (declarative-app-resources), 008 (template-based-nix-expression-generation), 041 (privileged-operations-agent)

## Context

Hop3 wires a backing service into an app by injecting the addon's connection details as environment variables: an addon's `get_connection_details()` returns a flat dict, which becomes encrypted `AddonCredential` rows and then `EnvVar` rows materialized into the app's process environment at spawn. An app that reads `DATABASE_URL` or `SMTP_HOST` from its environment is configured the moment the addon is attached.

Many real applications do not read their configuration from the environment. They read a config file — `homeserver.yaml`, `LocalSettings.php`, `config.production.json`, an INI section — or they keep it in their own database, set through a CLI or admin API (`occ config:system:set`, a Keycloak realm import). For these apps, environment injection reaches nothing: the credentials sit in a process environment the app never consults. A survey of the packaged catalog found roughly a third of the apps that send email — and several that read their *database* credentials — in this shape.

Today these apps are wired, when at all, by bespoke shell baked into each app's packaging — `scripts/setup-config.sh` heredocs, `Dockerfile` `RUN` blocks, per-app `getenv()` glue hand-written into a config file. This is the per-app workaround the platform exists to eliminate. It is invisible to the platform; it leaks secrets through shell word-splitting and the process list; it reinvents idempotency, file permissions, and failure handling in every app; and it silently disables features when it hardcodes a default (a `MAIL_MAILER=log`, a `MAILER_ENABLED=false`).

The missing capability is general, and not specific to email: **take a value that has already been resolved into the app's environment — an addon credential, a generated secret, a computed variable — and place it where an app that does not read the environment will find it: in a rendered config file, or in the app's own state via a setup command.**

The primitives to build on already exist. `expand_vars` (`lib/templating.py`) resolves `${VAR}` against a flat env map, guards against a NUL-injection signature, and is the engine behind `[env.computed]`. By the time `[env.computed]` resolves — after `reinject_attached_addons`, default and generated vars, `HOST_NAME`, and reference resolution — the app's environment already carries every addon credential. `[nix.config-files]` renders config files, but only for the nix-gen builder. The `[run].before-run` hook (ADR 002, §`[run]`) runs commands in the app environment before workers start, but as imperative shell with no idempotency or secret-safety contract.

The two application shapes call for two outputs: a **rendered file on disk** (file-based apps), and an **imperative effect in a store the platform does not own** (DB/CLI-state apps). A file is idempotent by overwrite; a CLI mutation is not, and needs a guard.

## Decision

Config injection happens in the **`before-run` lifecycle hook** (ADR 002, §`[run]`). It already runs in the app's environment — addon credentials, generated secrets, and computed variables all present — before workers start, on every builder, and several packaged apps already wire their database this way. A `before-run` script renders any config file or runs any setup command the app needs: the shell's own `${VAR}` / `${VAR:-default}` expansion (or `envsubst`) does the substitution, and the script author controls per-format quoting directly. No new platform mechanism is required to wire the config-file and DB apps — the imperative path is the baseline, and it works today.

What the platform owns here is not a rendering engine but a small set of **conventions** that keep these scripts from repeating the failures the bespoke ones make today (documented in the packaging guide):

- **Never hardcode a feature off.** A generated config that pins `MAIL_MAILER=log` or `MAILER_ENABLED=false` shadows the injected value and silently disables mail; default *through* the injected value (`MAIL_MAILER=${MAIL_MAILER:-log}`) so an attached addon or an `[env]` remap wins.
- **Keep secrets out of argv.** A setup command that interpolates a secret into a shell word (`occ … --value=$SMTP_PASSWORD`) leaks it to the process list; pass the env-var *name* (`--password-from-env`) or feed it on stdin.
- **Fail loud.** `set -euo pipefail`, and assert a required variable is present before rendering, so a missing credential aborts the deploy rather than writing a half-rendered config with a literal `${SMTP_PASSWORD}` in it.
- **Make setup commands idempotent.** Guard a non-idempotent CLI mutation with a probe (`occ status | grep installed`) so a redeploy does not double-apply.

These conventions are the immediate, low-cost answer for the config-file/DB apps; the platform's job is to make them easy and to surface a violation, not to replace the script.

### Optional, deferred: a declarative layer

A declarative form would lift the same wiring out of per-app shell into platform-visible, schema-validated declarations that apply those conventions *by construction* — fail-loud, secret redaction, idempotency, and safe file permissions that no app then reinvents. It is a **nice-to-have, not a prerequisite**, and it earns its keep only if the per-app scripts become a maintenance burden or the conventions are repeatedly violated. It is recorded here, settled, so the design is ready if that time comes. If built, it is two all-builder `hop3.toml` sections the platform resolves from the injected environment (mirroring `[limits]` / `[[volumes]]`, ADR 046):

#### `[[config-files]]` — render a config file

```toml
[[config-files]]
path = "homeserver.d/email.yaml"    # app-relative
format = "yaml"                      # value-escaping for the target syntax
mode = "0640"                        # default 0600, app-owned, atomic write
content = """
email:
  smtp_host: ${SMTP_HOST}
  smtp_port: ${SMTP_PORT}
  smtp_user: ${SMTP_USER}
  smtp_pass: ${SMTP_PASSWORD}
  notif_from: ${SMTP_FROM}
"""
```

(or `from = "templates/homeserver.yaml.tmpl"` for a file too large to inline). The platform reads the template, substitutes `${VAR}` from the deploy-time environment, and writes the result to `app_src/path`. The packager owns the surrounding syntax — the YAML indentation, the `$wgSMTP = [ … ]` PHP scaffolding, the INI section headers — and the platform owns only hole-filling, so each app's native config language is expressed directly.

- **Value-escaping by format.** `format` (`yaml | json | php | ini | shell | raw`, default `raw`) escapes each *substituted value* — not the template — for the target syntax. Hop3 mints random addon passwords, so a value containing a quote, colon, slash, or newline is the common case; substituting it raw into a YAML, JSON, or PHP file would corrupt the file or inject structure. Escaping the value closes that class without a template language.
- **`create-if-missing`** skips the write when the file already exists, for apps whose installer writes a base file the render only completes on the first deploy (`synapse --generate-config`, a Laravel `.env`).

#### `[[setup]]` — run an idempotent setup command

```toml
[[setup]]
argv = ["php", "occ", "config:system:set", "mail_smtphost", "--value", "${SMTP_HOST}"]
unless = { argv = ["php", "occ", "config:system:get", "mail_smtphost"], equals = "${SMTP_HOST}" }
```

For state that lives in a database or behind a CLI. A `[[setup]]` step is an **argv list** — never a shell string — substituted from the environment and `exec`'d directly. It runs after all `[[config-files]]` (so a step that imports a rendered file, such as `kc.sh import realm.json`, sees it) in the `before-run` slot, on every builder.

- **Idempotency is a first-class field.** `unless` declares a probe (`argv` plus one of `equals` / `contains` / `exit-zero`). A `[[setup]]` step the platform cannot prove idempotent and that carries no `unless` is a schema error, so a packager cannot ship a step that double-applies on every redeploy (the install-gate `occ status | grep "installed: true"` that bespoke scripts hand-code becomes a declared `unless`).
- **Secrets stay out of argv where the CLI allows it.** The convention is to pass a secret's env-var *name*, not its value (`--password-from-env=OC_PASS`), or to feed it on `stdin`; the child already carries the environment. Where a CLI only accepts `--value=<secret>`, that value is in the child's argv for its lifetime — an upstream limitation the platform cannot remove — but never in a shell, a log line, or the serialized build artifact: a step marked `secret = true` is redacted everywhere it is recorded.

#### Engine and ordering

- `expand_vars` gains `${VAR:-default}`. Configs in the tree rely on the shell evaluating `:-` at runtime; once the platform renders at deploy time that evaluation is gone, so the engine must provide it. The change is additive — bare `${VAR}` is unaffected — and is shared with `[env.computed]`.
- An unresolved `${…}` after substitution is **fatal**, not a warning. `[env.computed]` today logs a warning and proceeds; a config file containing a literal `${SMTP_PASSWORD}` is a security and correctness failure, so rendering aborts the deploy, naming the file, the missing variable, and the addon that supplies it. `[env.computed]` is aligned to the same strictness. A reference to an unattached addon's credential therefore surfaces here, at deploy, rather than as silently-broken mail at runtime.
- Both sections resolve after the full env pipeline and run before workers start, on native, Docker, and nix builds alike; `[[config-files]]` render first, then `[[setup]]`.

#### `[nix.config-files]` is subsumed

The nix-gen `ConfigFile` is `[[config-files]]` restricted to one builder. The top-level section is the all-builder generalization; `[nix.config-files]` is read for one release behind a deprecation warning that names its replacement, then removed.

## Rejected alternatives

### Jinja templates with conditionals and format filters

The strongest competing design renders Jinja2 templates (already a declared dependency of hop3-server) with `StrictUndefined`, per-format filters (`| yaml`, `| phpstr`, `| json`), and addon-awareness (`{% if addons.email %}`) so a block is emitted only when its addon is attached. It is the most capable design for structured configs, and it closes the "dead config lines when no addon is attached" gap directly.

It is rejected as the engine for three reasons. Jinja's `{{ }}` / `{% %}` delimiters collide with the formats being rendered — Django settings and templates, YAML anchors, some shell — forcing `{% raw %}` guards that are a footgun of their own. It introduces a second templating language beside the `${VAR}` syntax packagers already use in `[env.computed]`, for a value source that is always a flat map of strings with no loops or filters to express. And the per-format filters become load-bearing security code, where a half-correct `| phpstr` or `| yaml` is worse than none. The escaping-of-secrets correctness that motivates Jinja is obtained more cheaply by escaping the substituted *value* per `format`, without a template language. The conditional-on-attachment gap is handled by failing loud when a referenced credential is absent — explicit, and arguably better than a block that silently vanishes — with a separate `[[config-files]]` entry for the optional case. Jinja remains the sanctioned upgrade path if structural conditionals become a real need; this decision does not foreclose it.

### One unified `[[provision]]` step list

A single ordered tagged-union list (render-file or run-command) expresses arbitrary interleaving of files and commands under one mental model. The interleaving it buys — command, then file, then command — is needed by none of the surveyed apps; the one real ordering need, render a file then run a command that consumes it, is met by the fixed "files before commands" order of two sections. Two named sections read more honestly against the file-versus-DB taxonomy and keep each schema tight — a file step has `mode` and `format`, a command step has `argv` and `unless` — where the unified list forces both into one shape. The single-mechanism elegance does not pay for the lost readability.

### Build the declarative layer now, instead of using the `before-run` baseline

Tempting, because declarative sections read better than shell. Rejected as the immediate step: the `before-run` hook already places config from the injected environment with no platform change, so a new schema, renderer, and per-app migration is effort spent before the cheaper path — conventions plus documentation — has been shown insufficient. The declarative layer is deferred to the point where the per-app scripts demonstrably cost more than the mechanism would, not built speculatively. The hook exists; use it.

### Per-app `getenv()` glue in a hand-written config file

The Nextcloud Docker variant already wires its `config.php` mail keys from `getenv()` calls baked into a hand-written file. It works for one app, under non-standard names, and is exactly the bespoke per-app workaround this decision replaces with one general mechanism.

## Consequences

In the baseline, the immediate consequences are documentation and discipline: the packaging guide carries the four conventions above, and the silent-disable bugs they target are fixed where found (a `MAIL_MAILER=${MAIL_MAILER:-log}`, a `${VIKUNJA_MAILER_ENABLED:-false}`). The file-based apps in the catalog (Taiga, Matrix-Synapse, MediaWiki, Isso, Paheko, Kanboard, LimeSurvey, Gatus, Redmine, Ghost) and the DB/CLI-state apps (Nextcloud, Keycloak, Wiki.js, Dolibarr) are wired by a `before-run` script that renders from the environment they already receive — no platform change, and not email-specific, since the same `${VAR}` holes carry an addon's database, cache, or object-store credentials.

If the declarative layer is later built, it adds the same safety *by construction*: a config file carrying decrypted secrets written `0600` and owned by the app user, atomically (temp file, set mode, rename); a `[[setup]]` command run without a shell, preferring an env or stdin secret channel and redacting secrets from logs; every failure — unresolved variable, missing template, failing setup command, failing idempotency probe — aborting the deploy with a diagnosis rather than warning and continuing. The per-app scripts then translate mechanically (file half to `[[config-files]]`, command half to a guarded `[[setup]]`) and are deleted. No new third-party dependency either way.

## Open questions

1. **Docker apps.** A native or nix app's config file is rendered into a working directory the process reads directly. A Docker-Compose app reads its config inside the container, so a `[[config-files]]` render must land on a bind-mounted path (or a `[[setup]]` step must `exec` inside the container). This is the same class of Docker-specific plumbing that ADR 045 deferred for fixed ports, and likely lands alongside it.
2. **Where rendered files live across redeploys.** A rendered file under the app's source tree is recreated each deploy (idempotent by overwrite); one that must persist as mutable state belongs under the app's data directory or a volume (ADR 046). The schema should make the distinction explicit rather than leave it to `path` convention.
3. **`format` coverage.** The initial set (`yaml`, `json`, `php`, `ini`, `shell`, `raw`) covers the surveyed apps; a `python`/`pyrepr` form (for a rendered Django settings fragment) and a `toml` form may be needed, and each escaper is security-sensitive code that earns adversarial tests against secrets containing quotes, newlines, and backslashes.
