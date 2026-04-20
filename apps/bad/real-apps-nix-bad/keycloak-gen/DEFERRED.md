# Keycloak nix-gen (nixpkgs-wrapper template) — deferred

**Deferred:** 2026-04-18. **Classification:** platform blocker — see `local-notes/stacks-and-apps/DEFERRED-APPS.md` blocker #12.

## Blocker

Keycloak's launcher `kc.sh start-dev` (and `start` — any start variant) runs an implicit `kc.sh build` step first. The `build` step is Quarkus augmentation: it writes `$KC_HOME_DIR/lib/quarkus/generated-bytecode.jar` and updates `$KC_HOME_DIR/data/`.

`KC_HOME_DIR` defaults to the install dir inferred from the `kc.sh` location. For the nixpkgs package, that's `/nix/store/<hash>-keycloak-26.1.4/` — **read-only**. The implicit build fails, Keycloak exits, uWSGI respawns it, throttling kicks in at 40s cycles, and the health check times out at `start-timeout`.

Observed symptom in `web.1.log`:

```
Updating the configuration and installing your custom providers, if any. Please wait.
...
ERROR: Failed to run 'build' command.
For more details run the same command passing the '--verbose' option.
```

## Why the wrapper hack doesn't belong in hop3.toml

The mechanical workaround is: copy the nixpkgs Keycloak tree into a writable per-app dir at `pre-exec`, set `KC_HOME_DIR=$PWD/keycloak-home`, change the exec target from `PKGBIN/kc.sh` to `$PWD/keycloak-home/bin/kc.sh`. Four concerns:

1. **Heavy** — copying ~200 MB of JARs and themes on every deploy.
2. **Template can't currently express it.** `nixpkgs-wrapper` has no hook for "copy package tree into a writable location at deploy time", and `exec-target` is templated against `PKGBIN` (sed-replaced at Nix build), not against a runtime-computed path.
3. **Loses Nix-store immutability.** One of the reasons we chose the nix-gen path was per-deploy reproducibility. A writable copy breaks that.
4. **Per CLAUDE.md "Project Ethos":** workarounds in `hop3.toml` are a warning sign that the platform couldn't express what the app needed cleanly. This is the classic case.

## Unblocker (platform work)

Two alternatives, either unblocks Keycloak plus any similar nixpkgs-packaged Quarkus/Java app that needs a writable install dir:

**Option A — bake the build at package time.** Extend the `nixpkgs-wrapper` template with a `build-phase` hook: a shell snippet that runs during the Nix derivation's `installPhase`, after copying/wrapping, so tools like `kc.sh build --db=postgres` pre-generate artifacts. Then `exec-args` becomes `start --optimized` which skips the runtime build. Clean, reproducible, DB-type has to be pinned per deploy.

**Option B — writable-overlay at deploy time.** Extend `nixpkgs-wrapper` with a `writable-home: true` (+ optional `writable-dirs: ["lib/quarkus", "data"]`) flag. The generated wrapper creates a tmpfs/overlay copy of the nix-store package into `$PWD/.hop3-home`, sets `KC_HOME_DIR` (or a template-specific env var), and execs there. Expensive on first deploy, but heals the gap for any app in this family.

Option A is cleaner but requires the app to know its config at package time. Option B is more general at a runtime cost. Pick based on which other apps are gated (Jenkins? Possibly Mattermost? Keycloak.)

## Config as left (for re-attempt)

See `hop3.toml` in this directory — uses `nixpkgs-wrapper`, declares `KC_DB=postgres` via `runtime-env`, injects `KC_DB_URL` / `KC_DB_USERNAME` / `KC_DB_PASSWORD` via `env-exports`, admin bootstrap env vars set. Everything the app needs *except* a writable home dir.

## Working variant path forward

Hand-crafted `apps/real-apps-nix/keycloak/hop3.nix` (not yet written) with the write-home workaround inline — viable for the 0.5 window. Can serve as reference for Option B template work in 0.6.
