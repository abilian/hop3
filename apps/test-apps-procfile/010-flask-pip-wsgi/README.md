# 010-flask-pip-wsgi

## Purpose

Tests Hop3's **Python WSGI deployment** with pip and uWSGI.

## What It Validates

- Python toolchain detection via `requirements.txt`
- Virtual environment creation
- pip dependency installation
- uWSGI integration with `wsgi:` Procfile directive
- WSGI application loading (`app:app` syntax)

## Structure

```
Procfile          # wsgi: app:app
app.py            # Flask application
requirements.txt  # flask
```

## Technical Details

- **Toolchain**: Python (detected via requirements.txt)
- **Deployer**: uWSGI (detected via `wsgi:` directive)
- **Procfile syntax**: `wsgi: module:callable`

## Why This Test Matters

This is the canonical Python deployment path. Most Python web apps use WSGI, and this tests the integration between Hop3's Python toolchain and uWSGI deployer.
