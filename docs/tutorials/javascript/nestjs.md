---
tutorial:
  name: nestjs-hop3-tutorial
  env:
    NODE_ENV: development
  teardown:
    - rm -rf hop3-tuto-nestjs 2>/dev/null || true
    - hop3 app destroy --app hop3-tuto-nestjs -y 2>/dev/null || true
---

# Deploying Nest.js on Hop3

This guide walks you through deploying a Nest.js application on Hop3. By the end, you'll have a production-ready enterprise TypeScript API running on your own infrastructure.

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

## Step 1: Create a New Nest.js Application

Create a new Nest.js app using the CLI:

```bash exec id=create-nest timeout=180
CI=true npx --yes @nestjs/cli@latest new hop3-tuto-nestjs --package-manager npm --skip-git --skip-install
```

```assert file-exists path=hop3-tuto-nestjs/package.json
```

Install dependencies:

```bash exec id=install-deps dir=hop3-tuto-nestjs timeout=120
npm install
```

```output contains
added
```

```assert file-exists path=hop3-tuto-nestjs/src/main.ts
```

Verify the project structure:

```bash exec id=verify-structure dir=hop3-tuto-nestjs
ls -la src/
```

```output contains
main.ts
```

```output contains
app.module.ts
```

## Step 2: Create Health Check Endpoints

Create a health module:

```bash exec id=create-health-dir dir=hop3-tuto-nestjs
mkdir -p src/health
```

```file path=hop3-tuto-nestjs/src/health/health.controller.ts
import { Controller, Get } from '@nestjs/common';

@Controller()
export class HealthController {
  @Get('up')
  up(): string {
    return 'OK';
  }

  @Get('health')
  health() {
    return {
      status: 'ok',
      timestamp: new Date().toISOString(),
      uptime: process.uptime(),
      memory: process.memoryUsage(),
    };
  }

  @Get('api/info')
  info() {
    return {
      name: 'hop3-tuto-nestjs',
      version: '1.0.0',
      node: process.version,
      environment: process.env.NODE_ENV || 'development',
    };
  }
}
```

```file path=hop3-tuto-nestjs/src/health/health.module.ts
import { Module } from '@nestjs/common';
import { HealthController } from './health.controller';

@Module({
  controllers: [HealthController],
})
export class HealthModule {}
```

Update the main app module to include health:

```file path=hop3-tuto-nestjs/src/app.module.ts
import { Module } from '@nestjs/common';
import { AppController } from './app.controller';
import { AppService } from './app.service';
import { HealthModule } from './health/health.module';

@Module({
  imports: [HealthModule],
  controllers: [AppController],
  providers: [AppService],
})
export class AppModule {}
```

## Step 3: Update the Welcome Endpoint

Update the app controller:

```file path=hop3-tuto-nestjs/src/app.controller.ts
import { Controller, Get, Header } from '@nestjs/common';
import { AppService } from './app.service';

@Controller()
export class AppController {
  constructor(private readonly appService: AppService) {}

  @Get()
  @Header('Content-Type', 'text/html')
  getHello(): string {
    return `
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
          background: linear-gradient(135deg, #e0234e 0%, #9b1d3a 100%);
          color: white;
        }
        .container { text-align: center; padding: 2rem; }
        h1 { font-size: 3rem; margin-bottom: 1rem; }
        p { font-size: 1.25rem; opacity: 0.9; }
        a {
          display: inline-block;
          margin-top: 1rem;
          padding: 0.75rem 1.5rem;
          background: rgba(255,255,255,0.2);
          border-radius: 8px;
          color: white;
          text-decoration: none;
        }
      </style>
    </head>
    <body>
      <div class="container">
        <h1>Hello from Hop3!</h1>
        <p>Your Nest.js application is running.</p>
        <p>Current time: ${new Date().toISOString()}</p>
        <a href="/api/info">API Info</a>
      </div>
    </body>
    </html>
    `;
  }
}
```

## Step 4: Configure for Production

Update the main entry point to use environment port:

```file path=hop3-tuto-nestjs/src/main.ts
import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';

async function bootstrap() {
  const app = await NestFactory.create(AppModule);

  // SECURITY: Specify allowed origins explicitly - never use '*' in production
  const allowedOrigins = process.env.ALLOWED_ORIGINS;
  if (!allowedOrigins && process.env.NODE_ENV === 'production') {
    throw new Error('ALLOWED_ORIGINS must be set in production');
  }
  app.enableCors({
    origin: allowedOrigins ? allowedOrigins.split(',') : false,
  });

  // Global prefix (optional)
  // app.setGlobalPrefix('api');

  const port = process.env.PORT || 3000;
  await app.listen(port, '0.0.0.0');
  console.log(`Application is running on port ${port}`);
}
bootstrap();
```

## Step 5: Build and Verify

Build the application:

```bash exec id=build-app dir=hop3-tuto-nestjs timeout=120
npm run build && echo "Build completed"
```

```output contains
Build completed
```

Verify the build output:

```bash exec id=verify-build dir=hop3-tuto-nestjs
ls -la dist/
```

```output contains
main.js
```

Test that the application starts correctly (skipped in automated tests - local server tests are flaky):

```bash skip
node dist/main.js &
sleep 3
curl -s http://localhost:3000/health
```

Verify the build output:

```bash exec id=verify-build-files dir=hop3-tuto-nestjs
ls dist/main.js dist/app.module.js 2>/dev/null && echo "Build verified"
```

```output contains
Build verified
```

## Step 6: Create Deployment Configuration

### Create a Procfile

