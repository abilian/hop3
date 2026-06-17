# ADR 049: Catalog Distribution — Fetching App Specs from a Central Source

**Status**: Accepted (phased — v1 node + producer code shipped; signing key, published content, and the install→deploy step deferred)
**Type**: Feature
**Created**: 2026-06-16
**Related-ADRs**: 013 (supply chain), 031 (terminology), 019 (CLI commands), 002 (config format)

## Revisions

- v0.3 (2026-06-17): Accepted and implemented. Node side (`catalog/{verify,sync,
  service,loader,policy,refresh,keys}.py`, the `catalog refresh` command, the
  `hop3-server setup` sub-step) and the producer side (`catalog/publish.py` +
  `hop3-catalog` CLI) are landed and round-trip-tested. The F7 gate shipped
  **narrower** than v0.2 specified — see the corrected F7 below. Remaining work is
  out-of-band: bake a real signing key into `keys.py`, curate + publish content to
  `https://hop3.dev/catalog/`, and enable `app.deploy()` in `catalog_install`.
- v0.2 (2026-06-16): Security review (see `/security-review` of this file). Tightened
  three high-severity gaps into the v1 design — the signed index is now **authoritative
  for the file set** (loader iterates the verified index, not `iterdir()`); the
  "atomic swap" is specified as a symlink flip + in-process snapshot reference-swap
  under a lock; the pinned key is a **compiled-in constant** and the server-release
  channel is scoped as an independent trust root. Pulled the coexistence
  spec-validation gate, readme/SVG sanitization, the write-protected anti-rollback
  serial, hardened staging, and download/decompression bounds **into v1 scope**.
  Corrected two over-stated threat claims (deploy is currently stubbed; `readme_html`
  is not yet rendered). Added a documented-gaps section.
- v0.1 (2026-06-16): Initial draft.

## Context

The app **Catalog** (ADR 031 — the free, self-host collection of installable app
specs) needs its content from a central source **we control**, not from a
directory that happens to sit next to the code. Today `CatalogService.ensure_loaded()`
resolves its data dir by walking seven parents from `__file__` to a presumed
`repo_root/apps/catalog`. That works in a dev checkout and **fails silently in
production**: hop3-server runs from a wheel under `/home/hop3/venv`, so the walk
lands inside `site-packages`, the dir does not exist, and the `else` branch sets
`self._loaded = True` with **zero apps** — a real box serves an empty catalog and
calls it success. That is exactly the silent-empty fallback CLAUDE.md forbids, and
it is the concrete gap this ADR closes.

Constraints that shape the design:

- **Nodes pull; the source never pushes.** Hop3 nodes are self-hosted, typically
  behind NAT/a firewall, with no guaranteed inbound connectivity. The central
  source must be pull-only (like APT, Helm, YunoHost).
- **Sovereignty + simplicity.** Prefer static hosting and stdlib over a service and
  new dependencies. A dedicated catalog server is explicitly *later* work.
- **A catalog spec becomes executed code.** `catalog_install` copies the fetched
  spec's source verbatim into a new app (`_copy_catalog_source`) and is wired to
  deploy it — `app.deploy()` is the explicit next step (today stubbed behind a
  `# TODO: Phase 4` at `controllers/catalog.py:266`). Once that line is live, the
  spec's `hop3.toml` (`[build]`/`[run]`/`[[addons]]`) flows to the
  builder/toolchain/deployer and runs as the `hop3` user. There is no trust boundary
  between "catalog content" and "code we run" — so authenticity is not optional, and
  it must be in place *before* the deploy step is enabled, not after.
- **Fail loud.** Fetch/verify failures must surface where the user looks and must
  never degrade to a stale-unmarked or empty catalog presented as success.

## Decision

Distribute the catalog as a **signed artifact pulled over HTTPS**, verified against a
public key **pinned in the hop3-server release**, cached on disk, and loaded by the
existing loader. Evolve in phases; do not build the dedicated server now.

### Phasing

| Phase | Source | Shape | When |
|-------|--------|-------|------|
| **v1** (this ADR) | Static files under `https://hop3.dev/catalog/` | One signed `catalog.tar.gz` | Now |
| **v2** | Same static host | `index.json` + per-app artifacts fetched on demand | When catalog size/icons make whole-tarball refresh wasteful |
| **v3** | Dedicated catalog service | API + per-app + transparency log | Post-NGI |

