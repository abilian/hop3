---
tutorial:
  name: hop3-tuto-static
  teardown:
    - rm -rf hop3-tuto-static 2>/dev/null || true
    - hop3 app destroy --app hop3-tuto-static -y 2>/dev/null || true
---

# Deploying a Static Site on Hop3

This guide walks you through deploying a **plain static site** — just HTML, CSS, and JavaScript files — on Hop3. There is no build step and no application server: Hop3's static deployer configures nginx to serve your files directly. It's the simplest possible deployment.

> **New to static sites on Hop3?** Read the [Static Sites overview](index.md) for the two deployment strategies (build at the source vs. build on the server). Using a generator? Its build output is also just static files, so it deploys the same way — see [Hugo](hugo.md), [Eleventy](eleventy.md), [Astro](astro.md), or [Jekyll](jekyll.md).

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

Tell Hop3 to serve the `public/` directory as static. The recommended way is a short `hop3.toml` — **no `Procfile` required**. The `static` worker makes Hop3 skip the language toolchains and application servers entirely and serve the directory directly through nginx:

```bash exec id=create-config dir=hop3-tuto-static
cat > hop3.toml <<'TOML'
[metadata]
id = "hop3-tuto-static"

[run.workers]
static = "public"
TOML
```

Confirm the configuration:

```bash exec id=verify-config dir=hop3-tuto-static
cat hop3.toml
```

```output contains
static = "public"
```

> Prefer a `Procfile`? `echo "static: public" > Procfile` works too. Hop3 accepts either, but `hop3.toml` wins if both declare a static directory — it's Hop3's own config file, whereas a `Procfile` is a generic, cross-tool convention that may belong to something else.

## Deploy to Hop3

The following steps require a Hop3 server.

### Initialize (First Time Only)

```bash skip
hop3 init --ssh root@your-server.example.com
```

### Deploy

Deploy the site (the first deployment creates the app):

```bash exec id=deploy dir=hop3-tuto-static timeout=120
hop3 deploy --app hop3-tuto-static
```

```output contains
deployed successfully
```

### Set Hostname

Configure the hostname for the nginx proxy:

```bash exec id=set-hostname timeout=30
hop3 env set --app hop3-tuto-static HOST_NAME=hop3-tuto-static.$HOP3_TEST_DOMAIN
```

### Wait for Process Stop

Wait for the previous deployment to fully stop:

```bash exec id=wait-before-redeploy timeout=10
sleep 5
```

### Apply Configuration

Redeploy to apply the hostname configuration:

```bash exec id=redeploy dir=hop3-tuto-static timeout=120
hop3 deploy --app hop3-tuto-static
```

```output contains
deployed successfully
```

### Verify Deployment

```bash exec id=check-status timeout=30
hop3 app status --app hop3-tuto-static
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

- **No build, no runtime.** Hop3 sees the `static` directive (in `hop3.toml` or a `Procfile`) and uses its static deployer instead of a language toolchain or application server.
- **nginx serves your files.** The named directory (`public/`) is served directly; requests never reach an app process.
- **Anything static works.** Drop in CSS, JavaScript, images, or the build output of any static-site generator.

## Useful Commands

```bash skip
hop3 app logs --app hop3-tuto-static        # View logs
hop3 app restart --app hop3-tuto-static     # Restart the app
hop3 env show --app hop3-tuto-static # Show configuration
hop3 app destroy --app hop3-tuto-static -y  # Remove the app
```

## Next Steps

- Put a static-site generator in front of the same workflow: [Hugo](hugo.md), [Eleventy](eleventy.md), [Astro](astro.md), [Jekyll](jekyll.md).
- Add a custom domain and TLS — see the deployment guides.
