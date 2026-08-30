# Trying the app catalog on your own instance

This is the operator runbook for installing, managing, and removing **catalog apps** on a Hop3 server you control (e.g. a demo/staging box), against a **signed staging catalog** you build yourself. It exercises the real fetch → verify → publish → install path from [ADR 049](adrs/049-catalog-distribution.md); for the release-team publishing process see [catalog-publishing.md](catalog-publishing.md).

The catalog ships **disabled by design**: `hop3.server.catalog.keys.CATALOG_PUBLIC_KEY` is empty, and `hop3 catalog refresh` refuses to fetch an unverifiable catalog until a public key is compiled into the build. So step 0 for any self-test is to bake in *your* signing key.

> **Scripted (recommended for a self-test):** `scripts/stage-catalog.sh` automates the loop — `setup` (deploy + publish + sideload + list), then `publish` on each iteration, plus `install` / `destroy`. Override `HOST`, `CATALOG_REPO`, etc. via the environment.
>
> The script takes a shortcut the manual steps below do not: instead of the HTTPS fetch path (steps 0–4), it **sideloads** — it `scp`s the signed tarball to the box and calls the same verify-and-publish routine (`install_catalog_tarball`) directly, then restarts the server. The minisign signature is still checked against your key; only the (locally pointless) HTTP transport, TLS trust, and compiled-in key are skipped. The manual HTTPS path below is the real production-distribution shape — use it when you want to exercise fetch + verify over the wire.

## 0. Bake your catalog public key into the build

Generate a keypair once, or reuse the `catalog.pub` / `catalog.key` pair in your `hop3-catalog` checkout:

```bash
uv run hop3-catalog keygen --out-dir ./keys      # writes keys/catalog.pub + keys/catalog.key (0600)
```

Paste the public key into the build's pinned constant:

```python
# packages/hop3-server/src/hop3/server/catalog/keys.py
CATALOG_PUBLIC_KEY: str = "RWR...your catalog.pub base64 body..."
```

You can paste the full `catalog.pub` text or just its last base64 line. Keep `catalog.key` **offline**: it never touches the server. Redeploy the server so the running venv has the edited `keys.py` (`hop3-deploy-server --local`, or your usual deploy).

## 1. Build and sign the catalog

Point the publisher at a content dir of `apps/<app-id>/` blueprints (each must contain `hop3.toml`), e.g. your `hop3-catalog` checkout:

```bash
uv run hop3-catalog validate ./apps                     # optional: coexistence + structural gate
uv run hop3-catalog publish ./apps \
    --key ./keys/catalog.key \
    --out-dir ./dist \
    --serial 1
```

This writes `dist/catalog.tar.gz`, `dist/catalog.tar.gz.minisig`, and `dist/index.json`. The `--serial` must **strictly increase** on every republish the same server will fetch (anti-rollback); the default is the current Unix time, which is naturally monotonic.

## 2. Host it over HTTPS

Serve **both** the tarball and its signature at the same path, on a host whose TLS certificate is trusted by the server's CA store (Let's Encrypt is fine):

```
https://staging.example.com/catalog/catalog.tar.gz
https://staging.example.com/catalog/catalog.tar.gz.minisig
```

You do **not** host `index.json`; the server reads it from inside the tarball.

> The catalog fetch enforces TLS certificate + hostname verification and **cannot be disabled** (unlike the CLI's `--insecure`). A self-signed *TLS* cert on the staging host will fail; add its CA to the box's trust store or use a CA-issued cert. (A self-signed *signing* key, step 0, is the intended model — that's a different thing.)

## 3. Point the server at your staging catalog

`CATALOG_SOURCE_URL` defaults to `https://apps.hop3.cloud/catalog/catalog.tar.gz` and is overridable. Set it in the systemd env file (wins over `hop3-server.toml`):

```bash
# /etc/default/hop3
CATALOG_SOURCE_URL=https://staging.example.com/catalog/catalog.tar.gz
```

Restart `hop3-server` so the new value is read.

## 4. Fetch, browse, install, remove

```bash
hop3 catalog refresh                          # fetch -> verify signature -> anti-rollback -> publish -> reload
hop3 catalog list                             # ID / Title / Category / License
hop3 catalog install nextcloud --app mycloud  # stage the recipe + build & run, streaming logs live
hop3 app status --app mycloud                 # RUNNING / FAILED / ...
hop3 app destroy --app mycloud                # remove (a catalog app is a normal app)
```

`hop3 catalog install` deploys with the same live streaming output as `hop3 deploy`. The `--app` name is the **new** app to create; it is required (there is no ambient default for a create-style command). Add `--env KEY=VALUE` (repeatable) to seed environment variables.

The same flow is available in the **dashboard** at `/dashboard/catalog`: browse, open an app, and use the Install form, which stages the recipe and starts the deploy in the background, taking you to the app's live status page.

## Common snags

- **`No catalog signing public key is compiled into this build`**: step 0 not done (or the server wasn't redeployed after editing `keys.py`).
- **Signature verification fails**: the `catalog.key` you signed with is not the counterpart of the `catalog.pub` you baked in (they must share one keygen).
- **`refused as a rollback`**: the server already installed a serial ≥ the one you published. Bump `--serial`. (The high-water mark lives at `CATALOG_STATE_ROOT/serial`, outside the catalog dir, so a re-publish can't reset it.)
- **TLS error on fetch**: the staging host's cert isn't trusted by the server; see step 2.
- **`hop3 catalog install <id>` errors with "requires --app"**: pass `--app <name>`; the install target is a new app name, never inferred from the current directory.
