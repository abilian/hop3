# Directus native — deferred

**Last touched:** 2026-04-22. **Status:** blocker #1 cleared (build phase succeeds). Now blocked by blocker #8 (Node version).

## What was blocking

Directus's `npm install` compiles a native module that links against `libbrotli`:

```
npm ERR! /usr/bin/ld: cannot find -lbrotlidec: No such file or directory
```

The app's `hop3.toml` had `[build].packages = ["libbrotli-dev", "build-essential", "python3", "pkg-config"]` declared all along — but the server-side code parsed the field and never consumed it. Every native-profile Tier-A/B app built from Node source hit the same wall.

## Fix shipped (2026-04-22) — blocker #1

Installer-baseline-from-catalogue, per `local-notes/plans/isolation-strategy.md`:

1. **`[build].packages` / `[run].packages` are now canonical declarations** read by `hop3-installer` at server-provisioning time, not by the deploy pipeline.
2. **`hop3_installer/server_installer/baseline.py`** walks `apps/*/hop3.toml`, unions the declarations, translates per OS family via `package_aliases.py`, emits `baselines.py` (committed — CI check via `python -m … --check` verifies no drift against the catalogue).
3. **`hop3-install server` now installs the baseline** as part of step 1 (on top of the static `DEBIAN_BASE_PACKAGES`). Idempotent: rerun to pick up catalogue growth.
4. **`LocalBuilder` probes declared packages** before each native build runs. If something is missing it emits a `Diagnosis` naming the package + three remedies (rerun installer, add declaration & regenerate, switch profile) — replacing the opaque `pkg-config: not found` / linker errors.

Directus's existing declarations feed directly into the generated baseline — `libbrotli-dev` (debian) / `brotli-devel` (fedora) now ship in every Hop3 server. Same mechanism unlocks **Outline, Formbricks, Linkwarden, Hoppscotch, Joplin Server, Excalidraw, Budibase, Medusa** as their declarations land.

## Now blocked by #8 — Node 18 on the server, Directus 11 needs ≥22

2026-04-22 retry log: build phase clears (native modules compile, `isolated-vm` links fine now that libc-ares-dev/libnghttp2-dev/libicu-dev/libnode-dev are in the baseline). First run of the app then throws:

```
SyntaxError: Named export 'Type' not found. The requested module
'@sinclair/typebox' is a CommonJS module...
Node.js v18.19.1
```

Same ESM/CJS interop error the nix variant hit. Fixed there by pinning `${pkgs.nodejs_22}/bin` on the wrapper's PATH; native has no equivalent — the host ships whatever `apt install nodejs` provides.

**Unblocker:** blocker #8 — teach `hop3-installer` to provision Node 22 via NodeSource (or `nodeenv` per-app with `[build].node-version = "22"` in hop3.toml). Scope: separate installer feature, probably a half-day of real work plus a retry pass.

## To retry (after blocker #8 ships)

```
ssh root@hop3-dev.abilian.com 'hop3-install server --with=rust'
hop3-test system --ssh --host $HOP3_DEV_HOST --reuse apps/bad/real-apps-native-bad/directus
```

Once green, `git mv` to `apps/real-apps-native/directus/` and drop this note.

