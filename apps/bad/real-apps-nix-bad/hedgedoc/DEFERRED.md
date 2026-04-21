# HedgeDoc (nix) — deferred

**Last investigated:** 2026-04-21.

## Current state

Packaging switched from hand-crafted `hop3.nix` (pre-built release tarball + `cp -r`) to the `nixpkgs-wrapper` template against `pkgs.hedgedoc` 1.10.7. Build is clean; the binary `${hedgedoc}/bin/hedgedoc` is produced by nixpkgs with a proper Node wrapper (NODE_ENV, NODE_PATH pre-set).

## What's blocking

At runtime the daemon crashes instantly with:

```
TypeError: Cannot read properties of undefined (reading 'dbURL')
    at Object.<anonymous> (/nix/store/.../share/hedgedoc/lib/config/index.js:153:15)
```

Config-loading time (inside `require('./config')`). Line 153 of the installed file doesn't match upstream HedgeDoc 1.10.7 source — something in the `yarn run build` step that nixpkgs runs transforms the file layout. Without access to the running server's filesystem (per our "no server access" discipline), I can't inspect the transformed file to see which expression is dereferencing `undefined`.

Env vars I've tried (all set via `[nix.env-exports]`):

- `CMD_DB_URL`, `CMD_PORT`, `CMD_HOST`
- `CMD_SESSION_SECRET` (generated via `$(head -c 32 /dev/urandom | base64)`)
- `CMD_DOMAIN`, `CMD_URL_ADDPORT`, `CMD_PROTOCOL_USESSL`
- `CMD_ALLOW_ANONYMOUS`, `CMD_ALLOW_ANONYMOUS_EDITS`, `CMD_DEFAULT_PERMISSION`

Still crashes in < 1s after respawn.

## What the session surfaced (independent of HedgeDoc)

**Platform fix shipped 2026-04-21:** the uwsgi attach-daemon shell redirected only `2>>{log}`, losing stdout. HedgeDoc writes its `uncaughtException` to stdout, so the first investigation showed only uwsgi's respawn loop. Changed `packages/hop3-server/src/hop3/run/uwsgi/worker.py` to use `>>{log} 2>&1` on both `WebWorker` and `GenericWorker`. This is how we saw the real error above.

## Next steps (not attempted, pending session priority)

1. **Need a way to inspect the running daemon's actual transformed `index.js:153`.** Options: clone nixpkgs locally and build hedgedoc to see the transformed file; or add a one-shot debug hop3 command `hop3 app shell <name>` that opens a non-interactive exec into the vassal's cwd.
2. **Try the legacy `HMD_*` env-var prefix** (oldest HedgeDoc compat layer) in case `CMD_*` isn't being read in this particular build path.
3. **Try providing a minimal `config.json`** in the app's writable dir — HedgeDoc's config loader reads `CMD_CONFIG_FILE` or `./config.json` if present, and a file-based config merges last in `oldEnvironment` → `hackmdEnvironment` → `environment` → file chain.

## Platform-level pointer

- Related to DEFERRED-APPS.md **#4** (pnpm node_modules handling) — but *not* for the original symptom. The pnpm-symlink issue is sidestepped here by using `pkgs.hedgedoc` instead of the pre-built release. What's left is a HedgeDoc-internal config issue, arguably upstream, possibly nixpkgs-patch-specific.
- If we had a `hop3 app shell` command (or just a documented "ssh to hop3-dev and look at the running config file" procedure), this would be a 10-minute fix. The absence of that tool is the real lesson — log the gap in the meta-backlog.
