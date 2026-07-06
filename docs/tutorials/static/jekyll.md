---
tutorial:
  name: jekyll-hop3-tutorial
  teardown:
    - rm -rf hop3-tuto-jekyll 2>/dev/null || true
    - hop3 app destroy --app hop3-tuto-jekyll -y 2>/dev/null || true
---

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

```bash skip
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

```bash exec id=check-ruby
ruby -v
```

```output regex
ruby [3-9]\.
```

```bash exec id=check-jekyll
jekyll -v 2>&1 || echo "Jekyll version check"
```

```output regex
jekyll [0-9]+\.[0-9]+|Jekyll version check
```

## Step 1: Install Jekyll and Create Site

Install Jekyll and Bundler if not already installed:

```bash exec id=install-jekyll timeout=120
gem install jekyll bundler --no-document 2>&1 | tail -5 || echo "Jekyll installation completed"
```

```output regex
jekyll|Successfully installed|already activated|gems installed
```

Add gem binary path to PATH and verify Jekyll is available:

```bash exec id=check-jekyll-available
export PATH="$(ruby -e 'puts Gem.user_dir')/bin:$PATH" && jekyll -v
```

```output regex
jekyll [0-9]+\.
```

Create a new Jekyll site:

```bash exec id=create-site timeout=60
export PATH="$(ruby -e 'puts Gem.user_dir')/bin:$PATH" && jekyll new hop3-tuto-jekyll
```

```output contains
New jekyll site installed
```

```assert file-exists path=hop3-tuto-jekyll/Gemfile
```

Install dependencies:

```bash exec id=bundle-install dir=hop3-tuto-jekyll timeout=120
bundle install
```

```output contains
Bundle complete!
```

## Step 2: Configure the Site

Update `_config.yml`:

```file path=hop3-tuto-jekyll/_config.yml
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

```file path=hop3-tuto-jekyll/index.markdown
---
layout: home
title: Welcome to Hop3!
---

Your Jekyll site is running on Hop3.

Jekyll is a simple, blog-aware static site generator perfect for personal projects, documentation, and blogs.
```

Create an about page:

```file path=hop3-tuto-jekyll/about.markdown
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

```file path=hop3-tuto-jekyll/_posts/2024-01-01-hello-world.markdown
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

```bash exec id=build-site dir=hop3-tuto-jekyll
bundle exec jekyll build
```

```output contains
done in
```

Verify the build:

```bash exec id=verify-build dir=hop3-tuto-jekyll
ls -la _site/
```

```output contains
index.html
```

Test locally:

```bash exec id=test-site dir=hop3-tuto-jekyll timeout=15
bundle exec jekyll serve &
APP_PID=$!
sleep 5
curl -s http://localhost:4000/ | head -5 || echo "Test completed"
kill "$APP_PID" 2>/dev/null || true
```

```output contains
html
```

## Step 5: Create Deployment Configuration

```file path=hop3-tuto-jekyll/Procfile
# Pre-build: Install gems and build site
prebuild: bundle install && bundle exec jekyll build

# Serve static files
web: npx serve _site -l $PORT
```

```file path=hop3-tuto-jekyll/hop3.toml
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

```bash skip
hop3 init --ssh root@your-server.example.com
```

### Deploy

Deploy the application (first deployment creates the app):

```bash exec id=deploy dir=hop3-tuto-jekyll timeout=120
hop3 deploy --app hop3-tuto-jekyll
```

```output contains
deployed successfully
```

### Set Hostname

Configure the hostname for nginx proxy:

```bash exec id=set-hostname timeout=30
hop3 env set --app hop3-tuto-jekyll HOST_NAME=hop3-tuto-jekyll.$HOP3_TEST_DOMAIN
```

### Apply Configuration

Redeploy to apply the hostname configuration:

```bash exec id=redeploy dir=hop3-tuto-jekyll timeout=120
hop3 deploy --app hop3-tuto-jekyll
```

```output contains
deployed successfully
```

### Verify Deployment

```bash exec id=check-status timeout=30
hop3 app status --app hop3-tuto-jekyll
```

```output contains
hop3-tuto-jekyll
```

```bash exec id=check-health timeout=30
curl -s http://hop3-tuto-jekyll.$HOP3_TEST_DOMAIN/ | head -10
```

```output contains
html
```

### Managing Your Application

```bash skip
# Restart the application
hop3 app restart --app hop3-tuto-jekyll

# View logs
hop3 app logs --app hop3-tuto-jekyll

# View/set environment variables
hop3 env show --app hop3-tuto-jekyll
hop3 env set --app hop3-tuto-jekyll NEW_VAR=value

# Scale workers
hop3 ps scale --app hop3-tuto-jekyll web=2
```

## Advanced Configuration

### Custom Theme

```bash skip
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
