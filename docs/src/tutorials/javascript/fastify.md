# Deploying Fastify on Hop3

This guide walks you through deploying a Fastify application on Hop3. Fastify is a high-performance Node.js web framework focused on developer experience and speed.

## Prerequisites

Before you begin, ensure you have:

1. **A Hop3 server** - Follow the [Installation Guide](../../get-started/installation.md)
2. **The Hop3 CLI** - Installed on your local machine
3. **Node.js 18+** - Install from [nodejs.org](https://nodejs.org/)
4. **Git** - For version control and deployment

Verify your local setup:

```bash
node -v
```

## Step 1: Create a New Fastify Application

```bash
mkdir hop3-tuto-fastify && cd hop3-tuto-fastify && npm init -y
```

```console
package.json
```

Install Fastify:

```bash
npm install fastify @fastify/cors @fastify/swagger @fastify/swagger-ui
```

```console
added
```

## Step 2: Create the Application

```javascript
const fastify = require('fastify')({ logger: true });

// SECURITY: Specify allowed origins explicitly - never use 'true' or '*' in production
const allowedOrigins = process.env.ALLOWED_ORIGINS;
if (!allowedOrigins && process.env.NODE_ENV === 'production') {
  throw new Error('ALLOWED_ORIGINS must be set in production');
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

```json
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

## Step 3: Test the Application

Test locally (skipped in automated tests - local server tests are flaky):

```bash
node app.js &
sleep 2
curl -s http://localhost:3000/health
```

## Step 4: Create Deployment Configuration

```procfile
prebuild: npm install --production
web: node app.js
```

```toml
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

```bash
hop3 init --ssh root@your-server.example.com
```

### Deploy

Deploy the application (first deployment creates the app):

```bash
hop3 deploy hop3-tuto-fastify
```

```console
deployed successfully
```

### Set Hostname

Configure the hostname for nginx proxy:

```bash
hop3 config set --app hop3-tuto-fastify HOST_NAME=hop3-tuto-fastify.$HOP3_TEST_DOMAIN
```

### Set Environment Variables

Configure additional environment variables:

```bash
hop3 config set --app hop3-tuto-fastify ALLOWED_ORIGINS=http://hop3-tuto-fastify.$HOP3_TEST_DOMAIN
```

### Apply Configuration

Redeploy to apply the hostname and environment configuration:

```bash
hop3 deploy hop3-tuto-fastify
```

```console
deployed successfully
```

### Verify Deployment

```bash
hop3 status --app hop3-tuto-fastify
```

```console
hop3-tuto-fastify
```

```bash
curl -s http://hop3-tuto-fastify.$HOP3_TEST_DOMAIN/up
```

```console
OK
```

### Managing Your Application

```bash
# Restart the application
hop3 restart --app hop3-tuto-fastify

# View logs
hop3 logs --app hop3-tuto-fastify

# View/set environment variables
hop3 config show --app hop3-tuto-fastify
hop3 config set --app hop3-tuto-fastify NEW_VAR=value

# Scale workers
hop3 ps scale --app hop3-tuto-fastify web=2
```

## Advanced Configuration

### TypeScript Support

```bash
npm install typescript @types/node tsx
```

### Database with Prisma

```bash
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
