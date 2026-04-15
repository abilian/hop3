# BookWyrm (native + docker) — deferred

**Reason:** BookWyrm's migration 0224 uses `django.contrib.postgres.operations.BloomExtension()`, which issues `CREATE EXTENSION bloom` as the connecting user. The Hop3 PostgreSQL addon creates per-app users *without* the privilege to install extensions, and the deploy fails with:

```
django.db.utils.ProgrammingError: permission denied to create extension "bloom"
```

This is not a BookWyrm-specific defect — it is a gap in the PostgreSQL addon. Several classes of self-hosted apps need PostgreSQL extensions (`bloom`, `pg_trgm`, `hstore`, `citext`, `vector`, `pg_partman`), and all of them will hit the same wall. Mastodon, already packaged, avoids this by telling the operator to pre-create extensions out-of-band; that workaround is fine for docker setups where the image runs initialisation as postgres superuser, but does not scale to the per-app model Hop3 uses.

On PostgreSQL 13+, `bloom` and most commonly-needed extensions are *trusted* — they can be installed by a non-superuser with the CREATE privilege on the database. The Hop3 addon currently does not grant CREATE on the database to the per-app user. A one-line change in the addon provisioning (`ALTER DATABASE <db> OWNER TO <user>` or `GRANT CREATE ON DATABASE <db> TO <user>`) would unlock trusted extensions for all apps.

**Working variants (kept):**

- None — both native and docker failed for the same reason. BookWyrm cannot complete migrations without the bloom extension.

**Unblockers (in priority order):**

1. **Teach the PostgreSQL addon to grant CREATE on the database to the per-app user**, or add ownership of the database to the per-app user. ~2 lines in the addon's `provision()`. Unlocks trusted extensions (bloom, pg_trgm, hstore, citext, and others).
2. **Alternative:** support a `[[addons]].pg-extensions = ["bloom", "pg_trgm", ...]` field in `hop3.toml` that has the addon pre-create extensions as postgres superuser during provisioning. More explicit but needs an addon API surface.
3. **Workaround for operators today:** ssh into the Hop3 server and manually run as postgres user:
   ```sql
   GRANT CREATE ON DATABASE bookwyrm_<timestamp>_postgres TO bookwyrm_<timestamp>_postgres_user;
   ```
   Then redeploy. This is a one-off incantation that the addon should be doing automatically.

**Scope of impact:** Funkwhale (pg_trgm), Pretalx (pg_trgm), any Mastodon variant beyond the current docker-only path, Lemmy (pg_trgm), Plausible (in Postgres-only mode), many Django-based apps. Fixing the addon is high-leverage.

**Related apps deferred for similar reasons:**
- Directus native — `[build].packages` not consumed (different gap, same family: server-side capability missing).
- Vaultwarden docker/native — Rust toolchain not provisioned on server.

When the addon grows `CREATE` grants, revive BookWyrm — the start.sh / migrate.sh and the Dockerfile in this deferred directory are ready to go; nothing else about the BookWyrm packaging is broken.
