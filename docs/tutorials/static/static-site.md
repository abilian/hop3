---
tutorial:
  name: hop3-tuto-static
  teardown:
    - rm -rf hop3-tuto-static 2>/dev/null || true
    - hop3 app destroy --app hop3-tuto-static -y 2>/dev/null || true
---

# Deploying a Static Site on Hop3

This guide walks you through deploying a **plain static site** — just HTML, CSS, and JavaScript files — on Hop3. There is no build step and no application server: Hop3's static deployer configures nginx to serve your files directly. It's the simplest possible deployment.

> Using a static-site generator? Its build output is also just static files, so it deploys the same way — see the [Hugo](../go/hugo.md), [Eleventy](../javascript/eleventy.md), [Astro](../javascript/astro.md), or [Jekyll](../ruby/jekyll.md) tutorials.

## Prerequisites

Before you begin, ensure you have:

1. **A Hop3 server** - Follow the [Installation Guide](../../get-started/server-setup.md)
2. **The Hop3 CLI** - Installed on your local machine

No language runtime is required — that's the whole point of a static site.

## Step 1: Create the Site

Create a project directory with a `public/` folder to hold the files nginx will serve:

```bash exec id=create-project
mkdir hop3-tuto-static && cd hop3-tuto-static && mkdir public
```

Add a home page:

```bash exec id=create-index dir=hop3-tuto-static
cat > public/index.html <<'HTML'
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Hop3 Static Site</title>
  </head>
  <body>
    <h1>Hello from Hop3</h1>
    <p>This page is served as a plain static site — no build, no app server.</p>
  </body>
</html>
HTML
```

## Step 2: Configure Hop3

Hop3 serves static files via a one-line `Procfile`. The `static:` directive tells Hop3 to skip the language toolchains and application servers entirely and serve the named directory directly through nginx:

```bash exec id=create-procfile dir=hop3-tuto-static
echo "static: public" > Procfile
```

Confirm the configuration:

```bash exec id=verify-procfile dir=hop3-tuto-static
cat Procfile
```

```output contains
static: public
```

## Deploy to Hop3

The following steps require a Hop3 server.

### Initialize (First Time Only)

```bash skip
hop3 init --ssh root@your-server.example.com
```

### Deploy

Deploy the site (the first deployment creates the app):

```bash exec id=deploy dir=hop3-tuto-static timeout=120
hop3 deploy hop3-tuto-static
```

```output contains
deployed successfully
```

### Set Hostname

Configure the hostname for the nginx proxy:

```bash exec id=set-hostname timeout=30
hop3 config set --app hop3-tuto-static HOST_NAME=hop3-tuto-static.$HOP3_TEST_DOMAIN
```

### Wait for Process Stop

Wait for the previous deployment to fully stop:

```bash exec id=wait-before-redeploy timeout=10
sleep 5
```

### Apply Configuration

Redeploy to apply the hostname configuration:

```bash exec id=redeploy dir=hop3-tuto-static timeout=120
hop3 deploy hop3-tuto-static
```

```output contains
deployed successfully
```

### Verify Deployment

```bash exec id=check-status timeout=30
hop3 status --app hop3-tuto-static
```

```output contains
hop3-tuto-static
```

```bash exec id=check-health timeout=30
curl -s http://hop3-tuto-static.$HOP3_TEST_DOMAIN/
```

```output contains
Hello from Hop3
```

## How It Works

- **No build, no runtime.** Hop3 sees the `static:` Procfile directive and uses its static deployer instead of a language toolchain or application server.
- **nginx serves your files.** The named directory (`public/`) is served directly; requests never reach an app process.
- **Anything static works.** Drop in CSS, JavaScript, images, or the build output of any static-site generator.

## Useful Commands

```bash skip
hop3 logs --app hop3-tuto-static        # View logs
hop3 restart --app hop3-tuto-static     # Restart the app
hop3 config show --app hop3-tuto-static # Show configuration
hop3 app destroy --app hop3-tuto-static -y  # Remove the app
```

## Next Steps

- Put a static-site generator in front of the same workflow: [Hugo](../go/hugo.md), [Eleventy](../javascript/eleventy.md), [Astro](../javascript/astro.md), [Jekyll](../ruby/jekyll.md).
- Add a custom domain and TLS — see the deployment guides.