The **per-app artifact shape is the boundary that does not change** across phases:
each app is a directory of `<app-id>/{hop3.toml, readme.md, icon.*}`, and `CatalogApp`/
the dashboard controller are untouched. What *does* change in v1: `load_apps` no
longer trusts whatever directories happen to be on disk (`iterdir()`) — it iterates
the **verified `index.json`** and loads only indexed, hash-checked apps (see F1 in the
fetch flow).

### v1 concrete design

**Central side** — publish to `https://hop3.dev/catalog/`:
- `catalog.tar.gz` — contains `index.json` and the per-app directories above.
  `index.json` is the **authoritative manifest**: a monotonic `serial`, a `format`
  version, and for every app `{ id, version, files: [{path, sha256}], title,
  description, tags, category, icon }`. The `files` list enumerates **every** file
  the node should have — nothing on disk outside it is trusted (F1).
- `catalog.tar.gz.minisig` — a detached **minisign** (Ed25519) signature over the
  tarball, produced **offline** by the Hop3 release key. Signing the tarball pins the
  bytes; `index.json` (inside it) pins the file *set* — both matter (see F1).

Shipping `index.json` *inside* the v1 tarball from day one means v2 can move to
fetch-on-demand without changing the format the node already understands.

**Node side**:
- New config `CATALOG_SOURCE_URL` on `HopConfig` (default
  `https://hop3.dev/catalog/catalog.tar.gz`), mirroring `ACME_SERVER`.
- New derived path `CATALOG_ROOT = HOP3_ROOT/catalog`, added to `ROOT_DIRS` so
  `hop3-server setup` creates it. `CATALOG_ROOT` is a **symlink** to a versioned
  `catalog-<serial>/` dir (F2).
- The verifying public key is a **compiled-in constant** in the hop3-server package
  (not a file read at runtime — F3). The server-release channel (wheel + installer
  one-liner) is a **distinct trust root** from the catalog channel; if a
  `catalog-pubkey.pub` file is also shipped it is decorative — the constant is
  authoritative. Compromise of the server-release channel is explicitly out of scope
  for this ADR (see Documented Gaps).

**Fetch flow** (new `catalog/sync.py`):

1. **Stage**: create a per-run staging dir with `tempfile.mkdtemp(mode=0o700)` on the
   *same filesystem* as `CATALOG_ROOT` (so the final swap is atomic), never under a
   web-served path (F5). HTTPS GET the tarball + `.minisig` into it, enforcing a hard
   **byte ceiling** while reading (F9). TLS errors hard-fail; an `https→http` redirect
   aborts; the CLI's `verify_ssl false` is **ignored** here.
2. **Verify signature** on the on-disk tarball file — against the compiled-in key —
   *before* `tarfile.open` (Ed25519 via the existing `cryptography` dep, **no new
   dep**). Failure → abort, keep last-good.
3. **Extract** into staging with path confinement: resolve each member's real target
   against the staging realpath and reject absolute paths, `..`, and escaping
   symlinks/hardlinks before any write (no zip-slip); cap **uncompressed bytes and
   member count** and require free disk before extracting (F9).
4. **Bind index to disk (F1)**: verify `index.json` parses, then require an exact
   bijection — every file in `index.list` exists with a matching `sha256`, and **no
   file on disk is absent from the index**. Any mismatch, missing, or extra file →
   all-or-nothing abort.
