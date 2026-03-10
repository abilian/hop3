# 110-flask-gunicorn-poetry

## Purpose

Tests Hop3's **Python deployment with Poetry** package manager.

## What It Validates

- Python toolchain detection via `pyproject.toml`
- Poetry/PEP 517 build system (`pip install .`)
- src-layout package structure (`src/app/`)
- PYTHONPATH configuration for src-layout
- Gunicorn with module path (`app.main:app`)

## Structure

```
Procfile         # web: gunicorn -b 0.0.0.0:$PORT app.main:app
pyproject.toml   # Poetry configuration
src/
  app/
    __init__.py
    main.py      # Flask application
```

## Technical Details

- **Toolchain**: Python (detected via pyproject.toml)
- **Package manager**: Poetry (PEP 517 build)
- **Layout**: src-layout (code in `src/` directory)
- **Procfile syntax**: `web: gunicorn ... app.main:app`

## Comparison with 100-flask-gunicorn-pip

| Aspect | 100 (pip) | 110 (Poetry) |
|--------|-----------|--------------|
| Config | requirements.txt | pyproject.toml |
| Install | `pip install -r` | `pip install .` |
| Layout | flat (app.py) | src-layout |
| Import | `app:app` | `app.main:app` |

## Why This Test Matters

Poetry is still a popular dependency management tool for Python projects. This validates that Hop3 correctly handles PEP 517 builds and src-layout projects, which require PYTHONPATH configuration.
