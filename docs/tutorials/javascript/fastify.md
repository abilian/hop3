---
tutorial:
  name: fastify-hop3-tutorial
  env:
    NODE_ENV: development
  teardown:
    - rm -rf hop3-tuto-fastify 2>/dev/null || true
    - hop3 app destroy --app hop3-tuto-fastify -y 2>/dev/null || true
---

# Deploying Fastify on Hop3

This guide walks you through deploying a Fastify application on Hop3. Fastify is a high-performance Node.js web framework focused on developer experience and speed.

## Prerequisites

Before you begin, ensure you have:

1. **A Hop3 server** - Follow the [Installation Guide](../../get-started/server-setup.md)
2. **The Hop3 CLI** - Installed on your local machine
3. **Node.js 18+** - Install from [nodejs.org](https://nodejs.org/)
4. **Git** - For version control and deployment

Verify your local setup:

```bash exec id=check-node
node -v
```

```output regex
v[0-9]+\.
```

## Step 1: Create a New Fastify Application

```bash exec id=create-project
mkdir hop3-tuto-fastify && cd hop3-tuto-fastify && npm init -y
```

```output contains
package.json
```

Install Fastify:

```bash exec id=install-fastify dir=hop3-tuto-fastify timeout=60
npm install fastify @fastify/cors @fastify/swagger @fastify/swagger-ui
```

```output contains
added
```

## Step 2: Create the Application

```file path=hop3-tuto-fastify/app.js
const fastify = require('fastify')({ logger: true });

// SECURITY: specify allowed CORS origins explicitly in production. The very
// first deploy boots before you've set ALLOWED_ORIGINS (you set it with
// `hop3 env set` below, then redeploy), so default to "no cross-origin
// access" with a warning rather than crashing the app on startup.
const allowedOrigins = process.env.ALLOWED_ORIGINS;
if (!allowedOrigins && process.env.NODE_ENV === 'production') {
  console.warn('ALLOWED_ORIGINS is not set; CORS is disabled. Set it for production.');
}

// Register plugins
fastify.register(require('@fastify/cors'), {
  origin: allowedOrigins ? allowedOrigins.split(',') : false
});
fastify.register(require('@fastify/swagger'), {
  openapi: {
    info: { title: 'My API', version: '1.0.0' }
  }
});
fastify.register(require('@fastify/swagger-ui'), { routePrefix: '/docs' });

// Welcome page
fastify.get('/', async (request, reply) => {
  reply.type('text/html').send(`
    <!DOCTYPE html>
    <html>
    <head>
      <title>Welcome to Hop3</title>
      <style>
        body {
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
          display: flex;
          justify-content: center;
          align-items: center;
          min-height: 100vh;
          margin: 0;
          background: linear-gradient(135deg, #000000 0%, #333333 100%);
          color: white;
        }
        .container { text-align: center; padding: 2rem; }
        h1 { font-size: 3rem; margin-bottom: 1rem; }
        p { font-size: 1.25rem; opacity: 0.9; }
        a { color: #00d8ff; margin-top: 1rem; display: inline-block; }
      </style>
    </head>
    <body>
      <div class="container">
        <h1>Hello from Hop3!</h1>
        <p>Your Fastify application is running.</p>
        <p>Current time: ${new Date().toISOString()}</p>
        <a href="/docs">API Documentation</a>
      </div>
    </body>
    </html>
  `);
});

// Health endpoints
fastify.get('/up', async () => 'OK');

fastify.get('/health', async () => ({
  status: 'ok',
  timestamp: new Date().toISOString(),
  uptime: process.uptime()
}));

fastify.get('/api/info', async () => ({
  name: 'hop3-tuto-fastify',
  version: '1.0.0',
  node: process.version,
  fastify: require('fastify/package.json').version
}));

// Example CRUD API
const items = new Map([
  [1, { id: 1, name: 'Item 1', price: 9.99 }],
  [2, { id: 2, name: 'Item 2', price: 19.99 }]
]);
let nextId = 3;

fastify.get('/api/items', async () => Array.from(items.values()));

fastify.get('/api/items/:id', async (request, reply) => {
  const item = items.get(parseInt(request.params.id));
  if (!item) return reply.code(404).send({ error: 'Not found' });
  return item;
});

fastify.post('/api/items', async (request, reply) => {
  const item = { id: nextId++, ...request.body };
  items.set(item.id, item);
  return reply.code(201).send(item);
});

// Start server
const start = async () => {
  try {
    const port = process.env.PORT || 3000;
    await fastify.listen({ port, host: '0.0.0.0' });
  } catch (err) {
    fastify.log.error(err);
    process.exit(1);
  }
};

start();
```

Update package.json:

```file path=hop3-tuto-fastify/package.json
{
  "name": "hop3-tuto-fastify",
  "version": "1.0.0",
  "main": "app.js",
  "scripts": {
    "start": "node app.js",
    "dev": "node --watch app.js"
  },
  "dependencies": {
    "fastify": "^5.0.0",
    "@fastify/cors": "^11.0.0",
    "@fastify/swagger": "^9.0.0",
    "@fastify/swagger-ui": "^5.0.0"
  },
  "engines": {
    "node": ">=18.0.0"
  }
}
```

```assert file-exists path=hop3-tuto-fastify/app.js
```

## Step 3: Test the Application

Test locally (skipped in automated tests - local server tests are flaky):

```bash skip
node app.js &
sleep 2
curl -s http://localhost:3000/health
```

## Step 4: Create Deployment Configuration

```file path=hop3-tuto-fastify/Procfile
prebuild: npm install --production
web: node app.js
```

```file path=hop3-tuto-fastify/hop3.toml
[metadata]
id = "hop3-tuto-fastify"
version = "1.0.0"
title = "My Fastify Application"

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
```

## Deploy to Hop3

The following steps require a Hop3 server.

### Initialize (First Time Only)

```bash skip
hop3 init --ssh root@your-server.example.com
```

### Initialize the Git Repository

Hop3 deploys the committed contents of a Git repository. Ignore `node_modules` (it's rebuilt on the server, and its symlinks can't be archived) and commit:

```bash exec id=git-init dir=hop3-tuto-fastify
printf 'node_modules/\n.env\n' > .gitignore
git init && git add -A && git commit -m "Initial Fastify application"
```

### Deploy

Deploy the application (first deployment creates the app):

```bash exec id=deploy dir=hop3-tuto-fastify timeout=120
hop3 deploy --app hop3-tuto-fastify
```

```output contains
deployed successfully
```

### Set Hostname

Configure the hostname for nginx proxy:

```bash exec id=set-hostname timeout=30
hop3 env set --app hop3-tuto-fastify HOST_NAME=hop3-tuto-fastify.$HOP3_TEST_DOMAIN
```

### Set Environment Variables

Configure additional environment variables:

```bash exec id=set-env timeout=30
hop3 env set --app hop3-tuto-fastify ALLOWED_ORIGINS=http://hop3-tuto-fastify.$HOP3_TEST_DOMAIN
```

### Apply Configuration

Redeploy to apply the hostname and environment configuration:

```bash exec id=redeploy dir=hop3-tuto-fastify timeout=120
hop3 deploy --app hop3-tuto-fastify
```

```output contains
deployed successfully
```

### Verify Deployment

```bash exec id=check-status timeout=30
hop3 app status --app hop3-tuto-fastify
```

```output contains
hop3-tuto-fastify
```

```bash exec id=check-health timeout=30
curl -s http://hop3-tuto-fastify.$HOP3_TEST_DOMAIN/up
```

```output contains
OK
```

### Managing Your Application

```bash skip
# Restart the application
hop3 app restart --app hop3-tuto-fastify

# View logs
hop3 app logs --app hop3-tuto-fastify

# View/set environment variables
hop3 env show --app hop3-tuto-fastify
hop3 env set --app hop3-tuto-fastify NEW_VAR=value

# Scale workers
hop3 ps scale --app hop3-tuto-fastify web=2
```

## Advanced Configuration

### TypeScript Support

```bash skip
npm install typescript @types/node tsx
```

### Database with Prisma

```bash skip
npm install @prisma/client prisma
npx prisma init
```

### Validation with Zod

```javascript
const { z } = require('zod');

const itemSchema = z.object({
  name: z.string().min(1),
  price: z.number().positive()
});

fastify.post('/api/items', {
  schema: { body: itemSchema }
}, async (request, reply) => {
  // Validated request.body
});
```

## Example hop3.toml

```toml
[metadata]
id = "hop3-tuto-fastify"
version = "1.0.0"

[build]
before-build = ["npm install --production"]

[run]
start = "node app.js"

[env]
NODE_ENV = "production"

[port]
web = 3000

[healthcheck]
path = "/up"

[[provider]]
name = "postgres"
plan = "standard"
```