5. **Anti-rollback (F4)**: refuse if `index.serial <=` the high-water-mark, which is
   persisted **outside `CATALOG_ROOT`** (so a swap/teardown can't reset it) in
   write-protected state; a *missing* high-water-mark means "unknown → first-boot
   bootstrap," never "start from 0."
6. **Swap (F2)**: the verified tree is `catalog-<serial>/`; publish it by atomically
   flipping the `CATALOG_ROOT` symlink (`os.replace` of a temp symlink). Then build a
   fully-populated `CatalogService` snapshot off to the side and swap the singleton's
   object reference **under a lock** in one assignment — readers see only the old or
   the new complete state, never a half-rebuilt one. Persist the new serial and report
   success **only after** both the symlink flip and the reference swap succeed. GC the
   old version dir afterward.

Any failure leaves the previously verified catalog serving, cleans up staging, and
reports the reason. The loader iterates the verified `index.json`, not `iterdir()`.

**Where sync runs**: a sub-step of `hop3-server setup` (runs once, as the `hop3`
user, after dirs exist and before the service starts) plus an explicit
`hop3 catalog refresh` (RPC/CLI) for updates. Not per-request. A systemd timer is
deferred. `ensure_loaded()` is changed to resolve `CATALOG_ROOT` from config and the
silent-empty `else` is replaced: a *verified* catalog with 0 apps is allowed; a
missing/failed fetch is reported, not seeded as empty.

### Integrity — the trust chain

HTTPS authenticates the *channel*, not the *author*; the dominant realistic threat
is compromise of the origin/bucket/CDN/CI, against which TLS is useless. So the root
of trust is the **offline signature**: content is trusted because the Hop3 release
key signed it, independent of who serves the bytes. The verifying key is a
**compiled-in constant** in the server release (not a runtime file an attacker with a
node foothold could swap alongside `sync.py` — F3); the private key never touches a
production node. A monotonic `serial` in the signed index closes the rollback gap.
This is the APT model in miniature (sign the index, the index hashes the artifacts)
and aligns with ADR 013, which already pins by sha256 and defers heavyweight
attestation.

The chain only holds if the **server-release channel is a genuinely independent
trust root** from the catalog channel. Today both originate from `hop3.dev` (the
catalog *and* the `curl … | sudo python3` install one-liner), so origin compromise at
install time could ship a malicious verifier+key. v1 scopes server-release integrity
as out of scope (Documented Gaps); the install one-liner needs its own integrity
story, tracked separately.

## Considered Alternatives

**Transport — git repo (pinned commit) instead of a tarball.** Viable and a
documented fallback (the repo tree *is* the catalog, Homebrew-tap style); the
codebase already shells out to git. Rejected for v1: it puts a `git` runtime
dependency in the fetch path, re-ships the whole tree on every refresh, and has no
clean atomic-verify-then-swap story. Tarball over HTTPS needs only stdlib
`urllib.request` (already the established download mechanism in server and installer)
and verifies/swaps atomically.

**Integrity — bare HTTPS, no signature. REJECTED.** For executed code this is
negligent: one compromised static host = RCE across every node, and a
`verify_ssl false` escape hatch already exists in the client.

**Integrity — an unsigned `sha256` file next to the tarball. REJECTED.** An attacker
who can replace the tarball replaces the checksum in the same write; it catches
corruption, not tampering. (The per-artifact sha256 is still useful *inside the
signed* index — it just cannot be the trust root.)

**Integrity — per-publisher signing certs (Nextcloud-style). REJECTED for now.**
Overkill for a curated single-vendor catalog. Revisit only if third-party
maintainers submit specs (two-tier trust — see Hardening).

**Integrity — Sigstore/cosign + transparency log. DEFERRED.** The right end state
(CRA-aligned, named in ADR 013) but it drags in OIDC/Rekor/Fulcio and network calls
at verify time — wrong for a sovereign, simple v1. minisign is the proportionate
middle: one Ed25519 keypair, a ~100-byte detached sig, offline signing, no infra.

**Shape — index + per-app fetch from day one. DEFERRED to v2.** Correct at scale,
but a single signed tarball is the simplest thing that works now and maps almost
verbatim to today's directory-of-dirs loader. We ship the index format inside the
tarball so the move is non-breaking.

## Security Considerations

Authenticity is **necessary but not sufficient** — a *verified* spec is still
attacker- or mistake-shaped content. These are **in v1 scope**, because v1 is the
change that first makes catalog content installable; deferring them ships a known hole:

- **Spec-validation gate (F7)**: a hard gate that refuses a verified-but-hostile spec
  from claiming an **unmanaged shared resource** ("apps must coexist", CLAUDE.md). As
  shipped (`catalog/policy.py`) the gate is deliberately **narrow**: the only such
  resource a `hop3.toml` can actually express is the reverse-proxy default server, so
  it rejects a `[domains]` (or per-`[context]`) host that is the nginx catch-all `"_"`
  or a wildcard. The v0.2 wording ("allowlist builders/addons, reject fixed ports/
  undeclared addon slots") was pared back because those concerns are *already*
  platform-constrained — `[build].builder` by the strict hop3.toml schema, `[[ports]]`
  by Hop3's port registry (reserved ports conflict-refused), `[[addons]]` by per-app
  provisioning — so re-gating them here would be redundant, not defense-in-depth. The
  gate runs at **publish time** (the primary place, before signing — in
  `publish.build_index`) and again as a **load-time backstop** on the node (fail loud,
  name the spec, exclude it). Today `catalog_install` validates only the user-chosen
  app *name*; this gate is new.
- **icon/readme XSS (F6)**: the icon route is genuinely public (`guards=[]`) and serves
  `icon.svg` as `image/svg+xml` — a live stored-XSS sink the moment the catalog holds
  attacker-influenced content (which is exactly what this ADR enables). Drop SVG from
  the allowed set, or serve with `Content-Disposition: attachment` +
  `X-Content-Type-Options: nosniff` + sandbox CSP; add a `realpath` ancestry check on
  the `apps_dir/<app_id>/icon.*` join. `readme_html` is *computed* by the loader but
  not currently rendered by any template (latent, not live) — sanitize it with an
  allowlist (nh3/bleach) or disable raw-HTML passthrough **before** it is ever wired
  into the detail page.
- **Install authorization**: catalog-install runs with the server's deploy
  capability but is triggered by a dashboard user; "who may install" is part of the
  supply-chain surface.
- **Resource bounds (F9)**: cap download size, uncompressed size, and member count —
  `hop3 catalog refresh` is dashboard-reachable, so an oversized/zip-bomb artifact is a
  remotely-triggerable disk-fill DoS with cross-tenant impact (co-located apps + the
  SQLite DB under `HOP3_ROOT`).
- **Privilege separation (F8, defense-in-depth)**: the `hop3` user verifies the
  catalog, owns the high-water-mark, *and* is the uid a bad spec executes as — so one
  compromise can disable future verification. Prefer root-owned key/serial state where
  feasible; at minimum verify against the compiled-in constant, not on-disk material
  the `hop3` user can edit, and alert on high-water-mark decreases.

**Fail-loud points** (no silent fallback anywhere in this path):

- Signature invalid / `.minisig` missing/unreachable/unparseable → abort, keep
  last-good, surface `Catalog can't update: signature invalid …, using last verified
  catalog (serial N)`. No "verification unavailable → load anyway" branch may exist.
- Any per-file `sha256` mismatch → all-or-nothing abort, name the file.
- **Index↔disk mismatch (F1)** → a file on disk not named in the signed index, or an
  indexed file missing, is a hard abort (same severity as a hash mismatch).
- Download/uncompressed/member-count over the cap (F9) → abort before/while extracting.
- `serial <= ` high-water-mark → refuse (possible rollback), report it.
- Truncated/partial download → raise; `tomllib` parsing a truncated file is not proof
  of completeness — the signed index covering every expected file is.
- TLS error / `https→http` redirect → hard-fail; ignore `verify_ssl false`.
- Atomic swap only after all checks; never report "updated" unless the swap happened
  and verified (no optimistic success).
- Replace the existing `ensure_loaded` silent-empty path and `loader.py`'s
  warn-and-`return None`-on-parse-error: distinguish *verified-empty* (allowed) from
  *fetch/parse failure* (must raise/report).

## Consequences

- **Fixes the current production bug**: a real box gets a real, verified catalog
  instead of a silently empty one.
- **New on the node**: `catalog/sync.py` (fetch + verify-sig + index↔disk bind +
  symlink swap), a compiled-in pubkey constant, write-protected high-water-mark state,
  a spec-validation gate, readme/icon sanitization, `CATALOG_SOURCE_URL` +
  `CATALOG_ROOT` config, a `hop3 catalog refresh` command, a `hop3-server setup`
  sub-step. No new dependency (`cryptography` already present; `urllib` for fetch).
- **Changed**: `load_apps` iterates the verified `index.json` instead of `iterdir()`
  (F1); `CatalogService` refresh swaps an immutable snapshot reference under a lock
  (F2); the silent-empty `ensure_loaded` else and the warn-and-`return None` loader
  path are replaced with loud reporting.
- **New for the Hop3 team (operational)**: an offline catalog signing key, the
  `hop3-catalog publish` step in the release process (the tool now exists), and the
  constraint that the server-release channel stay an independent trust root. Real
  cost, accepted as the price of not making one static host a fleet-wide RCE.
- **Unchanged**: `CatalogApp`, the dashboard controller, the per-app
  `hop3.toml`+readme+icon artifact shape.

## Hardening Path

1. **v1**: single offline minisign key compiled into the release; `serial`
   anti-rollback in write-protected state; index↔disk binding; spec-validation gate.
2. **Rotation + revocation**: ship a *set* of trusted public keys (current + next) as
   a compiled-in constant (not a served list); accept any; retire old keys in the
   following release. Define a revocation/break-glass story for a *leaked* signing key
   (minisign has none natively) — at minimum, a forced-update release that drops the
   compromised key from the trust set.
3. **Privilege separation**: move the pinned key/serial state to root ownership so a
   `hop3`-user compromise cannot silently re-key or roll back (F8).
4. **Dedicated server (v3)**: keep the same offline content-signing key (the server
   signs nothing it serves), and add TLS cert/pubkey pinning as defense-in-depth.
5. **Transparency + attestation**: adopt Sigstore/Rekor + in-toto provenance and
   per-release SBOM (ADR 013, CRA-aligned); two-tier trust if third-party maintainers
   submit specs. minisign stays as a local belt-and-suspenders check.

The verifying key and the serial high-water-mark are anchored on the node, so trust
is never re-derived from whatever the origin currently serves.

## Documented Gaps (accepted for v1, not yet mitigated)

These are known and deliberately out of v1 scope; named here so they are not mistaken
for oversights:

- **Server-release channel integrity**: the wheel + `curl … | sudo python3` installer
  carry the pinned key and verifier from the same `hop3.dev` origin the catalog uses.
  If that origin is compromised at install time, the whole chain is moot. Needs its
  own integrity story (signed installer, independent host/key).
- **Signing-host / CI compromise**: a compromised offline-signing environment produces
  a validly-signed malicious catalog that passes every on-node check. Mitigated only
  later by transparency logs / 2-person signing.
- **Key revocation**: covered as hardening, absent in v1.
- **Freshness beyond monotonic serial**: no signed timestamp/TTL, so a NAT'd
  manual-refresh node can sit on old-but-valid content indefinitely with no staleness
  signal.
- **Trust-on-first-use bootstrap**: the first fetch at `hop3-server setup` sets the
  initial high-water-mark with nothing to compare against. A fresh node whose first
  fetch *fails* verification has no last-good — the server must start and report
  "no catalog," not silently run empty or block boot.

## Open Questions (resolved at implementation)

1. **Index format**: **JSON**. `index.json` ships inside the tarball; `publish.py`
   emits it, `verify`/`loader` consume it.
2. **Refresh cadence default**: **manual-only** for v1 (`hop3 catalog refresh` + a
   best-effort `hop3-server setup` sub-step). A systemd timer stays deferred.
3. **Minisign format handling**: **parse it ourselves** and call `cryptography`'s
   Ed25519 (`verify.py` for verify, `publish.py` for sign) — no vendored parser, no
   `minisign` binary in the path. Output stays `minisign -V`-compatible.
4. **Home for the anti-rollback serial**: **`HOP3_ROOT/catalog-state/`**
   (`CATALOG_STATE_ROOT`), outside `CATALOG_ROOT` so a swap/teardown can't reset it.
   Root-owned state (F8) remains a deferred hardening step.

## References

- ADR 013 — Software Supply Chain Security and SBOMs (sha256 pinning; Sigstore deferred)
- ADR 031 — Project Terminology (Catalog vs Marketplace)
- ADR 019 — CLI Commands (deferred `hop3 search`/`info`/`install`)
- YunoHost `catalog.json` + per-app git; Helm `index.yaml` + per-chart `.tgz` on static hosting — the closest analogues.
- Debian APT — the "sign the index, the index hashes the artifacts" chain.
- [minisign](https://jedisct1.github.io/minisign/) — Ed25519 detached signatures.
