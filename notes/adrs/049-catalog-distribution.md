# ADR 049: Catalog Distribution — Fetching App Specs from a Central Source

**Status**: Accepted
**Type**: Feature
**Created**: 2026-06-16
**Related-ADRs**: 013 (supply chain), 031 (terminology), 019 (CLI commands), 002 (config format)

## Context

The app **Catalog** (ADR 031) is a curated, self-hostable collection of installable app specs. Its content must come from a central source **we control**, not from a directory that happens to sit beside the code.

Today `CatalogService` resolves its data dir by walking seven parents up from `__file__`. That works in a dev checkout and **fails silently in production**: hop3-server runs from a wheel under `/home/hop3/venv`, the walk lands in `site-packages`, the directory doesn't exist, and the loader marks itself loaded with zero apps — a real box serves an empty catalog and calls it success. That silent-empty fallback is exactly what CLAUDE.md forbids, and closing it is the concrete trigger for this ADR.

Two constraints shape the design:

- **A catalog spec becomes code we run.** Installing an app copies the fetched spec's source into a new app and (once the deploy step is enabled) hands its `hop3.toml` to the builder to run as the `hop3` user. There is no trust boundary between "catalog content" and "code we execute," so authenticity is mandatory — and must be in place *before* the deploy step goes live.
- **Nodes pull; the source never pushes.** Hop3 nodes are self-hosted, typically behind NAT, with no inbound connectivity. The source must be pull-only, like APT, Helm, or YunoHost.

## Decision

Distribute the catalog as a **signed artifact pulled over HTTPS**, verified against a public key **pinned in the hop3-server release**, cached on disk, and loaded by the existing loader. Evolve in phases; do not build a dedicated catalog server yet.

### Phasing

| Phase | Source | Shape | Trigger |
|-------|--------|-------|---------|
| **v1** | Static files under `https://apps.hop3.cloud/catalog/` | One signed `catalog.tar.gz` | Baseline |
| **v2** | Same static host | `index.json` + per-app artifacts fetched on demand | When catalog size/icons make whole-tarball refresh wasteful |
| **v3** | Dedicated catalog service | API + per-app + transparency log | Post-NGI |

The per-app artifact shape — a directory of `<app-id>/{hop3.toml, readme.md, icon.*}` — is the boundary that does **not** change across phases. Shipping `index.json` inside the v1 tarball lets v2 move to fetch-on-demand without changing the format the node already understands.

### Trust model

HTTPS authenticates the *channel*, not the *author*; the realistic threat is compromise of the origin/bucket/CDN/CI, against which TLS is useless. So the root of trust is an **offline signature**: the catalog is trusted because the Hop3 release key signed it, independent of who serves the bytes. We use **minisign** (Ed25519 detached signatures), verified with the `cryptography` library Hop3 already depends on — no new dependency and no `minisign` binary in the path.

Two anchors live on the node and are never re-derived from whatever the origin currently serves:

- **The verifying public key is a compiled-in constant** in the server release — not a runtime file an attacker with a node foothold could swap. The private key never touches a production node.
- **A monotonic `serial`** in the signed index, persisted outside the catalog directory, blocks rollback to an older but validly-signed catalog.

This is the APT model in miniature — sign the index, the index hashes the artifacts — and aligns with ADR 013 (sha256 pinning; Sigstore deferred). The chain only holds if the **server-release channel is an independent trust root** from the catalog channel; today the catalog (`apps.hop3.cloud`) and the install one-liner (`hop3.cloud`) share the `hop3.cloud` parent domain and operator, so they are not yet independent trust roots — install-time origin integrity is a documented gap (below).

### How a refresh works

Catalog refresh runs as a sub-step of `hop3-server setup` (once, after dirs exist, before the service starts) and on demand via `hop3 catalog refresh` — never per request. It fetches the tarball and its signature over HTTPS into a staging area, **verifies the signature before opening the archive**, extracts with path confinement and resource caps, and then enforces the design's central invariant: the extracted tree must be **exactly** the file set named in the signed `index.json` — every listed file present with a matching hash, and nothing else on disk. Only then is the new version published, by an atomic symlink flip plus an in-process snapshot swap, and the new serial recorded.

