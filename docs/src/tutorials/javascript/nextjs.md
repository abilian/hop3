# Deploying Next.js on Hop3

This guide walks you through deploying a Next.js application on Hop3. By the end, you'll have a production-ready React application with server-side rendering running on your own infrastructure.

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

## Step 1: Create a New Next.js Application

Create a new Next.js app with minimal configuration:

```bash
CI=true NEXT_TELEMETRY_DISABLED=1 npx --yes create-next-app@latest hop3-tuto-nextjs --yes --typescript --tailwind --eslint --app --src-dir --no-import-alias --use-npm --no-turbopack
```

Verify the project structure:

```bash
ls -la
```

```console
package.json
```

```console
src
```

## Step 2: Configure for Production Deployment

### Enable Standalone Output

Create `next.config.mjs` to enable standalone output mode (creates a minimal production bundle).
This will replace any existing Next.js config:

```bash
rm -f next.config.ts next.config.mjs next.config.js 2>/dev/null; ls -la next.config* 2>/dev/null || echo "Config files removed"
```

```text
/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  images: {
    unoptimized: process.env.NEXT_IMAGE_UNOPTIMIZED === "true",
  },
};

export default nextConfig;
```

Verify the config file was created:

```bash
cat next.config.mjs | head -5
```

```console
standalone
```

### Create Health Check Endpoint

Create an API route for health checks:

```bash
mkdir -p src/app/api/health
```

```typescript
import { NextResponse } from "next/server";

export async function GET() {
  return NextResponse.json({
    status: "ok",
    timestamp: new Date().toISOString(),
    uptime: process.uptime(),
  });
}
```

Create a simple `/up` endpoint:

```bash
mkdir -p src/app/up
```

```typescript
import { NextResponse } from "next/server";

export async function GET() {
  return new NextResponse("OK", { status: 200 });
}
```

## Step 3: Customize the Home Page

Replace the default home page with a custom welcome page:

```typescript
export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-24">
      <div className="text-center">
        <h1 className="text-4xl font-bold mb-4">Hello from Hop3!</h1>
        <p className="text-xl text-gray-600 mb-8">
          Your Next.js application is running.
        </p>
        <div className="flex gap-4 justify-center">
          <a
            href="/api/health"
            className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
          >
            Health Check
          </a>
        </div>
      </div>
    </main>
  );
}
```

## Step 4: Build and Verify

Build the application to ensure it compiles correctly:

```bash
npm run build && echo "Build completed" || echo "Build step (may have warnings)"
```

Verify the standalone output was created:

```bash
ls -la .next/standalone/
```

```console
server.js
```

## Step 5: Create Deployment Configuration

### Create a Procfile

Create a `Procfile` in your project root:

```procfile
# Pre-build: Install dependencies and build
prebuild: npm install && npm run build

# Copy static files to standalone directory
prerun: cp -r .next/static .next/standalone/.next/ && cp -r public .next/standalone/ 2>/dev/null || true

# Main web process (uses standalone server)
web: node .next/standalone/server.js
```

### Create hop3.toml

Create a `hop3.toml` for advanced configuration:

```toml
[metadata]
id = "hop3-tuto-nextjs"
version = "1.0.0"
title = "My Next.js Application"

[build]
before-build = [
    "npm install",
    "npm run build"
]
packages = ["nodejs", "npm"]

[run]
start = "node .next/standalone/server.js"
before-run = "cp -r .next/static .next/standalone/.next/ && cp -r public .next/standalone/ 2>/dev/null || true"

[env]
NODE_ENV = "production"
HOSTNAME = "0.0.0.0"

[port]
web = 3000

[healthcheck]
path = "/up"
timeout = 30
interval = 60
```

Verify the deployment files exist:

```bash
ls -la Procfile hop3.toml
```

```console
Procfile
```

```console
hop3.toml
```

## Step 6: Initialize Git Repository

Create a `.gitignore` file (Next.js creates one, but let's ensure it's complete):

