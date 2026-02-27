# Matrix Synapse Build Issues

Matrix Synapse requires PostgreSQL databases with `C` collation, but Hop3's PostgreSQL addon creates databases with `en_US.UTF-8`.

## Error

```
synapse.storage.engines._base.IncorrectDatabaseSetup:
"Database has incorrect collation of 'en_US.UTF-8'. Should be 'C'"
```

## Root Cause

Synapse performs binary-safe string comparisons and requires databases created with:
```sql
CREATE DATABASE synapse
  ENCODING 'UTF8'
  LC_COLLATE='C'
  LC_CTYPE='C'
  template=template0;
```

## Fix Required

The Hop3 PostgreSQL addon needs to support specifying collation when provisioning databases. Until then, Matrix Synapse cannot use the standard PostgreSQL addon.

## Workaround

The Synapse config supports `allow_unsafe_locale: true` in the database section, but this is not recommended for production.
