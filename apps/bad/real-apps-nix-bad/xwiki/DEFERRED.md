# XWiki (nix) — deferred

**Last investigated:** 2026-04-24.

## Current state

Packaging is a hand-crafted `hop3.nix` that extracts the XWiki 16.1.0 WAR + Jetty standalone distribution into a writable `$PWD/.xwiki-home` on first boot (lazy-copy, `.hop3-ready` sentinel), then execs `$HOME_DIR/start_xwiki.sh`. Builds cleanly; uwsgi emperor spawns the attach-daemon; Jetty binds the assigned port.

Manual deployment from the devel branch works end-to-end:

```
hop3 deploy -v xwiki
...
-> Waiting for app 'xwiki' to start (timeout: 180.0s)...
-> App 'xwiki' is now running.
✓ Deployment completed successfully in 30.2s
```

Over HTTP on `127.0.0.1:<port>`:
- `/` → 302 (Jetty redirects to `/xwiki/`)
- `/xwiki/bin/view/Main/` → **202 Accepted** (install wizard is running)

## What's blocking

**XWiki's install wizard returns 202 indefinitely until the wizard is completed.** On a fresh deploy the sequence is:

1. Jetty binds the port (fast — seconds).
2. Solr initializes its embedded index (seconds).
3. `FilesystemStoreTools` creates the data store (seconds).
4. XWiki's DistributionManager waits for a human to drive the install wizard in a browser — schema migrations, bundled-extension imports, admin user creation. Until step 4 completes, every URL returns 202.

No amount of `status_in = [200, 202]` in the validation config turns this into a "working" deployment — the app is literally waiting for human input.

## What changed in this session (2026-04-24)

**Platform-level fixes shipped today unblocked two layers:**

1. **Server-side `TestValidation` schema** rejected the new `status_in` field (added to hop3-testing in W17 but not mirrored in `packages/hop3-server/src/hop3/project/schema.py`). `extra = "forbid"` failed `hop3.toml` validation at deploy time with:
   `Unknown field 'test -> validations -> 0 -> status_in'`
   Fixed: added `status_in` to `TestValidation` and `expects_failure` to `TestSection`, both with kebab aliases. `hop3.toml` now validates.

2. **`node-pnpm-install` nix-gen template** produced a wrapper whose `NODEBIN` sed was a no-op (nothing in the body referenced it → host's Node 18 ran instead of the pinned Node 22 → `@sinclair/typebox` ESM/CJS mismatch), and whose pre-exec expected `$out/app/...` to resolve at runtime (`$out` is only defined inside the Nix build sandbox — at wrapper runtime it was empty, making `$out/app/node_modules/.bin/directus` expand to `/app/...`). Template now injects a `PATH="${nodejs}/bin:${PATH}"` export and an `APPDIR="<store-path>/app"` export after the shebang; user pre-exec switched to `$APPDIR/...`.

XWiki benefits from the first fix (validation passes), is unaffected by the second.

## Why it's still in `bad/`

Neither of the two platform fixes addresses the install-wizard requirement. That's a per-app step. Two paths forward, both out of 0.5 scope:

1. **Automated first-boot**: bundle an `xwiki.cfg` that pre-answers the wizard + seeds the admin user, and a `[run].before-run` step that POSTs to `/xwiki/bin/installstep/...` to drive the wizard. Probably 2-4 hours of XWiki-specific work.
2. **Per-app post-deploy hook**: a generic `[run].post-deploy` (not yet in the schema) that runs after the healthcheck passes. Would also unblock similar apps (Gitea's wizard, Keycloak's first-admin, Grafana's initial-user).

Option 2 is a platform improvement worth logging in `local-notes/stacks-and-apps/DEFERRED-APPS.md` rather than fixing in xwiki's hop3.toml — multiple apps share this shape.

## Bonus: a separate test-harness bug surfaced alongside

The 2026-04-23 system-test run showed xwiki's `hop3-test` session fail with "Deploy timed out after 30 minutes" — yet `hop3 deploy -v xwiki` from a developer shell returns in 30s. Same RPC call, different transport wrapper. Likely pipe-buffer deadlock on `hop3 deploy` stdout inside `hop3-test`, or the timestamped-addon-creation path (`xwiki-<timestamp>-postgres`) stalling. Not an xwiki problem; track it separately once P0 0.5 items close.

## Platform-level pointer

- Cluster E in `local-notes/stacks-and-apps/FAILURE-PATTERNS-2026-04-22.md` (first-boot async initialization). XWiki is the canonical example; keycloak and grafana share the shape.
- Post-deploy-hook design is the right generic answer; see `DEFERRED-APPS.md` blocker backlog.
