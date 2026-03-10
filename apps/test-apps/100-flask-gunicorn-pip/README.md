# 100-flask-gunicorn-pip

## Purpose

Tests Hop3's **Python deployment with Gunicorn** using pip/requirements.txt.

## What It Validates

- Python toolchain with requirements.txt
- Gunicorn WSGI server (alternative to uWSGI's built-in WSGI)
- `web:` Procfile directive (vs `wsgi:`)
- PORT environment variable injection for Gunicorn

## Structure

```
Procfile          # web: gunicorn -b 0.0.0.0:$PORT app:app
app.py            # Flask application
requirements.txt  # flask, gunicorn
```

## Technical Details

- **Toolchain**: Python (detected via requirements.txt)
- **Deployer**: uWSGI (generic process management)
- **Server**: Gunicorn (user-provided WSGI server)
- **Procfile syntax**: `web: gunicorn -b 0.0.0.0:$PORT app:app`

## Comparison with 010-flask-pip-wsgi

| Aspect | 010 (wsgi:) | 100 (web: gunicorn) |
|--------|-------------|---------------------|
| WSGI server | uWSGI built-in | Gunicorn |
| Procfile | `wsgi: app:app` | `web: gunicorn ...` |
| Config | Hop3 manages | User manages |

## Why This Test Matters

Many developers prefer Gunicorn over uWSGI's WSGI mode. This validates that Hop3 can manage user-provided WSGI servers correctly.
