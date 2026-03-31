# 120-flask-pip-alt

## Purpose

Tests Hop3's **alternate configuration path** (`hop3/` subdirectory).

## What It Validates

- Configuration file discovery in `hop3/` subdirectory
- Procfile loading from alternate location
- WSGI deployment with non-standard config path

## Structure

```
app.py            # Flask application (in root)
requirements.txt  # Dependencies
hop3/
  Procfile        # wsgi: app:app (alternate location)
```

## Technical Details

- **Toolchain**: Python (detected via requirements.txt)
- **Deployer**: uWSGI (detected via `wsgi:` directive)
- **Config path**: `hop3/Procfile` instead of `Procfile`

## Why This Test Matters

Some projects prefer to keep deployment configuration in a subdirectory to avoid cluttering the project root. Hop3 supports looking for Procfile and hop3.toml in a `hop3/` subdirectory. This test validates that alternate path discovery works correctly.

## Related

See also the hop3.toml reference for other configuration options that can be placed in the `hop3/` subdirectory.
