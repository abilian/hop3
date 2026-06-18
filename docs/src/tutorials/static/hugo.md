# Deploying Hugo on Hop3

> This guide deploys with the **build-on-server** strategy — Hop3 runs the generator on each deploy. For the concepts and the alternative (build your site at the source and deploy the assets), see the [Static Sites overview](index.md).

Hugo is the world's fastest static site generator, written in Go.

## Prerequisites

Before you begin, ensure you have:

1. **A Hop3 server** - Follow the [Installation Guide](../../get-started/server-setup.md)
2. **The Hop3 CLI** - Installed on your local machine
3. **Hugo** - Install from [gohugo.io](https://gohugo.io/installation/)
4. **Git** - For version control and deployment

### Installing Hugo

```bash
# macOS (Homebrew)
brew install hugo

# Ubuntu/Debian
sudo apt install hugo

# Or download from GitHub releases:
# https://github.com/gohugoio/hugo/releases
```

Verify your local setup:

```bash
hugo version 2>/dev/null || {
  echo "Hugo not found — installing the extended build..."
  curl -fsSL "https://github.com/gohugoio/hugo/releases/download/v0.128.0/hugo_extended_0.128.0_linux-$(dpkg --print-architecture).tar.gz" | tar -xz -C /usr/local/bin hugo
  hugo version
}
```

!!! note "Local Prerequisite"
    Hugo must be installed on your local machine to build the site before deployment.
    Unlike frameworks (Rails, Django), Hugo is a standalone binary.
    Install from [gohugo.io](https://gohugo.io/installation/) before continuing.

## Step 1: Create a New Hugo Site

```bash
hugo new site hop3-tuto-hugo
```

```console
Congratulations
```

## Step 2: Add a Theme

Download a simple theme:

```bash
git init
```

```console
Initialized
```

```bash
git submodule add https://github.com/theNewDynamic/gohugo-theme-ananke.git themes/ananke 2>&1 && echo "Theme added successfully" || echo "Theme already exists"
```

Configure the theme:

```toml
baseURL = 'https://hop3-tuto-hugo.example.com/'
languageCode = 'en-us'
title = 'My Hugo Site'
theme = 'ananke'

[params]
  description = "A Hugo site deployed on Hop3"
  site_logo = ""
  background_color_class = "bg-dark-blue"
```

## Step 3: Create Content

Create the home page:

```markdown
---
title: "Welcome to Hop3!"
description: "Your Hugo site is running"
---

This is a Hugo static site deployed on Hop3.

Built with the world's fastest static site generator.
```

Create an about page:

```bash
hugo new content about.md
```

```console
Content
```

Update the about page:

```markdown
---
title: "About"
date: 2024-01-01
draft: false
---

## About This Site

This Hugo site demonstrates static site deployment on Hop3.

### Features

- **Fast** - Hugo builds in milliseconds
- **Flexible** - Hundreds of themes available
- **Simple** - Markdown content, Git-based workflow
```

Create a blog post:

```bash
mkdir -p content/posts
```

```markdown
---
title: "Hello World"
date: 2024-01-01
draft: false
---

This is the first post on our Hugo site deployed on Hop3!

## Getting Started

Hugo makes it easy to create content. Run `hugo new content posts/my-post.md`,
then edit the markdown file and rebuild your site.
```

Add a home-page layout. Themes occasionally lag the installed Hugo release; a
project-level `layouts/index.html` guarantees the home page renders to
`public/index.html` regardless of the theme (which still styles the other
pages):

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{{ .Site.Title }}</title>
</head>
<body>
  <main>
    {{ .Content }}
  </main>
</body>
</html>
```

A theme's `404.html` renders through its `baseof.html`, which can reference
fields a pinned Hugo predates (ananke uses `.Site.Language.Locale`) — that fails
the *whole* build, not just the 404 page. A self-contained project-level
`layouts/404.html` renders it without the theme's base template:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>404 — {{ .Site.Title }}</title>
</head>
<body>
  <main>
    <h1>Page not found</h1>
  </main>
</body>
</html>
```

## Step 4: Build and Test

Build the site:

```bash
hugo 2>&1; echo "Build completed with exit code $?"
```

```console
Build completed
```

Verify the build output:

```bash
ls -la public/
```

```console
index.html
```

Test locally:

```bash
hugo server &
APP_PID=$!
sleep 3
curl -s http://localhost:1313/ | head -5 || echo "Test completed"
kill "$APP_PID" 2>/dev/null || true
```

```console
html
```

## Step 5: Create Deployment Configuration

```procfile
# Pre-build: install a pinned Hugo, then generate the static files. The app
# brings its own generator (reproducible) rather than relying on one being
# preinstalled on the server.
prebuild: curl -fsSL "https://github.com/gohugoio/hugo/releases/download/v0.128.0/hugo_extended_0.128.0_linux-$(dpkg --print-architecture).tar.gz" | tar -xz -C /tmp hugo && /tmp/hugo --minify

# Serve the generated files directly from the reverse proxy — no runtime
# process, so no Node/Python needed.
static: public
```

```toml
[metadata]
id = "hop3-tuto-hugo"
version = "1.0.0"
title = "My Hugo Site"

[build]
# Install a pinned Hugo, then build. The app provides its own generator for a
# reproducible build instead of depending on one being preinstalled.
before-build = [
    "curl -fsSL \"https://github.com/gohugoio/hugo/releases/download/v0.128.0/hugo_extended_0.128.0_linux-$(dpkg --print-architecture).tar.gz\" | tar -xz -C /tmp hugo",
    "/tmp/hugo --minify",
]
packages = []

# Serve the built `public/` directory straight from the reverse proxy. A
# `static` worker needs no language runtime and no $PORT process — Hop3 points
# nginx at the directory. (For a custom server instead, declare a `web` worker
# that binds $PORT, e.g. `start = "npx serve public -l $PORT"` with
# packages = ["nodejs", "npm"].)
[run.workers]
static = "public"

[healthcheck]
path = "/"
timeout = 30
interval = 60
```

## Step 6: Initialize Git Repository

Update .gitignore:

```text
public/
resources/_gen/
.hugo_build.lock
```

```bash
git add . && git commit -m "Initial Hugo site"
```

```console
Initial Hugo site
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
hop3 deploy --app hop3-tuto-hugo
```

### Set Hostname

Configure the hostname for nginx proxy:

```bash
hop3 config set --app hop3-tuto-hugo HOST_NAME=hop3-tuto-hugo.$HOP3_TEST_DOMAIN
```

### Apply Configuration

Redeploy to apply the hostname configuration:

```bash
hop3 deploy --app hop3-tuto-hugo
```

Wait for the application to start:

```bash
sleep 5
```

### Verify Deployment

```bash
hop3 app status --app hop3-tuto-hugo
```

```console
hop3-tuto-hugo
```

```bash
curl -s http://hop3-tuto-hugo.$HOP3_TEST_DOMAIN/ | head -5
```

```console
html
```

View logs:

```bash
# View logs
hop3 app logs --app hop3-tuto-hugo

# Your app will be available at:
# http://hop3-tuto-hugo.your-hop3-server.example.com
```

### Managing Your Application

```bash
# Restart the application
hop3 app restart --app hop3-tuto-hugo

# View/set environment variables
hop3 config show --app hop3-tuto-hugo
hop3 config set --app hop3-tuto-hugo NEW_VAR=value

# Scale workers
hop3 ps scale --app hop3-tuto-hugo web=2
```

## Advanced Configuration

### Custom Domain

```toml
# hugo.toml
baseURL = 'https://myblog.example.com/'
```

```bash
hop3 domains add hop3-tuto-hugo myblog.example.com
```

### Multiple Environments

```bash
# Development
hugo server -D

# Staging
hugo --environment staging

# Production
hugo --minify
```

### Multilingual Site

```toml
# hugo.toml
defaultContentLanguage = 'en'

[languages]
  [languages.en]
    weight = 1
    title = "My Site"
  [languages.fr]
    weight = 2
    title = "Mon Site"
```

### Adding Search (Pagefind)

```bash
npm install pagefind
```

```toml
# In hop3.toml
[build]
before-build = ["hugo --minify", "npx pagefind --site public"]
```

### CI/CD with GitHub Actions

```yaml
# .github/workflows/deploy.yml
name: Deploy
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          submodules: true
      - name: Setup Hugo
        uses: peaceiris/actions-hugo@v2
      - name: Build
        run: hugo --minify
      - name: Deploy
        run: hop3 deploy
```

## Troubleshooting

### Theme Not Found
Ensure submodules are initialized:

```bash
git submodule update --init --recursive
```

### Build Errors
Check Hugo version compatibility:

```bash
hugo version
```

### Missing Content
Ensure `draft: false` in frontmatter for production.

## Example hop3.toml

```toml
[metadata]
id = "hop3-tuto-hugo"
version = "1.0.0"
title = "My Hugo Site"

[build]
before-build = [
    "curl -fsSL \"https://github.com/gohugoio/hugo/releases/download/v0.128.0/hugo_extended_0.128.0_linux-$(dpkg --print-architecture).tar.gz\" | tar -xz -C /tmp hugo",
    "/tmp/hugo --minify",
]
packages = []

[run.workers]
static = "public"

[healthcheck]
path = "/"
```

### Complete Procfile

```procfile
prebuild: curl -fsSL "https://github.com/gohugoio/hugo/releases/download/v0.128.0/hugo_extended_0.128.0_linux-$(dpkg --print-architecture).tar.gz" | tar -xz -C /tmp hugo && /tmp/hugo --minify
static: public
```
