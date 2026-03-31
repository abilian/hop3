# 020-nodejs-express

## Purpose

Tests Hop3's **Node.js deployment** with npm and Express.

## What It Validates

- Node.js toolchain detection via `package.json`
- npm dependency installation (`npm install`)
- Process management for Node applications
- PORT environment variable injection

## Structure

```
Procfile      # web: node app.js
app.js        # Express application
package.json  # express dependency
```

## Technical Details

- **Toolchain**: Node.js (detected via package.json)
- **Deployer**: uWSGI (generic process management)
- **Procfile syntax**: `web: node app.js`

## Local Testing

```bash
npm install
PORT=3000 node app.js
# Visit http://localhost:3000
```

## Why This Test Matters

Node.js is one of the most common deployment targets. This validates that Hop3 can correctly install npm dependencies and manage Node processes with proper PORT injection.