```text
# Dependencies
node_modules/
/.pnp
.pnp.js

# Build output
/.next/
/out/
/build

# Environment
.env
.env.local
.env.development.local
.env.test.local
.env.production.local

# Debug
npm-debug.log*
yarn-debug.log*
yarn-error.log*

# Vercel
.vercel

# TypeScript
*.tsbuildinfo
next-env.d.ts

# OS files
.DS_Store
Thumbs.db

# IDE
.idea/
.vscode/
*.swp
*.swo
```

Initialize the repository:

```bash
git init
```

```bash
git add .
```

```bash
git commit -m "Initial Next.js application"
```

```console
Initial Next.js application
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
hop3 deploy hop3-tuto-nextjs
```

### Set Hostname

Configure the hostname for nginx proxy:

```bash
hop3 config:set hop3-tuto-nextjs HOST_NAME=hop3-tuto-nextjs.$HOP3_TEST_DOMAIN
```

### Wait for Process Stop

Wait for the previous deployment to fully stop:

```bash
sleep 5
```

### Apply Configuration

Redeploy to apply the hostname configuration:

```bash
hop3 deploy hop3-tuto-nextjs
```

```console
deployed successfully
```

You'll see output showing:
- Code upload
- Dependency installation (`npm install`)
- Application build (`npm run build`)
- Static file copying
- Application startup

## Step 8: Verify Deployment

Check your application status:

```bash
hop3 app:status hop3-tuto-nextjs
```

```console
hop3-tuto-nextjs
```

```bash
curl -s http://hop3-tuto-nextjs.$HOP3_TEST_DOMAIN/up
```

```console
OK
```

## Managing Your Application

### Restart the Application

```bash
hop3 app:restart hop3-tuto-nextjs
```

### View and Manage Environment Variables

```bash
# List all variables
hop3 config:show hop3-tuto-nextjs

# Set a variable
hop3 config:set hop3-tuto-nextjs NEXT_PUBLIC_API_URL=https://api.example.com

# Remove a variable
hop3 config:unset hop3-tuto-nextjs OLD_VARIABLE
```

### Scaling

```bash
# Check current processes
hop3 ps hop3-tuto-nextjs

# Scale web workers
hop3 ps:scale hop3-tuto-nextjs web=2
```

## Advanced Configuration

### Adding a Database (PostgreSQL with Prisma)

Install Prisma:

```bash
cd hop3-tuto-nextjs
npm install prisma @prisma/client
npx prisma init
```

Configure the database in `prisma/schema.prisma`:

```prisma
datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}

generator client {
  provider = "prisma-client-js"
}

model User {
  id        Int      @id @default(autoincrement())
  email     String   @unique
  name      String?
  createdAt DateTime @default(now())
}
```

Update `hop3.toml` to run migrations:

```toml
[run]
before-run = "npx prisma migrate deploy && cp -r .next/static .next/standalone/.next/"
```

Attach a database addon:

```bash
hop3 addons:create postgres hop3-tuto-nextjs-db
hop3 addons:attach hop3-tuto-nextjs hop3-tuto-nextjs-db
```

### Environment Variables for Client-Side

Next.js exposes environment variables prefixed with `NEXT_PUBLIC_` to the browser:

```bash
# Server-side only (secure)
hop3 config:set hop3-tuto-nextjs DATABASE_URL=postgres://...
hop3 config:set hop3-tuto-nextjs SECRET_KEY=your-secret

# Client-side (visible in browser)
hop3 config:set hop3-tuto-nextjs NEXT_PUBLIC_API_URL=https://api.example.com
```

!!! warning "Security Note"
    Never put secrets in `NEXT_PUBLIC_` variables. They are embedded in the JavaScript bundle and visible to anyone.

### Custom Server (Advanced)

For custom server needs, create `server.js`:

```javascript
const { createServer } = require('http');
const { parse } = require('url');
const next = require('next');

const dev = process.env.NODE_ENV !== 'production';
const hostname = process.env.HOSTNAME || 'localhost';
const port = parseInt(process.env.PORT || '3000', 10);

const app = next({ dev, hostname, port });
const handle = app.getRequestHandler();

app.prepare().then(() => {
  createServer(async (req, res) => {
    try {
      const parsedUrl = parse(req.url, true);
      await handle(req, res, parsedUrl);
    } catch (err) {
      console.error('Error occurred handling', req.url, err);
      res.statusCode = 500;
      res.end('internal server error');
    }
  }).listen(port, () => {
    console.log(`> Ready on http://${hostname}:${port}`);
  });
});
```

Update `Procfile`:

```procfile
web: node server.js
```

### Image Optimization

Next.js Image Optimization requires additional configuration for self-hosting:

```typescript
// next.config.ts
const nextConfig: NextConfig = {
  output: "standalone",
  images: {
    // Use unoptimized images (simplest)
    unoptimized: true,
    // Or configure remote patterns for external images
    // remotePatterns: [
    //   { protocol: 'https', hostname: 'example.com' }
    // ],
  },
};
```

### ISR (Incremental Static Regeneration)

ISR works out of the box with standalone mode. Configure revalidation in your pages:

```typescript
// In a Server Component
export const revalidate = 60; // Revalidate every 60 seconds

export default async function Page() {
  const data = await fetch('https://api.example.com/data');
  return <div>{/* ... */}</div>;
}
```

### API Routes with Database

Example API route with database access:

```typescript
// src/app/api/users/route.ts
import { NextResponse } from "next/server";
import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();

export async function GET() {
  const users = await prisma.user.findMany();
  return NextResponse.json(users);
}

export async function POST(request: Request) {
  const body = await request.json();
  const user = await prisma.user.create({
    data: { email: body.email, name: body.name },
  });
  return NextResponse.json(user, { status: 201 });
}
```

## Troubleshooting

### Application Won't Start

Check the logs for errors:

```bash
hop3 app:logs hop3-tuto-nextjs --tail
```

Common issues:
- **Missing standalone output**: Ensure `output: "standalone"` is in `next.config.ts`
- **Static files not copied**: Check the `prerun` command in Procfile
- **Wrong hostname binding**: Set `HOSTNAME=0.0.0.0`

### Build Failures

If the build fails:

1. Check Node.js version matches locally and on server
2. Ensure all dependencies are in `dependencies` (not just `devDependencies`)
3. Run `npm run build` locally to see detailed errors

### Memory Issues

Next.js can consume significant memory during build:

```bash
hop3 config:set hop3-tuto-nextjs NODE_OPTIONS="--max-old-space-size=2048"
```

### Static Assets Not Loading

Ensure static files are copied to standalone directory:

```bash
cp -r .next/static .next/standalone/.next/
cp -r public .next/standalone/
```

### Slow Cold Starts

To improve cold start times:
- Minimize dependencies
- Use dynamic imports for heavy components
- Consider edge runtime for API routes where appropriate

## Static Export (Alternative)

For fully static sites (no SSR), use static export:

```typescript
// next.config.ts
const nextConfig: NextConfig = {
  output: "export",
};
```

Update deployment:

```toml
[build]
before-build = ["npm install", "npm run build"]

[run]
start = "npx serve out -l $PORT"

[env]
NODE_ENV = "production"
```

Install serve:

```bash
npm install serve
```

## Next Steps

- **[CLI Reference](../../reference/cli.md)** - Complete command reference
- **[hop3.toml Reference](../../reference/config.md)** - Full configuration options
- **[Backup and Restore Guide](../../guides/backup-restore.md)** - Protect your data

## Example Files

### Complete hop3.toml for Next.js

```toml
# hop3.toml - Next.js Application

[metadata]
id = "hop3-tuto-nextjs"
version = "1.0.0"
title = "My Next.js Application"
author = "Your Name <you@example.com>"

[build]
before-build = [
    "npm install",
    "npm run build"
]
packages = ["nodejs"]

[run]
start = "node .next/standalone/server.js"
before-run = "cp -r .next/static .next/standalone/.next/ && cp -r public .next/standalone/ 2>/dev/null || true"

[env]
NODE_ENV = "production"
HOSTNAME = "0.0.0.0"

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

### Complete Procfile for Next.js

```procfile
# Procfile - Next.js Application

# Build phase
prebuild: npm install && npm run build

# Pre-run: Copy static assets to standalone directory
prerun: cp -r .next/static .next/standalone/.next/ && cp -r public .next/standalone/ 2>/dev/null || true

# Web server (standalone mode)
web: node .next/standalone/server.js
```
