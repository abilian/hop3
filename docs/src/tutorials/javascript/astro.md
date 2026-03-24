# Deploying Astro on Hop3

This guide walks you through deploying an Astro site on Hop3. Astro is a modern static site builder that ships zero JavaScript by default and supports partial hydration.

## Prerequisites

Before you begin, ensure you have:

1. **A Hop3 server** - Follow the [Installation Guide](../../get-started/server-setup.md)
2. **The Hop3 CLI** - Installed on your local machine
3. **Node.js 18+** - Install from [nodejs.org](https://nodejs.org/)
4. **Git** - For version control and deployment

Verify your local setup:

```bash
node -v
```

## Step 1: Create a New Astro Site

```bash
CI=true ASTRO_TELEMETRY_DISABLED=1 npm create astro@latest hop3-tuto-astro -- --template minimal --no-install --no-git --yes
```

Install dependencies:

```bash
npm install
```

```console
added
```

## Step 2: Create Site Structure

Create the layout:

```text
---
interface Props {
  title: string;
}

const { title } = Astro.props;
---

<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} | My Astro Site</title>
    <style is:global>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 2rem;
            line-height: 1.6;
        }
        header {
            border-bottom: 1px solid #eee;
            padding-bottom: 1rem;
            margin-bottom: 2rem;
        }
        nav a {
            margin-right: 1rem;
            text-decoration: none;
            color: #333;
        }
        nav a:hover {
            color: #ff5d01;
        }
        .hero {
            background: linear-gradient(135deg, #ff5d01 0%, #ff8a4c 100%);
            color: white;
            padding: 3rem;
            border-radius: 8px;
            text-align: center;
            margin-bottom: 2rem;
        }
        .hero h1 {
            font-size: 2.5rem;
            margin-bottom: 0.5rem;
        }
    </style>
</head>
<body>
    <header>
        <nav>
            <a href="/">Home</a>
            <a href="/about">About</a>
            <a href="/blog">Blog</a>
        </nav>
    </header>
    <main>
        <slot />
    </main>
    <footer>
        <p>&copy; 2024 My Astro Site on Hop3</p>
    </footer>
</body>
</html>
```

## Step 3: Create Pages

Update the home page:

```text
---
import Base from '../layouts/Base.astro';
---

<Base title="Home">
    <div class="hero">
        <h1>Hello from Hop3!</h1>
        <p>Your Astro site is running.</p>
        <p>Current time: {new Date().toISOString()}</p>
    </div>

    <h2>Welcome</h2>
    <p>This is an Astro static site deployed on Hop3.</p>

    <h2>Why Astro?</h2>
    <ul>
        <li><strong>Zero JS by default</strong> - Ships HTML, adds JS only when needed</li>
        <li><strong>Component Islands</strong> - Partial hydration for interactive components</li>
        <li><strong>Framework agnostic</strong> - Use React, Vue, Svelte, or vanilla JS</li>
    </ul>
</Base>
```

Create the about page:

```text
---
import Base from '../layouts/Base.astro';
---

<Base title="About">
    <h1>About</h1>

    <h2>About This Site</h2>
    <p>This Astro site demonstrates static site deployment on Hop3.</p>

    <h3>Features</h3>
    <ul>
        <li><strong>Fast</strong> - Ships minimal JavaScript</li>
        <li><strong>Modern</strong> - Built for the modern web</li>
        <li><strong>Flexible</strong> - Use any UI framework</li>
    </ul>
</Base>
```

Create a blog directory and posts:

```bash
mkdir -p src/pages/blog
```

```text
---
import Base from '../../layouts/Base.astro';

const posts = [
    { title: 'Hello World', slug: 'hello-world', date: '2024-01-01' },
    { title: 'Getting Started with Astro', slug: 'getting-started', date: '2024-01-02' },
];
---

<Base title="Blog">
    <h1>Blog</h1>

    <ul>
        {posts.map((post) => (
            <li>
                <a href={`/blog/${post.slug}`}>{post.title}</a>
                <small>({post.date})</small>
            </li>
        ))}
    </ul>
</Base>
```

```text
---
import Base from '../../layouts/Base.astro';
---

<Base title="Hello World">
    <article>
        <h1>Hello World</h1>
        <p><small>January 1, 2024</small></p>

        <p>Welcome to our Astro site on Hop3!</p>

        <h2>Getting Started</h2>
        <p>Astro makes building fast websites easy:</p>

        <ol>
            <li>Create pages in <code>src/pages/</code></li>
            <li>Use <code>.astro</code> components for layouts</li>
            <li>Add interactive islands when needed</li>
        </ol>
    </article>
</Base>
```

## Step 4: Build and Test

Build the site:

```bash
npm run build
```

```console
Complete!
```

Verify the build:

```bash
ls -la dist/
```

```console
index.html
```

Test the build:

```bash
cat dist/index.html | grep "Hello from Hop3" | head -1
```

```console
Hello from Hop3
```

## Step 5: Create Deployment Configuration

Configure Astro for static output:

```text
import { defineConfig } from 'astro/config';

export default defineConfig({
  output: 'static',
  build: {
    assets: 'assets'
  }
});
```

```procfile
prebuild: npm install && npm run build
web: npx serve dist -l $PORT
```

```toml
[metadata]
id = "hop3-tuto-astro"
version = "1.0.0"
title = "My Astro Site"

[build]
before-build = ["npm install", "npm run build"]
packages = ["nodejs", "npm"]

[run]
start = "npx serve dist -l $PORT"

[port]
web = 3000

[healthcheck]
path = "/"
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
hop3 deploy hop3-tuto-astro
```

```console
deployed successfully
```

### Set Hostname

Configure the hostname for nginx proxy:

```bash
hop3 config:set hop3-tuto-astro HOST_NAME=hop3-tuto-astro.$HOP3_TEST_DOMAIN
```

### Wait for Process Stop

Wait for the previous deployment to fully stop:

```bash
sleep 5
```

### Apply Configuration

Redeploy to apply the hostname configuration:

```bash
hop3 deploy hop3-tuto-astro
```

```console
deployed successfully
```

### Verify Deployment

```bash
hop3 app:status hop3-tuto-astro
```

```console
hop3-tuto-astro
```

```bash
curl -s http://hop3-tuto-astro.$HOP3_TEST_DOMAIN/
```

```console
Hello from Hop3
```

### Managing Your Application

```bash
# Restart the application
hop3 app:restart hop3-tuto-astro

# View logs
hop3 app:logs hop3-tuto-astro

# View/set environment variables
hop3 config:show hop3-tuto-astro
hop3 config:set hop3-tuto-astro NEW_VAR=value

# Scale workers
hop3 ps:scale hop3-tuto-astro web=2
```

## Advanced Configuration

### SSR Mode (Server-Side Rendering)

```javascript
// astro.config.mjs
import { defineConfig } from 'astro/config';
import node from '@astrojs/node';

export default defineConfig({
  output: 'server',
  adapter: node({ mode: 'standalone' })
});
```

```toml
# hop3.toml
[run]
start = "node dist/server/entry.mjs"
```

### Adding React Components

```bash
npx astro add react
```

```astro
---
import Counter from '../components/Counter.jsx';
---

<Counter client:load />
```

### Content Collections

```typescript
// src/content/config.ts
import { defineCollection, z } from 'astro:content';

const blog = defineCollection({
  schema: z.object({
    title: z.string(),
    date: z.date(),
    draft: z.boolean().default(false),
  }),
});

export const collections = { blog };
```

### Image Optimization

```astro
---
import { Image } from 'astro:assets';
import myImage from '../assets/image.png';
---

<Image src={myImage} alt="Description" />
```

### MDX Support

```bash
npx astro add mdx
```

### Tailwind CSS

```bash
npx astro add tailwind
```

## Troubleshooting

### Build Errors
Check for syntax errors in `.astro` files.

### Missing Pages
Ensure pages are in `src/pages/` directory.

### Hydration Issues
Use correct `client:*` directives for interactive components.

## Example hop3.toml

```toml
[metadata]
id = "hop3-tuto-astro"
version = "1.0.0"
title = "My Astro Site"

[build]
before-build = ["npm install", "npm run build"]
packages = ["nodejs", "npm"]

[run]
start = "npx serve dist -l $PORT -s"

[port]
web = 3000

[healthcheck]
path = "/"
```

### SSR Mode hop3.toml

```toml
[metadata]
id = "hop3-tuto-astro"
version = "1.0.0"

[build]
before-build = ["npm install", "npm run build"]
packages = ["nodejs"]

[run]
start = "node dist/server/entry.mjs"

[env]
HOST = "0.0.0.0"

[port]
web = 4321

[healthcheck]
path = "/"
```
