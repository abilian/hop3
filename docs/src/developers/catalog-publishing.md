# Publishing a Catalog

Hop3 distributes its app **Catalog** as a **signed tarball pulled over HTTPS** (see ADR 049). A node fetches `catalog.tar.gz` + its detached signature, verifies the signature against a public key compiled into the release, checks the contents against a signed index, and only then publishes it locally. Every catalog must be authenticated: a catalog spec becomes code Hop3 runs, so one unsigned or tampered catalog would be a fleet-wide remote-code-execution vector.

This page documents the **producer** side: how the Hop3 project builds and signs the official catalog, and how you can run your own (Hop3 is sovereignty-first; `CATALOG_SOURCE_URL` is configurable, so you can point your nodes at a catalog you control).

The tool is `hop3-catalog` (shipped with `hop3-server`). It signs with the `cryptography` library already bundled with Hop3 (**no `minisign` binary required**), and its output verifies with both Hop3 and the stock `minisign -V`.

> **Recommended — the catalog repo drives it.** The official catalog is its own repository ([`git.sr.ht/~sfermigier/hop3-catalog`](https://git.sr.ht/~sfermigier/hop3-catalog)), which holds **both** the content (`apps/<status>/<app-id>/`) and the deployable static site that serves it (`hop3.toml` + `public/`). A `Makefile` there runs the whole release from that one directory:
>
> ```bash
> cd hop3-catalog
> make publish CONTEXT=<ctx>    # validate → sign → verify → stage → deploy
> ```
>
> `hop3-catalog` (the signing tool) resolves from the repo's `hop3-server` dependency, so `uv run` is all you need; `make deploy` uses the `hop3` client. The numbered steps below are exactly what each `make` target runs — follow them by hand if you publish some other way.
>
> The official public key is already pinned in the release (`hop3/server/catalog/keys.py`, id `fa06cb6b08e36105`), so §1 is only for **rotating** the key or running an **independent** catalog. The dev-only variant — sideloading a signed catalog onto your own box with no HTTPS host and no baked-in key — is [`stage-catalog.sh`](catalog-staging.md).

## 1. Generate a signing key (once)

Run this **on an offline / trusted machine** (`make keygen`, or directly). The private key is the root of trust for everything your nodes will execute, so it must never touch a server.

```bash
hop3-catalog keygen --out-dir ./keys
# writes keys/catalog.pub  (public — ships in the release)
#        keys/catalog.key  (SECRET, mode 0600 — guard it, never commit)
```

Then bake the **public** key into the build that your nodes run:

- Edit `packages/hop3-server/src/hop3/server/catalog/keys.py`.
- Set `CATALOG_PUBLIC_KEY` to the base64 body line of `catalog.pub` (the second,
  non-comment line; the full file text also works).
- Commit and release. From then on, those nodes verify catalogs against this key.

**Key custody.** Losing the private key means you must rotate (§5). A *leaked* key is a break-glass event: rotate **and** ship a release that drops the compromised key from the trust set. Keep the `.key` offline (hardware token or sealed secret), never commit it, never copy it to a node.

## 2. Build and sign (each release): `make build`

Content is one directory per app under `apps/<status>/<app-id>/`, where the directory naming the status is what records it ([ADR 059](adrs/059-catalog-maturity-status.md)); each app directory holds at least a `hop3.toml` (plus an optional `readme.md` and a raster `icon.png`/`icon.webp`). Publish walks the hierarchy and emits a **flat** `<app-id>/…` tree, so the signed artefact's shape is unchanged, and it refuses a recipe whose status is not publishable rather than dropping it silently. `make build` validates then signs:

```bash
make build                       # = validate, then:
hop3-catalog publish apps/ --key keys/catalog.key --out-dir dist/ --serial $(date +%s)
# → dist/index.json, dist/catalog.tar.gz, dist/catalog.tar.gz.minisig
```

`publish` validates every spec through the coexistence gate **before signing**. A spec that pins the nginx catch-all host `"_"` or a wildcard host is rejected here, because it would hijack the reverse-proxy default server and shadow every other app on a node. The tarball is built from the generated `index.json`, so the published tree is exactly the signed file set.

`--serial` must **strictly increase** on every republish a node will fetch: a node records the highest serial it has installed (`CATALOG_STATE_ROOT/serial`) and refuses anything less than or equal to it as a rollback. The `$(date +%s)` default is naturally monotonic, but two `make build` runs in the same second, or a machine whose clock has moved backward, collide, and the node then silently rejects the newer tarball as a rollback. Pass `--serial` explicitly when you need to guarantee the increment.

## 3. Verify before deploying: `make verify`

`make verify` confirms the freshly-built artifact verifies against the public key, catching a wrong or rotated signing key *before* anything ships. `make publish` runs it between `build` and `deploy`.

```bash
make verify        # = verify_minisign(dist/catalog.tar.gz, .minisig, keys/catalog.pub)
```

## 4. Deploy the site: `make stage` + `make deploy`

`apps.hop3.cloud` is itself a **Hop3-deployed static app**, and this repo *is* that app: a `hop3.toml` (a `static` app bound to host `apps.hop3.cloud`) plus a `public/` web root. `make stage` copies the signed artifacts into `public/catalog/`, and `make deploy` ships the site with `hop3`:

```bash
make stage                     # cp dist/catalog.tar.gz{,.minisig} → public/catalog/
make deploy CONTEXT=<ctx>      # hop3 --context <ctx> deploy --app apps-hop3-cloud
```

so nodes fetch them at `https://apps.hop3.cloud/catalog/catalog.tar.gz` (+ `.minisig`).

**The signing key never ships.** `hop3 deploy` uploads a tar of the working directory, and this repo also holds `keys/catalog.key`. The site's `hop3.toml` guards against that with an allowlist `[build].ignore`:

```toml
ignore = ["**", "!/public/", "!/public/**", "!/hop3.toml"]
```

so the upload contains **only** `public/` + `hop3.toml`, never `keys/`, `dist/`, `apps/`, or any `*.key`. Anything new in the repo stays excluded by default (fail-safe).

Deploy to the server `apps.hop3.cloud` actually resolves to, picking it with `CONTEXT=<name>`; deploying to the wrong box means the domain won't reach it. HTTPS is mandatory on the node side: a node refuses a plaintext URL or an `https → http` redirect and ignores any `verify_ssl false` client setting on this path. `index.json` travels inside the tarball, so it is not served separately. (Serving the catalog some other way, from object storage or a plain nginx root, also works: just place the two files at `CATALOG_SOURCE_URL`.)

**Confirm the deploy took.** `hop3 deploy` reporting success means the upload landed, which is not the same as the domain serving your new bytes. A wrong `CONTEXT`, or a cache in front of the host, would leave the *old* catalog live while the release looked green. Check the live artifact against what you signed before announcing:

```bash
curl -fsSL https://apps.hop3.cloud/catalog/catalog.tar.gz | sha256sum
sha256sum dist/catalog.tar.gz            # the two hashes must match
```

Then, on any node:

```bash
hop3 catalog refresh        # fetch → verify → anti-rollback → publish → reload
```

A failed fetch or verification leaves the previously verified catalog in place and reports why. It never falls back to an empty or unverified catalog.

## 5. Key rotation

Ship a **set** of trusted keys (current + next) compiled into the release, accept any of them, and retire old keys in a later release. There is no online revocation mechanism: rotation is a release. `keys.py` currently holds a single key; widening it to a tuple is the next hardening step.

## Using the `minisign` binary instead

If you prefer the stock tool, generate the key with `minisign -G` and sign with `minisign -S -m catalog.tar.gz` (its default prehashed format), then bake that `.pub` into `keys.py`. Hop3 verifies it identically. In that workflow you still use `hop3-catalog publish` to build the index and tarball; only the signing step changes.
