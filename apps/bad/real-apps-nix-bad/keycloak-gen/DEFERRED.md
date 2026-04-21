# Keycloak nix-gen (nixpkgs-wrapper template) — deferred

**Last touched:** 2026-04-21. **Classification:** platform blocker — see `local-notes/stacks-and-apps/DEFERRED-APPS.md` blocker #12 and the new need for a `nixpkgs-overrides` template feature.

**Hand-crafted variant works.** `apps/real-apps-nix/keycloak/` ships a working Keycloak via the lazy-cp-to-writable-home pattern. This directory is the nix-gen probe: it documents which template capability is still missing so Keycloak could drop into the nix-gen flow cleanly.

## What today's session showed

Two nixpkgs-wrapper hooks shipped to unblock this class of app:

- **`[nix].install-extra`** — free-form shell appended to the Nix `installPhase`, emitted raw so `${pkg}` references interpolate at build time.
- **`[nix].exec-prefix`** — overrides `PKGBIN` in the wrapper's exec line, so `exec-target` can sit under `$out/<dir>/bin` instead of `${<pkg>}/bin`.

Four new unit tests cover them (`test_nix_gen_templates.py`).

The install-extra recipe for Keycloak was `cp -R ${keycloak}/. $out/keycloak-home; chmod -R u+w; rm -rf lib/quarkus; kc.sh build --db=postgres`. This fails on both macOS and Linux Nix sandboxes with:

```
java.nio.file.ReadOnlyFileSystemException
  at jdk.zipfs.ZipFileSystem.checkWritable
  ...
  at io.quarkus.deployment.pkg.steps.JarResultBuildStep.buildThinJar
```

Not a permissions issue (`u+w` took; `stat` confirms writable). Quarkus' `JarResultBuildStep` opens some JAR via `ZipFileSystem.newFileSystem` without `create: true` and then tries to `createDirectory` inside it. This behaviour of `kc.sh build` inside a partially-rebuilt tree is reproducible on both macOS Darwin and Linux — the hop3-dev test run on 2026-04-21 hit the same exception.

## Real fix — a different template feature

The cleanest path is to let **nixpkgs itself** run `kc.sh build --db=postgres`. The nixpkgs recipe (`pkgs/by-name/ke/keycloak/package.nix`) already does this in its own `buildPhase`:

```nix
export KC_HOME_DIR=$(pwd)
bin/kc.sh build ${featuresSubcommand}
```

and it accepts a `confFile` override:

```nix
+ lib.optionalString (confFile != null) ''
    install -m 0600 ${confFile} conf/keycloak.conf
''
```

So `pkgs.keycloak.override { confFile = pkgs.writeText "kc.conf" "db=postgres\n"; }` bakes the right DB profile at nixpkgs build time. Runtime then goes through `start --optimized` with `KC_DB_URL` env vars — no install-extra, no re-augmentation, no ReadOnlyFileSystemException.

**What the template needs:** a new `[nix].nixpkgs-overrides` field (dict of key → Nix expression) that generates:

```nix
keycloak = pkgs.keycloak.override {
  confFile = pkgs.writeText "kc.conf" "db=postgres\n";
};
```

in the let block instead of the current plain `keycloak = pkgs.keycloak;`.

This is narrower than today's install-extra (which is a general escape hatch) and solves the confFile-style family of cases cleanly:

- **Keycloak** — `confFile`
- **Jenkins** (nixpkgs) — `extraPlugins`, `extraJavaOpts`
- **Mattermost** (nixpkgs) — plugins override
- **Grafana** (nixpkgs) — `provisioning` overrides

## What stands from today regardless of the above

The install-extra + exec-prefix fields remain valid for the "bake-then-run-optimized" shape when nixpkgs doesn't already run the build, or when a custom post-install step is genuinely needed. They're shipped and tested; Keycloak just isn't the right first customer.

## Config in this dir as left

`hop3.toml` reverted to a plain `nixpkgs-wrapper` config with `start-dev`. It will fail the same way it did in 2026-04-20's triage (Quarkus tries to write `generated-bytecode.jar` inside `$NIX_STORE`). Pass it through again once the `nixpkgs-overrides` template field lands.

## Related

- `packages/hop3-server/src/hop3/plugins/build/nix/gen/spec.py` — `install_extra`, `exec_prefix` fields
- `packages/hop3-server/src/hop3/plugins/build/nix/gen/templates/nixpkgs_wrapper.py` — template emits them
- `apps/real-apps-nix/keycloak/` — working hand-crafted variant
- `local-notes/stacks-and-apps/DEFERRED-APPS.md` blocker #12
