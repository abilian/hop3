# flask-env-ref — dynamic `[env]` reference smoke test

Proves Hop3's dynamic `[env]` references (ADR 046 §1b) end-to-end, through a
real deploy, not just unit tests.

`hop3.toml` declares a `postgres` addon named `db` and two references:

```toml
[env]
DB_HOST_VIA_REF  = { from = "db", key = "PGHOST" }   # copy an addon attribute
APP_NAME_VIA_REF = { key = "name" }                  # an app fact
```

The postgres addon also auto-injects `PGHOST` directly, so a correctly resolved
reference makes `DB_HOST_VIA_REF == PGHOST`. The app serves **`ENV REF OK`**
only when the addon reference matches that injected value *and* the app-fact
reference resolved — which the test harness asserts via `[[test.validations]]`.

Endpoints:

- `GET /` — `ENV REF OK` (200) when both references resolved, else a 500 naming
  the mismatch.
- `GET /config` — echoes the resolved values for inspection.
