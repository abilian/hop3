# Directus native — deferred

**Reason:** Directus's npm install compiles a native module that links against `libbrotli`:

```
npm ERR! /usr/bin/ld: cannot find -lbrotlidec: No such file or directory
```

The fix is trivial in principle — install `libbrotli-dev` on the host — but the `[build].packages` field in `hop3.toml` is parsed by `Hop3Config.build_packages` (see `packages/hop3-server/src/hop3/project/hop3_config.py:224`) and **not consumed anywhere in the build pipeline**. A grep across the server code confirms: no caller reads `build_packages`.

This is a gap in Hop3 itself, not in the application packaging. Until the server implements `[build].packages` apt-install (or an operator manually runs `sudo apt-get install libbrotli-dev build-essential python3 pkg-config` on the host), the Directus native variant cannot build.

**Working variants (kept):**
- `apps/real-apps-docker/directus/` — Dockerfile installs libbrotli-dev directly, no Hop3 change needed.
- `apps/real-apps-nix/directus/` — Nix-packaged brotli via `${pkgs.brotli}` closure, no host deps.

**Unblocker (in priority order):**

1. **Teach the build pipeline to honour `[build].packages`.** `Hop3Config.build_packages` already returns the list; a caller in the deploy orchestration needs to hand it off to the OS plugin's `package_install()` (the protocol is already defined in `hop3/core/protocols.py`). ~20 lines + a test.
2. **Alternative:** declare the native runtime dependency closure via a richer mechanism (e.g. `nativeBuildInputs`-style list that covers both build and runtime libs).
3. **Workaround for operators today:** ssh into the Hop3 server and `sudo apt-get install -y libbrotli-dev build-essential python3 pkg-config` manually before deploying Directus.

Same pattern will hit **Outline, Formbricks, Linkwarden, Hoppscotch, Joplin Server, Excalidraw, Budibase, Medusa** — the entire Node-distributed Tier-A/B catalogue. Fixing the general mechanism is worth more than patching each app.
