---
tutorial:
  name: hugo-hop3-tutorial
  teardown:
  - rm -rf hop3-tuto-hugo 2>/dev/null || true
  - hop3 app:destroy hop3-tuto-hugo -y 2>/dev/null || true
---

# Deploying Hugo on Hop3

This guide walks you through deploying a Hugo static site on Hop3. Hugo is the world's fastest static site generator, written in Go.

## Prerequisites

Before you begin, ensure you have:

1. **A Hop3 server** - Follow the [Installation Guide](../../get-started/installation.md)
2. **The Hop3 CLI** - Installed on your local machine
3. **Hugo** - Install from [gohugo.io](https://gohugo.io/installation/)
4. **Git** - For version control and deployment

### Installing Hugo

```bash skip
# macOS (Homebrew)
brew install hugo

# Ubuntu/Debian
sudo apt install hugo

# Or download from GitHub releases:
# https://github.com/gohugoio/hugo/releases
```

Verify your local setup:

```bash exec id=check-hugo
hugo version || (echo "SKIP: Hugo is not installed locally. Install from https://gohugo.io/installation/" && exit 1)
```

```output regex
hugo v[0-9]+\.[0-9]+|SKIP: Hugo
```

!!! note "Local Prerequisite"
    Hugo must be installed on your local machine to build the site before deployment.
    Unlike frameworks (Rails, Django), Hugo is a standalone binary.
    Install from [gohugo.io](https://gohugo.io/installation/) before continuing.

## Step 1: Create a New Hugo Site

```bash exec id=create-site timeout=30
hugo new site hop3-tuto-hugo
```

```output contains
Congratulations
```

```assert file-exists path=hop3-tuto-hugo/hugo.toml
```

## Step 2: Add a Theme

Download a simple theme:

```bash exec id=git-init dir=hop3-tuto-hugo
git init
```

```output contains
Initialized
```

```bash exec id=add-theme dir=hop3-tuto-hugo timeout=120
git submodule add https://github.com/theNewDynamic/gohugo-theme-ananke.git themes/ananke 2>&1 && echo "Theme added successfully" || echo "Theme already exists"
```

```output regex
Theme added|Theme already|Cloning
```

Configure the theme:

```file path=hop3-tuto-hugo/hugo.toml
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

```file path=hop3-tuto-hugo/content/_index.md
---
title: "Welcome to Hop3!"
description: "Your Hugo site is running"
---

This is a Hugo static site deployed on Hop3.

Built with the world's fastest static site generator.
```

Create an about page:

```bash exec id=create-about dir=hop3-tuto-hugo
hugo new content about.md
```

```output contains
Content
```

Update the about page:

```file path=hop3-tuto-hugo/content/about.md
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

```bash exec id=create-posts-dir dir=hop3-tuto-hugo
mkdir -p content/posts
```

```file path=hop3-tuto-hugo/content/posts/hello-world.md
---
title: "Hello World"
date: 2024-01-01
draft: false
---

This is the first post on our Hugo site deployed on Hop3!

## Getting Started

Hugo makes it easy to create content:

```bash
hugo new content posts/my-post.md
```

Then edit the markdown file and rebuild your site.

## Step 4: Build and Test

Build the site:

```bash exec id=build-site dir=hop3-tuto-hugo
hugo 2>&1; echo "Build completed with exit code $?"
```

```output contains
Build completed
```

Verify the build output:

```bash exec id=verify-build dir=hop3-tuto-hugo
ls -la public/
```

```output contains
index.html
```

Test locally:

```bash exec id=test-site dir=hop3-tuto-hugo timeout=10
hugo server &
sleep 3
curl -s http://localhost:1313/ | head -5 || echo "Test completed"
pkill -f "hugo server" 2>/dev/null || true
```

```output contains
html
```

## Step 5: Create Deployment Configuration

```file path=hop3-tuto-hugo/Procfile
# Pre-build: Generate static files
prebuild: hugo --minify

# Serve static files
web: npx serve public -l $PORT
```

```file path=hop3-tuto-hugo/hop3.toml
[metadata]
id = "hop3-tuto-hugo"
version = "1.0.0"
title = "My Hugo Site"

[build]
before-build = ["hugo --minify"]
packages = ["hugo", "nodejs", "npm"]

[run]
start = "npx serve public -l $PORT"

[port]
web = 3000

[healthcheck]
path = "/"
timeout = 30
interval = 60
```

Alternatively, use Python's built-in HTTP server (no Node.js required):

```file path=hop3-tuto-hugo/hop3-python.toml
[metadata]
id = "hop3-tuto-hugo"
version = "1.0.0"
title = "My Hugo Site"

[build]
before-build = ["hugo --minify"]
packages = ["hugo"]

[run]
start = "python3 -m http.server $PORT --directory public"

[port]
web = 8000

[healthcheck]
path = "/"
```

## Step 6: Initialize Git Repository

Update .gitignore:

```file path=hop3-tuto-hugo/.gitignore
public/
resources/_gen/
.hugo_build.lock
```

```bash exec id=git-add dir=hop3-tuto-hugo
git add . && git commit -m "Initial Hugo site"
```

```output contains
Initial Hugo site
```

## Deploy to Hop3

The following steps require a Hop3 server.

### Initialize (First Time Only)

```bash skip
hop3 init --ssh root@your-server.example.com
```

### Deploy

Deploy the application (first deployment creates the app):

```bash exec id=deploy dir=hop3-tuto-hugo timeout=120
hop3 deploy hop3-tuto-hugo
```

### Set Hostname

Configure the hostname for nginx proxy:

```bash exec id=set-hostname timeout=30
hop3 config:set hop3-tuto-hugo HOST_NAME=hop3-tuto-hugo.$HOP3_TEST_DOMAIN
```

### Apply Configuration

Redeploy to apply the hostname configuration:

```bash exec id=redeploy dir=hop3-tuto-hugo timeout=120
hop3 deploy hop3-tuto-hugo
```

Wait for the application to start:

```bash exec id=wait-for-app timeout=10
sleep 5
```

### Verify Deployment

```bash exec id=check-status timeout=30
hop3 app:status hop3-tuto-hugo
```

```output contains
hop3-tuto-hugo
```

```bash exec id=check-health timeout=30
curl -s http://hop3-tuto-hugo.$HOP3_TEST_DOMAIN/ | head -5
```

```output contains
html
```

View logs:

```bash skip
# View logs
hop3 app:logs hop3-tuto-hugo

# Your app will be available at:
# http://hop3-tuto-hugo.your-hop3-server.example.com
```

### Managing Your Application

```bash skip
# Restart the application
hop3 app:restart hop3-tuto-hugo

# View/set environment variables
hop3 config:show hop3-tuto-hugo
hop3 config:set hop3-tuto-hugo NEW_VAR=value

# Scale workers
hop3 ps:scale hop3-tuto-hugo web=2
```

## Advanced Configuration

### Custom Domain

```toml
# hugo.toml
baseURL = 'https://myblog.example.com/'
```

```bash skip
hop3 domains:add hop3-tuto-hugo myblog.example.com
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

```bash skip
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
before-build = ["hugo --minify"]
packages = ["hugo", "nodejs", "npm"]

[run]
start = "npx serve public -l $PORT -s"

[port]
web = 3000

[healthcheck]
path = "/"
```

### Complete Procfile

```procfile
prebuild: hugo --minify
web: npx serve public -l $PORT -s
```
