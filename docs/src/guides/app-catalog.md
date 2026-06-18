# App Catalog

The **App Catalog** is a curated collection of ready-to-run applications you can browse from your Hop3 dashboard and install onto your server. Each catalog entry is a pre-written app specification (its `hop3.toml`, a README, and an icon), so you don't have to write deployment configuration from scratch for common apps like Nextcloud, Gitea, Miniflux, or WordPress.

The catalog is distributed to your server as a single signed bundle, fetched over HTTPS and verified before it is trusted (see [Where the catalog comes from](#where-the-catalog-comes-from)).

## Browsing the catalog

Open the dashboard and go to **Catalog** (`/dashboard/catalog`). You can:

- See **featured** apps and browse by **category** on the catalog home page.
- Search and filter the full list at **Catalog → All apps** (search matches an app's title, description, tags, and author).
- Open any app to see its full **README**, version, license, author, website, resource needs (a `light` / `medium` / `heavy` tier plus a memory hint), and an **Install** form.

Browsing and installing are done in the **web dashboard**. The command line has a single catalog verb, `hop3 catalog refresh`, for keeping the catalog up to date — see below.

## Installing and deploying an app

From an app's detail page, fill in the **Install** form:

- **App name** — the name your instance will have (lowercase letters, digits and `-`, 2–50 characters; e.g. `my-notes`).
- **Environment variables** (optional) — any values the app needs.

Installing **creates the app on your server, pre-seeded from the catalog**: it copies the catalog app's source into your new app and applies the environment variables you provided. You then **deploy** it — building and starting it — like any other Hop3 app:

```bash
hop3 deploy --app my-notes
```

> **Note:** installing from the catalog seeds and configures the app; it does not build or start it on its own. The deploy step above is what brings it up. (One-click "install *and* deploy" is planned but not yet enabled.)

After deployment, manage it exactly like a hand-configured app — `hop3 app status --app my-notes`, `hop3 app logs --app my-notes`, set a domain with `hop3 domain`, attach addons, and so on.

## Keeping the catalog up to date

The catalog is synced to your server **once during `hop3-server setup`** (best-effort — if the source is unreachable, setup still completes and warns you), and you refresh it on demand afterwards:

```bash
hop3 catalog refresh
```

On success it prints the new catalog **serial**:

```
Catalog refreshed to serial 42.
```

`refresh` downloads the latest signed bundle, verifies its signature, refuses any bundle older than the one you already have (anti-rollback), and swaps it in atomically. If anything fails — the source is unreachable, the signature doesn't verify, or the bundle is a rollback — the command **fails loudly and your current catalog is left untouched**:

```
Catalog refresh failed: Catalog source URL must be https://...
```

There is no automatic refresh timer yet; run `hop3 catalog refresh` when you want the newest apps.

## Where the catalog comes from

The catalog is a **signed artifact that your server pulls** — the source never pushes to your server. Authenticity is mandatory: because installing a catalog app runs code you didn't write, the bundle's signature is verified against a public key **built into your hop3-server release** (not a file on disk that could be swapped). A bundle that fails verification is rejected; it is never loaded "anyway."

The default source is Hop3's own catalog at `https://hop3.dev/catalog/catalog.tar.gz` (with a detached signature at the same URL plus `.minisig`). An empty-but-verified catalog is valid; a *failed fetch* is reported as an error, never silently treated as "zero apps."

## Configuration (operators)

These settings are read from the environment (or your server config); most deployments never change them.

| Setting | Default | Purpose |
|---------|---------|---------|
| `CATALOG_SOURCE_URL` | `https://hop3.dev/catalog/catalog.tar.gz` | The signed bundle to pull. Override to point at a **staging** catalog or an **air-gapped mirror**. Must be `https://` — the sync refuses any other scheme, and TLS verification is always on. |
| `CATALOG_ROOT` | `$HOP3_ROOT/catalog` | Where the active catalog lives (a symlink the sync manages). |
| `CATALOG_STATE_ROOT` | `$HOP3_ROOT/catalog-state` | Holds the anti-rollback serial, kept outside `CATALOG_ROOT` so it survives catalog swaps. |

The signing key is pinned in the release and is not operator-configurable. There is no option to disable signature or TLS verification — verification is not optional.

To serve your own catalog (e.g. a private internal mirror), publish a signed `catalog.tar.gz` + `catalog.tar.gz.minisig` over HTTPS, point `CATALOG_SOURCE_URL` at it, and ship a hop3-server build whose pinned key matches your signing key.

## "Catalog not available"

If the dashboard shows a yellow banner saying the catalog isn't available, no catalog has been synced to this server yet (for example, the source was unreachable during setup). Run:

```bash
hop3 catalog refresh
```

once the source is reachable. Hop3 deliberately reports this state rather than showing an empty catalog as if it had loaded successfully.
