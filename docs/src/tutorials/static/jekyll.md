# Deploying Jekyll on Hop3

> This guide deploys with the **build-on-server** strategy — Hop3 runs the generator on each deploy. For the concepts and the alternative (build your site at the source and deploy the assets), see the [Static Sites overview](index.md).

This guide walks you through deploying a Jekyll static site on Hop3. Jekyll is a simple, blog-aware static site generator, powering GitHub Pages.

## Prerequisites

Before you begin, ensure you have:

1. **A Hop3 server** - Follow the [Installation Guide](../../get-started/server-setup.md)
2. **The Hop3 CLI** - Installed on your local machine
3. **Ruby 3.0+** - Install via your package manager
4. **Jekyll** - Install with `gem install jekyll bundler`
5. **Git** - For version control and deployment

### Installing Ruby and Jekyll

```bash
# macOS (Homebrew)
brew install ruby
echo 'export PATH="/opt/homebrew/opt/ruby/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
gem install jekyll bundler

# Ubuntu/Debian
sudo apt install ruby ruby-dev build-essential
gem install jekyll bundler

# Verify installation
jekyll -v
```

Verify your local setup:

```bash
ruby -v
```

```bash
jekyll -v 2>&1 || echo "Jekyll version check"
```

## Step 1: Install Jekyll and Create Site

Install Jekyll and Bundler if not already installed:

```bash
gem install jekyll bundler --no-document 2>&1 | tail -5 || echo "Jekyll installation completed"
```

Add gem binary path to PATH and verify Jekyll is available:

```bash
export PATH="$(ruby -e 'puts Gem.user_dir')/bin:$PATH" && jekyll -v
```

Create a new Jekyll site:

```bash
export PATH="$(ruby -e 'puts Gem.user_dir')/bin:$PATH" && jekyll new hop3-tuto-jekyll
```

```console
New jekyll site installed
```

Install dependencies:

```bash
bundle install
```

```console
Bundle complete!
```

## Step 2: Configure the Site

Update `_config.yml`:

```yaml
title: My Jekyll Site
description: A Jekyll site deployed on Hop3
baseurl: ""
url: "https://hop3-tuto-jekyll.example.com"

# Build settings
markdown: kramdown
theme: minima

# Exclude from build
exclude:
  - Gemfile
  - Gemfile.lock
  - node_modules
  - vendor

# Plugins
plugins:
  - jekyll-feed
  - jekyll-seo-tag
```

## Step 3: Create Content

Update the home page:

```text
---
layout: home
title: Welcome to Hop3!
---

Your Jekyll site is running on Hop3.

Jekyll is a simple, blog-aware static site generator perfect for personal projects, documentation, and blogs.
```

Create an about page:

```text
---
layout: page
title: About
permalink: /about/
---

## About This Site

This Jekyll site demonstrates static site deployment on Hop3.

### Features

- **Simple** - Write in Markdown
- **Blog-aware** - Built-in support for posts
- **Customizable** - Liquid templates and themes
```

Create a blog post:

```text
---
layout: post
title: "Hello World"
date: 2024-01-01 12:00:00 -0000
categories: blog
---

Welcome to our Jekyll site on Hop3!

## Getting Started

Create new posts in the `_posts` directory:

```
_posts/YYYY-MM-DD-title.markdown
```

Jekyll will automatically process them into your site.
```

## Step 4: Build and Test

Build the site:

```bash
bundle exec jekyll build
```

```console
done in
```

Verify the build:

```bash
ls -la _site/
```

```console
index.html
```

Test locally:

```bash
bundle exec jekyll serve &
APP_PID=$!
sleep 5
curl -s http://localhost:4000/ | head -5 || echo "Test completed"
kill "$APP_PID" 2>/dev/null || true
```

```console
html
```

## Step 5: Create Deployment Configuration

```procfile
# Pre-build: Install gems and build site
prebuild: bundle install && bundle exec jekyll build

# Serve static files
web: npx serve _site -l $PORT
```

```toml
[metadata]
id = "hop3-tuto-jekyll"
version = "1.0.0"
title = "Hop3 Tutorial - Jekyll"

[build]
before-build = ["bundle install", "bundle exec jekyll build"]
packages = ["ruby", "ruby-dev", "nodejs", "npm"]

[run]
start = "npx serve _site -l $PORT"

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
hop3 deploy hop3-tuto-jekyll
```

```console
deployed successfully
```

### Set Hostname

Configure the hostname for nginx proxy:

```bash
hop3 config set --app hop3-tuto-jekyll HOST_NAME=hop3-tuto-jekyll.$HOP3_TEST_DOMAIN
```

### Apply Configuration

Redeploy to apply the hostname configuration:

```bash
hop3 deploy hop3-tuto-jekyll
```

```console
deployed successfully
```

### Verify Deployment

```bash
hop3 app status --app hop3-tuto-jekyll
```

```console
hop3-tuto-jekyll
```

```bash
curl -s http://hop3-tuto-jekyll.$HOP3_TEST_DOMAIN/ | head -10
```

```console
html
```

### Managing Your Application

```bash
# Restart the application
hop3 app restart --app hop3-tuto-jekyll

# View logs
hop3 app logs --app hop3-tuto-jekyll

# View/set environment variables
hop3 config show --app hop3-tuto-jekyll
hop3 config set --app hop3-tuto-jekyll NEW_VAR=value

# Scale workers
hop3 ps scale --app hop3-tuto-jekyll web=2
```

## Advanced Configuration

### Custom Theme

```bash
# Use a gem-based theme
bundle add just-the-docs

# Or use remote theme (GitHub Pages compatible)
# In _config.yml:
remote_theme: pmarsceill/just-the-docs
```

### Collections

```yaml
# _config.yml
collections:
  docs:
    output: true
    permalink: /docs/:path/
```

### Pagination

```yaml
# _config.yml
plugins:
  - jekyll-paginate

paginate: 10
paginate_path: "/blog/page:num/"
```

### Drafts

```bash
# Create drafts in _drafts/
# Build with drafts:
bundle exec jekyll build --drafts
```

### Multilingual

```yaml
# _config.yml
defaults:
  - scope:
      path: ""
      type: "pages"
    values:
      lang: "en"
```

### Adding Search (Lunr.js)

```yaml
# _config.yml
plugins:
  - jekyll-lunr-js-search
```

## Troubleshooting

### Gem Errors
Update bundler:

```bash
gem update bundler
bundle update
```

### Build Failures
Check Ruby version:

```bash
ruby -v
# May need: rbenv install 3.2.0
```

### Missing Posts
Ensure date in filename matches frontmatter.

## Example hop3.toml

```toml
[metadata]
id = "hop3-tuto-jekyll"
version = "1.0.0"
title = "My Jekyll Site"

[build]
before-build = ["bundle install", "JEKYLL_ENV=production bundle exec jekyll build"]
packages = ["ruby", "ruby-dev", "nodejs", "npm"]

[run]
start = "npx serve _site -l $PORT -s"

[port]
web = 3000

[healthcheck]
path = "/"
```

### Complete Procfile

```procfile
prebuild: bundle install && JEKYLL_ENV=production bundle exec jekyll build
web: npx serve _site -l $PORT -s
```
