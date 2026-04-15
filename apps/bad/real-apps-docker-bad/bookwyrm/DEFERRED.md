# BookWyrm docker — deferred

See `apps/bad/real-apps-native-bad/bookwyrm/DEFERRED.md` for the full explanation. Short version: BookWyrm's migrations run `CREATE EXTENSION bloom`, which the Hop3 PostgreSQL addon's per-app user lacks privilege to do. Addon gap, not an app-level fix.
