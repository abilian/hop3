# Mastodon Build Issues

Mastodon requires multiple encryption secrets that must be generated and persisted.

## Error

```
Mastodon now requires that these variables are set:
  - ACTIVE_RECORD_ENCRYPTION_DETERMINISTIC_KEY
  - ACTIVE_RECORD_ENCRYPTION_KEY_DERIVATION_SALT
  - ACTIVE_RECORD_ENCRYPTION_PRIMARY_KEY

Run `bin/rails db:encryption:init` to generate new secrets
```

## Root Cause

Mastodon 4.x requires Rails Active Record encryption keys. These must be:
1. Generated once using `bin/rails db:encryption:init`
2. Stored persistently (changing them causes data loss)
3. Passed as environment variables on every startup

## Fix Required

The Hop3 deployment needs to:
1. Generate these secrets on first deployment
2. Store them in the app's env vars (database)
3. Inject them on subsequent deployments

This requires Hop3 infrastructure support for "first-run secret generation" pattern.

## Additional Complexity

Mastodon also requires:
- Yarn 4.x via corepack (fixed in Dockerfile)
- Redis for caching and Sidekiq
- Background workers (Sidekiq) - not just web process
- Asset precompilation on first run