Every failure aborts, leaves the previously verified catalog serving, and reports why. There is no "verification unavailable → load anyway" branch and no silent-empty or silent-stale fallback: a *verified* catalog with zero apps is allowed; a fetch or verification failure is surfaced, not seeded as empty. With no key compiled in, refresh refuses to run rather than fetch something it cannot verify.

### Producer side

The release process builds and signs the artifact offline with the `hop3-catalog` tool (`keygen` + `publish`): it assembles `index.json`, builds the tarball *from* that index (so the published tree is bijective with the signed index by construction), runs the coexistence gate on every spec before signing, and emits the detached signature. See `docs/src/developers/catalog-publishing.md`.

## Considered Alternatives

**Transport — git repo (pinned commit) instead of a tarball.** Viable, and a documented fallback (the repo tree *is* the catalog, Homebrew-tap style). Rejected for v1: it puts `git` in the fetch path, re-ships the whole tree per refresh, and has no clean atomic-verify-then-swap story. A tarball over HTTPS needs only stdlib `urllib` and swaps atomically.

**Integrity — bare HTTPS, no signature. Rejected.** For executed code this is negligent: one compromised static host = RCE across every node, and a `verify_ssl false` escape hatch already exists in the client.

**Integrity — an unsigned `sha256` next to the tarball. Rejected.** An attacker who can replace the tarball replaces the checksum in the same write. (Per-file sha256 is still useful *inside the signed* index — it just can't be the trust root.)

**Integrity — Sigstore/cosign + transparency log. Deferred.** The right end state (CRA-aligned, named in ADR 013) but it drags in OIDC/Rekor/Fulcio and verify-time network calls — wrong for a sovereign, simple v1. minisign is the proportionate middle: one keypair, a tiny detached sig, offline signing, no infra.

**Shape — index + per-app fetch from day one. Deferred to v2.** Correct at scale, but a single signed tarball is the simplest thing that works now and maps almost verbatim to today's directory-of-dirs loader.

## Security Considerations

Authenticity is **necessary but not sufficient** — a verified spec is still attacker- or mistake-shaped content. These are in v1 scope because v1 is the change that first makes catalog content installable; deferring them would ship a known hole. Each maps to a property in the table at the end.

- **Coexistence gate (F7).** A verified spec must not claim an unmanaged shared resource and break the "apps must coexist" invariant. The one such resource a `hop3.toml` can express is the reverse-proxy default server, so the gate rejects a catch-all (`"_"`) or wildcard host; it runs at publish time (primary) and as a load-time backstop. The gate deliberately does not re-validate builders, addons, or fixed ports: those are already constrained by the hop3.toml schema, the port registry, and per-app addon provisioning, so re-gating them would be redundant rather than defense-in-depth.
- **Untrusted readme/icon (F6).** The public icon route serves raster images only — never SVG, an inline-XSS vector — with `nosniff`, resolved within the app's own verified directory. The readme is rendered through an HTML-sanitizing allowlist.
- **Resource bounds (F9).** `hop3 catalog refresh` is dashboard-reachable, so download size, uncompressed size, and member count are capped to prevent a zip-bomb / disk-fill DoS with cross-tenant impact.
- **Privilege separation (F8, deferred hardening).** The `hop3` user verifies the catalog, owns the serial, *and* is the uid a bad spec runs as — so one compromise can disable future verification. Root-owned key/serial state is the hardening target; v1 verifies against the compiled-in constant and keeps the serial outside the catalog dir.
- **Install authorization.** Catalog-install runs with the server's deploy capability but is triggered by a dashboard user; "who may install" is part of this surface, tightened when the deploy step is enabled.

## Consequences

- **Fixes the current production bug**: a real box gets a real, verified catalog instead of a silently empty one.
- **New on the node**: a fetch / verify / atomic-publish path, a compiled-in pubkey constant, an anti-rollback serial outside the catalog dir, a coexistence gate, readme/icon sanitization, `CATALOG_SOURCE_URL` + `CATALOG_ROOT` config, and a `hop3 catalog refresh` command. No new dependency.
- **Changed**: the loader iterates the verified `index.json` instead of `iterdir()`; refresh swaps an immutable snapshot under a lock; the silent-empty load path is replaced with loud reporting.
- **New for the Hop3 team**: an offline signing key, the `hop3-catalog publish` release step, and the standing constraint that the server-release channel stay an independent trust root. Real cost, accepted as the price of not making one static host a fleet-wide RCE.
- **Unchanged**: `CatalogApp`, the dashboard controller, and the per-app artifact shape.

## Hardening Path

1. **v1**: single offline key compiled in; anti-rollback serial; index↔disk binding; coexistence gate.
2. **Rotation + revocation**: ship a *set* of trusted keys (current + next) compiled in, accept any, retire old keys in the next release; a leaked key is handled by a forced-update release that drops it (minisign has no online revocation).
3. **Privilege separation**: move the key/serial state to root ownership (F8).
4. **Dedicated server (v3)**: keep the same offline content-signing key (the server signs nothing it serves); add TLS pinning as defense-in-depth.
5. **Transparency + attestation**: Sigstore/Rekor + in-toto provenance and per-release SBOM (ADR 013); two-tier trust if third-party maintainers submit specs.

## Documented Gaps (accepted for v1)

- **Server-release channel integrity**: the wheel + install one-liner (`hop3.cloud`) and the catalog (`apps.hop3.cloud`) live under the same `hop3.cloud` parent domain and operator, so they are not yet genuinely independent trust roots; if that domain/hosting is compromised at install time the whole chain is moot. Needs its own integrity story (signed installer, independent host/key).
- **Signing-host / CI compromise**: a compromised signing environment produces a validly-signed malicious catalog. Mitigated only later by transparency logs / two-person signing.
- **Freshness beyond monotonic serial**: no signed timestamp/TTL, so a NAT'd manual-refresh node can sit on old-but-valid content with no staleness signal.
- **First-fetch bootstrap**: the first fetch sets the initial serial with nothing to compare against; a fresh node whose first fetch fails verification has no last-good and must start reporting "no catalog," never silently empty.

## Resolved Choices

- **Index format**: JSON (`index.json`, shipped inside the tarball).
- **Refresh cadence**: manual (`hop3 catalog refresh`) plus the setup sub-step; a systemd timer stays deferred.
- **minisign handling**: parse the format ourselves and use `cryptography`'s Ed25519 — no vendored parser, no minisign binary; output stays `minisign -V`-compatible.
- **Serial state home**: `HOP3_ROOT/catalog-state/`, outside `CATALOG_ROOT`.

## Security Properties (referenced from code as F1–F9)

| # | Property |
|---|----------|
| F1 | The signed `index.json` is authoritative for the file *set*: the extracted tree must be an exact bijection with it — no extra, missing, or mismatched files. |
| F2 | Publish is atomic: a versioned `catalog-<serial>/` dir, a symlink flip, and an in-process snapshot reference-swap under a lock. |
| F3 | The verifying public key is a compiled-in constant, not a runtime file. |
| F4 | A monotonic `serial`, persisted outside `CATALOG_ROOT`, blocks rollback to an older signed catalog. |
| F5 | Fetch/extract stage on the same filesystem as `CATALOG_ROOT`, never under a web-served path. |
| F6 | Icons are raster-only (never SVG) with `nosniff`; the readme is HTML-sanitized. |
| F7 | A coexistence gate rejects a spec that claims the reverse-proxy default/catch-all host. |
| F8 | *(Deferred)* privilege separation of the key/serial state from the `hop3` runtime uid. |
| F9 | Download, uncompressed, and member-count bounds guard against zip-bomb / disk-fill DoS. |

## References

- `docs/src/developers/catalog-publishing.md` — producer guide (keygen, publish, upload, rotation)
- ADR 013 — Software Supply Chain Security and SBOMs (sha256 pinning; Sigstore deferred)
- ADR 031 — Project Terminology (Catalog vs Marketplace)
- ADR 019 — CLI Commands
- YunoHost `catalog.json` + per-app git; Helm `index.yaml` + per-chart `.tgz` — closest analogues.
- Debian APT — "sign the index, the index hashes the artifacts."
- [minisign](https://jedisct1.github.io/minisign/) — Ed25519 detached signatures.
