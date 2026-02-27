# Wekan - Build Issues

Wekan is currently unsupported due to fundamental compatibility issues.

## Issues

### 1. Requires Node.js 14 (EOL)

Wekan is built on Meteor, which depends on the `fibers` package. The `fibers` package:
- Is deprecated and unmaintained
- Only works with Node.js 14 (ABI compatibility)
- Node.js 14 reached End-of-Life in April 2023

Using Node 14 in production is a security risk.

### 2. Requires MongoDB

Wekan requires MongoDB as its database backend. Hop3 currently does not have a MongoDB addon, so the Dockerfile bundles MongoDB directly - which is not ideal for:
- Resource usage (running MongoDB inside the app container)
- Data persistence and backup
- Scaling and maintenance

## Path Forward

Wekan could be supported once:
1. **Wekan migrates to Meteor 3.0** - which removes the `fibers` dependency and supports modern Node.js
2. **Hop3 adds a MongoDB addon** - for proper database management

## Alternatives

Consider these Kanban alternatives that work with PostgreSQL:
- **Focalboard** (supported)
- **Vikunja** (supported)
- **Kanboard** (supported)
