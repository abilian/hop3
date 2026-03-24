# Deploying Express.js on Hop3

This guide walks you through deploying an Express.js application on Hop3. By the end, you'll have a production-ready Node.js application running on your own infrastructure.

## Prerequisites

Before you begin, ensure you have:

1. **A Hop3 server** - Follow the [Installation Guide](../../get-started/server-setup.md) if you haven't set one up yet
2. **The Hop3 CLI** - Installed on your local machine
3. **Node.js 18+** - Install from [nodejs.org](https://nodejs.org/) or via your package manager
4. **npm** - Comes with Node.js
5. **Git** - For version control and deployment

Verify your local setup:

```bash
node -v
```

```bash
npm -v
```

## Step 1: Create a New Express Application

Create the project directory and initialize it:

```bash
mkdir hop3-tuto-express && cd hop3-tuto-express && npm init -y
```

```console
package.json
```

Install Express and production dependencies:

```bash
npm install express
```

```console
added
```

## Step 2: Create the Application

Create the main application file:

```javascript
const express = require('express');
const app = express();

// Parse JSON bodies
app.use(express.json());

// Welcome route
app.get('/', (req, res) => {
  res.json({
    message: 'Hello from Hop3!',
    timestamp: new Date().toISOString()
  });
});

// Health check endpoint for Hop3
app.get('/up', (req, res) => {
  res.status(200).send('OK');
});

app.get('/health', (req, res) => {
  res.json({
    status: 'ok',
    uptime: process.uptime(),
    memory: process.memoryUsage()
  });
});

// Example API route
app.get('/api/info', (req, res) => {
  res.json({
    name: 'hop3-tuto-express',
    version: '1.0.0',
    node: process.version,
    env: process.env.NODE_ENV || 'development'
  });
});

// Error handling middleware
app.use((err, req, res, next) => {
  console.error(err.stack);
  res.status(500).json({ error: 'Something went wrong!' });
});

// Start server
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});

module.exports = app;
```

## Step 3: Add Development Scripts

Update `package.json` with useful scripts:

```json
{
  "name": "hop3-tuto-express",
  "version": "1.0.0",
  "description": "Express.js application for Hop3",
  "main": "app.js",
  "scripts": {
    "start": "node app.js",
    "dev": "node --watch app.js"
  },
  "keywords": [],
  "author": "",
  "license": "ISC",
  "dependencies": {
    "express": "^4.18.0"
  },
  "engines": {
    "node": ">=18.0.0"
  }
}
```

## Step 4: Verify the Application Works

Test locally (skipped in automated tests - local server tests are flaky):

```bash
node app.js &
sleep 2
curl -s http://localhost:3000/
```

Check the package structure:

```bash
ls -la
```

```console
app.js
```

```console
package.json
```

```console
node_modules
```

## Step 5: Create Deployment Configuration

### Create a Procfile

Create a `Procfile` in your project root:

```procfile
# Pre-build: Install dependencies
prebuild: npm install

# Main web process
web: node app.js
```

### Create hop3.toml

Create a `hop3.toml` for advanced configuration:

```toml
[metadata]
id = "hop3-tuto-express"
version = "1.0.0"
title = "My Express Application"

[build]
before-build = ["npm install"]
packages = ["nodejs", "npm"]

[run]
start = "node app.js"

[env]
NODE_ENV = "production"

[port]
web = 3000

[healthcheck]
path = "/up"
timeout = 30
interval = 60
```

Verify the deployment files exist:

```bash
ls -la
```

```console
Procfile
```

```console
hop3.toml
```

## Step 6: Initialize Git Repository

Create a `.gitignore` file:

```text
# Dependencies
node_modules/

# Logs
logs/
*.log
npm-debug.log*

# Environment
.env
.env.local
.env.*.local

# OS files
.DS_Store
Thumbs.db

# IDE
.idea/
.vscode/
*.swp
*.swo

# Build output
dist/
build/
```

Initialize the repository:

```bash
git init
```

```console
Initialized empty Git repository
```

```bash
git add .
```

```bash
git commit -m "Initial Express.js application"
```

```console
Initial Express.js application
```

## Step 7: Deploy to Hop3

The following steps require a Hop3 server. Set the `HOP3_SERVER` environment variable to your server address before running these commands.

### Configure the CLI

If this is your first deployment, initialize Hop3:

```bash
hop3 init --ssh root@your-server.example.com
```

### Deploy

Deploy the application (first deployment creates the app):

```bash
hop3 deploy hop3-tuto-express
```

### Set Hostname

Configure the hostname for nginx proxy:

```bash
hop3 config:set hop3-tuto-express HOST_NAME=hop3-tuto-express.$HOP3_TEST_DOMAIN
```

### Wait for Process Stop

Wait for the previous deployment to fully stop:

```bash
sleep 5
```

### Apply Configuration

Redeploy to apply the hostname configuration:

```bash
hop3 deploy hop3-tuto-express
```

```console
deployed successfully
```

## Step 8: Verify Deployment

Check your application status:

```bash
hop3 app:status hop3-tuto-express
```

```console
hop3-tuto-express
```

```bash
curl -s http://hop3-tuto-express.$HOP3_TEST_DOMAIN/up
```

```console
OK
```

## Managing Your Application

### Restart the Application

```bash
hop3 app:restart hop3-tuto-express
```

### Run Commands in the Application Context

```bash
hop3 run hop3-tuto-express node -e "console.log('Hello from server!')"
```

### View and Manage Environment Variables

```bash
# List all variables
hop3 config:show hop3-tuto-express

# Set a variable
hop3 config:set hop3-tuto-express NEW_VARIABLE=value

# Remove a variable
hop3 config:unset hop3-tuto-express OLD_VARIABLE
```

### Scaling

```bash
# Check current processes
hop3 ps hop3-tuto-express

# Scale web workers
hop3 ps:scale hop3-tuto-express web=2
```

## Advanced Configuration

### Adding a Database (PostgreSQL)

Install the PostgreSQL client:

```bash
cd hop3-tuto-express
npm install pg
```

Create a database configuration file:

```javascript
// db.js
const { Pool } = require('pg');

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: process.env.NODE_ENV === 'production' ? { rejectUnauthorized: false } : false
});

module.exports = {
  query: (text, params) => pool.query(text, params),
  pool
};
```

Attach a database addon:

```bash
hop3 addons:create postgres hop3-tuto-express-db
hop3 addons:attach hop3-tuto-express hop3-tuto-express-db
```

### Adding Redis for Sessions/Caching

Install Redis client:

```bash
npm install redis connect-redis express-session
```

Configure session middleware:

```javascript
const session = require('express-session');
const RedisStore = require('connect-redis').default;
const { createClient } = require('redis');

const redisClient = createClient({ url: process.env.REDIS_URL });
redisClient.connect();

app.use(session({
  store: new RedisStore({ client: redisClient }),
  secret: process.env.SESSION_SECRET,
  resave: false,
  saveUninitialized: false
}));
```

Attach a Redis addon:

```bash
hop3 addons:create redis hop3-tuto-express-redis
hop3 addons:attach hop3-tuto-express hop3-tuto-express-redis
hop3 config:set hop3-tuto-express SESSION_SECRET=$(openssl rand -hex 32)
```

### Using PM2 for Process Management

For more robust process management, use PM2:

```bash
npm install pm2
```

Create `ecosystem.config.js`:

```javascript
module.exports = {
  apps: [{
    name: 'hop3-tuto-express',
    script: 'app.js',
    instances: 'max',
    exec_mode: 'cluster',
    env_production: {
      NODE_ENV: 'production'
    }
  }]
};
```

Update `Procfile`:

```procfile
web: npx pm2-runtime ecosystem.config.js --env production
```

### TypeScript Support

For TypeScript projects, add build configuration:

```bash
npm install typescript @types/node @types/express ts-node
npx tsc --init
```

Update `package.json`:

```json
{
  "scripts": {
    "build": "tsc",
    "start": "node dist/app.js",
    "dev": "ts-node src/app.ts"
  }
}
```

Update `hop3.toml`:

```toml
[build]
before-build = ["npm install", "npm run build"]
```

### CORS Configuration

For API servers accessed from different domains:

```javascript
const cors = require('cors');

app.use(cors({
  origin: process.env.ALLOWED_ORIGINS?.split(',') || '*',
  methods: ['GET', 'POST', 'PUT', 'DELETE'],
  allowedHeaders: ['Content-Type', 'Authorization']
}));
```

### Request Logging with Morgan

```bash
npm install morgan
```

```javascript
const morgan = require('morgan');

// Use 'combined' format in production for detailed logs
app.use(morgan(process.env.NODE_ENV === 'production' ? 'combined' : 'dev'));
```

## Troubleshooting

### Application Won't Start

Check the logs for errors:

```bash
hop3 app:logs hop3-tuto-express --tail
```

Common issues:
- **Missing dependencies**: Ensure `npm install` runs during build
- **Wrong Node.js version**: Check `engines` field in `package.json`
- **Port binding**: Ensure you use `process.env.PORT`

### Memory Issues

Node.js can consume significant memory. Set limits:

```bash
hop3 config:set hop3-tuto-express NODE_OPTIONS="--max-old-space-size=512"
```

### Module Not Found Errors

Ensure all dependencies are in `dependencies` (not `devDependencies`) if needed in production:

```json
{
  "dependencies": {
    "express": "^4.18.0"
  },
  "devDependencies": {
    "nodemon": "^3.0.0"
  }
}
```

### Slow Startup

For faster cold starts:
- Minimize dependencies
- Use lazy loading for heavy modules
- Consider using `esbuild` or `webpack` to bundle your app

## Next Steps

- **[CLI Reference](../../reference/cli.md)** - Complete command reference
- **[hop3.toml Reference](../../reference/config.md)** - Full configuration options
- **[Backup and Restore Guide](../../guides/backup-restore.md)** - Protect your data

## Example Files

### Complete hop3.toml for Express

```toml
# hop3.toml - Express.js Application

[metadata]
id = "hop3-tuto-express"
version = "1.0.0"
title = "My Express Application"
author = "Your Name <you@example.com>"

[build]
before-build = ["npm install --production"]
packages = ["nodejs"]

[run]
start = "node app.js"

[env]
NODE_ENV = "production"

[port]
web = 3000

[healthcheck]
path = "/up"
timeout = 30
interval = 60

[[provider]]
name = "postgres"
plan = "standard"
```

### Complete Procfile for Express

```procfile
# Procfile - Express.js Application

# Build phase
prebuild: npm install --production

# Web server
web: node app.js

# Background worker (optional)
worker: node worker.js
```
