---
tutorial:
  name: nuxtjs-hop3-tutorial
  env:
    NODE_ENV: development
  teardown:
    - rm -rf hop3-tuto-nuxtjs 2>/dev/null || true
    - hop3 app destroy --app hop3-tuto-nuxtjs -y 2>/dev/null || true
---

# Deploying Nuxt.js on Hop3

This guide walks you through deploying a Nuxt.js application on Hop3. By the end, you'll have a production-ready Vue.js application with server-side rendering running on your own infrastructure.

## Prerequisites

Before you begin, ensure you have:

1. **A Hop3 server** - Follow the [Installation Guide](../../get-started/server-setup.md) if you haven't set one up yet
2. **The Hop3 CLI** - Installed on your local machine
3. **Node.js 18+** - Install from [nodejs.org](https://nodejs.org/)
4. **npm** - Comes with Node.js
5. **Git** - For version control and deployment

Verify your local setup:

```bash exec id=check-node
node -v
```

```output regex
v[0-9]+\.
```

```bash exec id=check-npm
npm -v
```

```output regex
[0-9]+\.
```

## Step 1: Create a New Nuxt Application

Create the project directory and initialize:

```bash exec id=create-project
mkdir -p hop3-tuto-nuxtjs && cd hop3-tuto-nuxtjs && npm init -y
```

```output contains
package.json
```

```assert file-exists path=hop3-tuto-nuxtjs/package.json
```

Install Nuxt:

```bash exec id=install-nuxt dir=hop3-tuto-nuxtjs timeout=120
npm install nuxt@latest
```

```output contains
added
```

Create the Nuxt config:

```file path=hop3-tuto-nuxtjs/nuxt.config.ts
export default defineNuxtConfig({
  devtools: { enabled: false },
  compatibilityDate: "2024-11-01",
  nitro: {
    preset: "node-server",
  },
});
```

Update package.json with Nuxt scripts:

```bash exec id=add-scripts dir=hop3-tuto-nuxtjs
npm pkg set scripts.build="nuxt build" scripts.start="node .output/server/index.mjs" scripts.dev="nuxt dev"
```

Verify the project structure:

```bash exec id=verify-structure dir=hop3-tuto-nuxtjs
ls -la
```

```output contains
nuxt.config.ts
```

```output contains
package.json
```

## Step 2: Create Application Pages

Create the welcome page:

```file path=hop3-tuto-nuxtjs/app.vue
<template>
  <div>
    <NuxtPage />
  </div>
</template>
```

```bash exec id=create-pages-dir dir=hop3-tuto-nuxtjs
mkdir -p pages
```

```file path=hop3-tuto-nuxtjs/pages/index.vue
<template>
  <div class="container">
    <h1>Hello from Hop3!</h1>
    <p>Your Nuxt.js application is running.</p>
    <p>Current time: {{ currentTime }}</p>
    <div class="links">
      <NuxtLink to="/about">About</NuxtLink>
      <a href="/api/health">Health Check</a>
    </div>
  </div>
</template>

<script setup lang="ts">
const currentTime = ref(new Date().toISOString())

onMounted(() => {
  setInterval(() => {
    currentTime.value = new Date().toISOString()
  }, 1000)
})
</script>

<style scoped>
.container {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  margin: 0;
  background: linear-gradient(135deg, #00DC82 0%, #36E4DA 100%);
  color: white;
  text-align: center;
}
h1 {
  font-size: 3rem;
  margin-bottom: 1rem;
}
p {
  font-size: 1.25rem;
  opacity: 0.9;
}
.links {
  margin-top: 2rem;
  display: flex;
  gap: 1rem;
}
.links a {
  padding: 0.75rem 1.5rem;
  background: rgba(255,255,255,0.2);
  border-radius: 8px;
  color: white;
  text-decoration: none;
}
.links a:hover {
  background: rgba(255,255,255,0.3);
}
</style>
```

Create an about page:

```file path=hop3-tuto-nuxtjs/pages/about.vue
<template>
  <div class="container">
    <h1>About</h1>
    <p>This is a Nuxt.js application deployed on Hop3.</p>
    <NuxtLink to="/">Back to Home</NuxtLink>
  </div>
</template>

<style scoped>
.container {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  background: #1a1a2e;
  color: white;
  text-align: center;
}
a {
  margin-top: 2rem;
  color: #00DC82;
}
</style>
```

## Step 3: Create API Routes

Create API routes for health checks:

```bash exec id=create-server-dir dir=hop3-tuto-nuxtjs
mkdir -p server/api
```

```file path=hop3-tuto-nuxtjs/server/api/health.ts
export default defineEventHandler((event) => {
  return {
    status: 'ok',
    timestamp: new Date().toISOString(),
    uptime: process.uptime(),
  }
})
```

```file path=hop3-tuto-nuxtjs/server/api/up.ts
export default defineEventHandler((event) => {
  return 'OK'
})
```

```file path=hop3-tuto-nuxtjs/server/api/info.ts
export default defineEventHandler((event) => {
  return {
    name: 'hop3-tuto-nuxtjs',
    version: '1.0.0',
    node: process.version,
    nuxt: '3.x',
  }
})
```

```assert file-exists path=hop3-tuto-nuxtjs/server/api/health.ts
```

## Step 4: Configure for Production

Update `nuxt.config.ts` for production:

```file path=hop3-tuto-nuxtjs/nuxt.config.ts
// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: '2024-11-01',
  devtools: { enabled: false },

  // Nitro server configuration
  nitro: {
    preset: 'node-server',
  },

  // Runtime config
  runtimeConfig: {
    // Private keys (server-side only)
    secretKey: process.env.SECRET_KEY || 'dev-secret',

    // Public keys (exposed to client)
    public: {
      apiBase: process.env.API_BASE || '/api',
    },
  },

  // App configuration
  app: {
    head: {
      title: 'My Nuxt App',
      meta: [
        { charset: 'utf-8' },
        { name: 'viewport', content: 'width=device-width, initial-scale=1' },
      ],
    },
  },
})
```

## Step 5: Build and Verify

Build the application:

```bash exec id=build-app dir=hop3-tuto-nuxtjs timeout=180
npm run build && echo "Build completed successfully"
```

```output contains
Build completed successfully
```

Verify the build output:

```bash exec id=verify-build dir=hop3-tuto-nuxtjs
ls -la .output/
```

```output contains
server
```

## Step 6: Create Deployment Configuration

### Create a Procfile

```file path=hop3-tuto-nuxtjs/Procfile
# Pre-build: Install dependencies and build
prebuild: npm install && npm run build

# Main web process
web: node .output/server/index.mjs
```

### Create hop3.toml

```file path=hop3-tuto-nuxtjs/hop3.toml
[metadata]
id = "hop3-tuto-nuxtjs"
version = "1.0.0"
title = "My Nuxt.js Application"

[build]
before-build = ["npm install", "npm run build"]
packages = ["nodejs", "npm"]

[run]
start = "node .output/server/index.mjs"

[env]
NODE_ENV = "production"
NITRO_PORT = "$PORT"

[port]
web = 3000

[healthcheck]
path = "/api/up"
timeout = 30
interval = 60
```

Verify the deployment files:

```bash exec id=verify-deploy-files dir=hop3-tuto-nuxtjs
ls -la Procfile hop3.toml
```

```output contains
Procfile
```

```output contains
hop3.toml
```

## Step 7: Initialize Git Repository

```file path=hop3-tuto-nuxtjs/.gitignore
# Dependencies
node_modules/

# Build output
.output/
.nuxt/
dist/

# Environment
.env
.env.*
!.env.example

# IDE
.idea/
.vscode/
*.swp

# OS
.DS_Store

# Logs
*.log
```

```bash exec id=git-init dir=hop3-tuto-nuxtjs
git init
```

```output contains
Initialized empty Git repository
```

```bash exec id=git-add dir=hop3-tuto-nuxtjs
git add .
```

```bash exec id=git-commit dir=hop3-tuto-nuxtjs
git commit -m "Initial Nuxt.js application"
```

```output contains
Initial Nuxt.js application
```

## Step 8: Deploy to Hop3

The following steps require a Hop3 server.

### Initialize (First Time Only)

```bash skip
hop3 init --ssh root@your-server.example.com
```

### Deploy

Deploy the application (first deployment creates the app):

```bash exec id=deploy dir=hop3-tuto-nuxtjs timeout=120
hop3 deploy hop3-tuto-nuxtjs
```

### Set Hostname

Configure the hostname for nginx proxy:

```bash exec id=set-hostname timeout=30
hop3 config set --app hop3-tuto-nuxtjs HOST_NAME=hop3-tuto-nuxtjs.$HOP3_TEST_DOMAIN
```

### Wait for Process Stop

Wait for the previous deployment to fully stop:

```bash exec id=wait-before-redeploy timeout=10
sleep 5
```

### Apply Configuration

Redeploy to apply the hostname configuration:

```bash exec id=redeploy dir=hop3-tuto-nuxtjs timeout=120
hop3 deploy hop3-tuto-nuxtjs
```

```output contains
deployed successfully
```

### Verify Deployment

```bash exec id=check-status timeout=30
hop3 app status --app hop3-tuto-nuxtjs
```

```output contains
hop3-tuto-nuxtjs
```

```bash exec id=check-health timeout=30
curl -s http://hop3-tuto-nuxtjs.$HOP3_TEST_DOMAIN/api/up
```

```output contains
OK
```

## Managing Your Application

### Environment Variables

```bash skip
hop3 config set --app hop3-tuto-nuxtjs NUXT_PUBLIC_API_BASE=https://api.example.com
hop3 config set --app hop3-tuto-nuxtjs NUXT_SECRET_KEY=$(openssl rand -hex 32)
```

### View Logs

```bash skip
hop3 app logs --app hop3-tuto-nuxtjs --tail
```

## Advanced Configuration

### Adding a Database (PostgreSQL with Prisma)

```bash skip
npm install prisma @prisma/client
npx prisma init
```

### Server Middleware

```typescript
// server/middleware/auth.ts
export default defineEventHandler((event) => {
  const authHeader = getHeader(event, 'authorization')
  if (event.path.startsWith('/api/protected') && !authHeader) {
    throw createError({ statusCode: 401, message: 'Unauthorized' })
  }
})
```

### Static Site Generation

For fully static sites:

```typescript
// nuxt.config.ts
export default defineNuxtConfig({
  ssr: false,
  nitro: {
    preset: 'static',
  },
})
```

## Troubleshooting

### Build Failures
- Check Node.js version matches locally and on server
- Ensure all dependencies are in `dependencies` (not `devDependencies`)

### Runtime Errors
- Check `NITRO_PORT` is set correctly
- Verify `.output` directory exists after build

## Example Files

### Complete hop3.toml

```toml
[metadata]
id = "hop3-tuto-nuxtjs"
version = "1.0.0"
title = "My Nuxt.js Application"

[build]
before-build = ["npm install", "npm run build"]
packages = ["nodejs"]

[run]
start = "node .output/server/index.mjs"

[env]
NODE_ENV = "production"
NITRO_PORT = "$PORT"

[port]
web = 3000

[healthcheck]
path = "/api/up"
timeout = 30
interval = 60

[[provider]]
name = "postgres"
plan = "standard"
```
