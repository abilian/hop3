# 000-static

## Purpose

Tests Hop3's **static file deployment** capability.

## What It Validates

- Static deployer detection (no application server needed)
- Nginx configuration for serving static files directly
- The `static:` Procfile directive (non-standard, Hop3-specific)

## Structure

```
Procfile      # static: public
public/       # Static files served by nginx
```

## Technical Details

- **Deployer**: Static (nginx serves files directly)
- **No runtime**: No Python/Node/Go - just files
- **Procfile syntax**: `static: <directory>` tells Hop3 to serve that directory

## Why This Test Matters

Validates the simplest deployment path: no application server, no build process, just serving files. This is the baseline test that should always pass.
