# Bugsink nix-gen — deferred

**Reason:** The `python-venv` template installs `bugsink` + DB driver via pip into a Nix-built Python venv. When the driver is `psycopg2-binary` or `psycopg[binary]`, the wheel's compiled `_psycopg.so` references a version-pinned `libkrb5-fcafa220.so.3.3` that isn't installed alongside the wheel and isn't on the host's loader path. When the driver is pure-Python `psycopg`, the runtime needs `libpq.so.5` on `LD_LIBRARY_PATH`. Either way, **`LD_LIBRARY_PATH` must point at a Nix-store path that can only be expressed via Nix interpolation** (`${pkgs.postgresql.lib}/lib`, `${pkgs.krb5.lib}/lib`).

The `python-venv` template currently has no mechanism for this:

- `env-exports` go through `nix_escape`, which escapes `$` so Nix interpolation never happens at build time.
- `runtime-env` writes static strings into `runtime.json`; same Nix-interpolation gap.
- `extra-paths` only feeds `PATH`, not `LD_LIBRARY_PATH`.

**Working variants (kept):**

- `apps/real-apps-native/bugsink/` — Hop3 server already has `libpq` and `libkrb5` from system Debian packages.
- `apps/real-apps-docker/bugsink/` — Dockerfile installs `libpq5` directly; psycopg2-binary wheel works because it uses the same Debian-style libkrb5.
- `apps/real-apps-nix/bugsink/` — hand-crafted `hop3.nix` exports `LD_LIBRARY_PATH=${pkgs.postgresql.lib}/lib:${pkgs.krb5.lib}/lib` in the wrapper before running `bugsink-manage` and `gunicorn`. Uses pure-Python psycopg v3.

**Unblocker:** extend `python-venv` (and any other template that pip-installs C extensions) with a `nix-runtime-libs` field that emits `${pkgs.<x>.lib}/lib` paths into `LD_LIBRARY_PATH` at the Nix interpolation layer, not via `nix_escape`. Same shape as the proposed `nix-env-exports` mechanism in `local-notes/stacks-and-apps/TEMPLATE-LIMITATIONS.md` Gap 1. Future apps with C-extension Python deps (Outline/Funkwhale via psycopg, Mobilizon via Erlang ports, etc.) will hit the same wall.