```file path=hop3-tuto-nestjs/Procfile
# Pre-build: Install dependencies and build
prebuild: npm install && npm run build

# Main web process
web: node dist/main.js
```

### Create hop3.toml

```file path=hop3-tuto-nestjs/hop3.toml
[metadata]
id = "hop3-tuto-nestjs"
version = "1.0.0"
title = "My Nest.js Application"

[build]
before-build = ["npm install", "npm run build"]
packages = ["nodejs", "npm"]

[run]
start = "node dist/main.js"

[env]
NODE_ENV = "production"

[port]
web = 3000

[healthcheck]
path = "/up"
timeout = 30
interval = 60
```

Verify the deployment files:

```bash exec id=verify-deploy-files dir=hop3-tuto-nestjs
ls -la Procfile hop3.toml
```

```output contains
Procfile
```

```output contains
hop3.toml
```

## Step 7: Initialize Git Repository

```file path=hop3-tuto-nestjs/.gitignore
# Dependencies
node_modules/

# Build output
dist/

# Environment
.env
.env.*

# IDE
.idea/
.vscode/

# OS
.DS_Store

# Logs
*.log

# Testing
coverage/
```

```bash exec id=git-init dir=hop3-tuto-nestjs
git init
```

```output contains
Initialized empty Git repository
```

```bash exec id=git-add dir=hop3-tuto-nestjs
git add .
```

```bash exec id=git-commit dir=hop3-tuto-nestjs
git commit -m "Initial Nest.js application"
```

```output contains
Initial Nest.js application
```

## Step 8: Deploy to Hop3

The following steps require a Hop3 server.

### Initialize (First Time Only)

```bash skip
hop3 init --ssh root@your-server.example.com
```

### Deploy

Deploy the application (first deployment creates the app):

```bash exec id=deploy dir=hop3-tuto-nestjs timeout=120
hop3 deploy hop3-tuto-nestjs
```

### Set Hostname

Configure the hostname for nginx proxy:

```bash exec id=set-hostname timeout=30
hop3 config set --app hop3-tuto-nestjs HOST_NAME=hop3-tuto-nestjs.$HOP3_TEST_DOMAIN
```

### Set Environment Variables

Configure additional environment variables:

```bash exec id=set-env timeout=30
hop3 config set --app hop3-tuto-nestjs ALLOWED_ORIGINS=http://hop3-tuto-nestjs.$HOP3_TEST_DOMAIN
```

### Apply Configuration

Redeploy to apply the hostname and environment configuration:

```bash exec id=redeploy dir=hop3-tuto-nestjs timeout=120
hop3 deploy hop3-tuto-nestjs
```

Wait for the application to start:

```bash exec id=wait-for-app timeout=10
sleep 5
```

### Verify Deployment

```bash exec id=check-status timeout=30
hop3 status --app hop3-tuto-nestjs
```

```output contains
hop3-tuto-nestjs
```

```bash exec id=check-health timeout=30
curl -s http://hop3-tuto-nestjs.$HOP3_TEST_DOMAIN/up
```

```output contains
OK
```

### Managing Your Application

```bash skip
# Restart the application
hop3 restart --app hop3-tuto-nestjs

# View logs
hop3 logs --app hop3-tuto-nestjs

# View/set environment variables
hop3 config show --app hop3-tuto-nestjs
hop3 config set --app hop3-tuto-nestjs NEW_VAR=value

# Scale workers
hop3 ps scale --app hop3-tuto-nestjs web=2
```

## Advanced Configuration

### Adding TypeORM with PostgreSQL

```bash skip
npm install @nestjs/typeorm typeorm pg
```

```typescript
// src/app.module.ts
import { TypeOrmModule } from '@nestjs/typeorm';

@Module({
  imports: [
    TypeOrmModule.forRoot({
      type: 'postgres',
      url: process.env.DATABASE_URL,
      autoLoadEntities: true,
      synchronize: process.env.NODE_ENV !== 'production',
    }),
  ],
})
export class AppModule {}
```

### Adding Validation

```bash skip
npm install class-validator class-transformer
```

```typescript
// src/main.ts
import { ValidationPipe } from '@nestjs/common';
app.useGlobalPipes(new ValidationPipe({ transform: true }));
```

### Adding Swagger Documentation

```bash skip
npm install @nestjs/swagger
```

```typescript
// src/main.ts
import { DocumentBuilder, SwaggerModule } from '@nestjs/swagger';

const config = new DocumentBuilder()
  .setTitle('My API')
  .setVersion('1.0')
  .build();
const document = SwaggerModule.createDocument(app, config);
SwaggerModule.setup('docs', app, document);
```

### Queue Processing with Bull

```bash skip
npm install @nestjs/bull bull
```

```typescript
// src/app.module.ts
import { BullModule } from '@nestjs/bull';

@Module({
  imports: [
    BullModule.forRoot({
      redis: process.env.REDIS_URL,
    }),
  ],
})
export class AppModule {}
```

## Troubleshooting

### Build Failures
- Ensure TypeScript compiles without errors: `npm run build`
- Check for missing dependencies

### Runtime Errors
- Verify PORT environment variable
- Check database connection strings

## Example Files

### Complete hop3.toml

```toml
[metadata]
id = "hop3-tuto-nestjs"
version = "1.0.0"
title = "My Nest.js Application"

[build]
before-build = ["npm install", "npm run build"]
packages = ["nodejs"]

[run]
start = "node dist/main.js"
before-run = "npm run migration:run"

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

[[provider]]
name = "redis"
plan = "basic"
```

### Complete Procfile

```procfile
prebuild: npm install && npm run build
prerun: npm run migration:run || true
web: node dist/main.js
worker: node dist/worker.js
```
