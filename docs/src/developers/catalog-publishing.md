# Publishing a Catalog

Hop3 distributes its app **Catalog** as a **signed tarball pulled over HTTPS** (see
ADR 049). A node fetches `catalog.tar.gz` + its detached signature, verifies the
signature against a public key compiled into the release, checks the contents against
a signed index, and only then publishes it locally. Authenticity is not optional: a
catalog spec becomes code Hop3 runs, so one unsigned or tampered catalog would be a
fleet-wide remote-code-execution vector.

This page documents the **producer** side — how the Hop3 project builds and signs the
official catalog, and how you can run your own (Hop3 is sovereignty-first;
`CATALOG_SOURCE_URL` is configurable, so you can point your nodes at a catalog you
control).

The tool is `hop3-catalog` (shipped with `hop3-server`). It signs with the
`cryptography` library already bundled with Hop3 — **no `minisign` binary required** —
and its output verifies with both Hop3 and the stock `minisign -V`.

## 1. Generate a signing key (once)

Run this **on an offline / trusted machine**. The private key is the root of trust for
everything your nodes will execute — it must never touch a server.

```bash
hop3-catalog keygen --out-dir ./catalog-keys
# writes catalog-keys/catalog.pub  (public — ships in the release)
#        catalog-keys/catalog.key  (SECRET, mode 0600 — guard it)
```

Then bake the **public** key into the build that your nodes run:

- Edit `packages/hop3-server/src/hop3/server/catalog/keys.py`.
- Set `CATALOG_PUBLIC_KEY` to the base64 body line of `catalog.pub` (the second,
  non-comment line; the full file text also works).
- Commit and release. From then on, those nodes verify catalogs against this key.

**Key custody.** Losing the private key means you must rotate (§5). A *leaked* key is a
break-glass event: rotate **and** ship a release that drops the compromised key from the
trust set. Keep the `.key` offline (hardware token or sealed secret), never commit it,
never copy it to a node.

## 2. Build and sign (each release)

Lay out one directory per app — `content/<app-id>/` — each containing at least a
`hop3.toml` (plus an optional `readme.md` and a raster `icon.png`/`icon.webp`):

```bash
hop3-catalog publish content/ --key ./catalog-keys/catalog.key --out-dir dist/
# → dist/index.json, dist/catalog.tar.gz, dist/catalog.tar.gz.minisig
```

`publish` validates every spec through the coexistence gate **before signing** — a spec
that pins the nginx catch-all host `"_"` or a wildcard host is rejected here, because it
would hijack the reverse-proxy default server and shadow every other app on a node. The
tarball is built from the generated `index.json`, so the published tree is exactly the
signed file set — nothing more, nothing less.

`--serial` defaults to the current Unix time, which increases monotonically across
releases. Nodes enforce anti-rollback: a serial less than or equal to one a node already
holds is refused. If you set `--serial` manually, it must strictly increase.

## 3. Upload

Copy both files to your static host at the URL your nodes are configured to fetch
(`CATALOG_SOURCE_URL`, default `https://hop3.dev/catalog/catalog.tar.gz`):

```
https://hop3.dev/catalog/catalog.tar.gz
https://hop3.dev/catalog/catalog.tar.gz.minisig
```

HTTPS is mandatory — a node refuses a plaintext URL or an `https → http` redirect and
ignores any `verify_ssl false` client setting on this path. `index.json` travels inside
the tarball, so it does not need to be served separately.

## 4. Verify before announcing

Confirm the artifact verifies against the public key, then refresh a node:

```bash
python -c "
from pathlib import Path
from hop3.server.catalog.verify import verify_minisign
d = Path('dist')
verify_minisign(
    (d/'catalog.tar.gz').read_bytes(),
    (d/'catalog.tar.gz.minisig').read_text(),
    Path('catalog-keys/catalog.pub').read_text(),
)
print('OK')
"

# on a node, after upload:
hop3 catalog refresh        # fetch → verify → publish → reload; reports the serial
```

A failed fetch or verification leaves the previously verified catalog in place and
reports why — it never falls back to an empty or unverified catalog.

## 5. Key rotation

Ship a **set** of trusted keys (current + next) compiled into the release, accept any of
them, and retire old keys in a later release. There is no online revocation mechanism —
rotation is a release. `keys.py` currently holds a single key; widening it to a tuple is
the next hardening step.

## Using the `minisign` binary instead

If you prefer the stock tool, generate the key with `minisign -G` and sign with
`minisign -S -m catalog.tar.gz` (its default prehashed format), then bake that `.pub`
into `keys.py`. Hop3 verifies it identically. In that workflow you still use
`hop3-catalog publish` to build the index and tarball; only the signing step changes.
