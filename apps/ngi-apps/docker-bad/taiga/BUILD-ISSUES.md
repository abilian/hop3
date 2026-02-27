# Taiga Build Issues

Taiga build exceeds the 600-second timeout due to its complex multi-component architecture.

## Issue

The Docker build times out because Taiga requires building:
1. Python backend (Django)
2. Node.js frontend (Angular)
3. Multiple Python dependencies with native extensions
4. Frontend asset compilation

## Root Cause

Taiga is a large, complex project with:
- Backend: Django + Celery + many Python packages
- Frontend: Angular app requiring full npm build
- Total build time: 10-20 minutes on typical hardware

## Recommendation

Use official Taiga Docker images instead of building from source:
- https://github.com/taigaio/taiga-docker

The official images are pre-built and optimized for deployment.

## Alternative

If building from source is required:
1. Increase Hop3's Docker build timeout
2. Use multi-stage builds with better caching
3. Consider pre-building frontend assets
