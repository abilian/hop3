---
tutorial:
  name: eleventy-hop3-tutorial
  env:
    NODE_ENV: development
  teardown:
    - rm -rf hop3-tuto-eleventy 2>/dev/null || true
    - hop3 app destroy --app hop3-tuto-eleventy -y 2>/dev/null || true
---

# Deploying Eleventy on Hop3

This guide walks you through deploying an Eleventy (11ty) static site on Hop3. Eleventy is a simpler static site generator with zero-config by default.

## Prerequisites

Before you begin, ensure you have:

1. **A Hop3 server** - Follow the [Installation Guide](../../get-started/installation.md)
2. **The Hop3 CLI** - Installed on your local machine
3. **Node.js 18+** - Install from [nodejs.org](https://nodejs.org/)
4. **Git** - For version control and deployment

Verify your local setup:

```bash exec id=check-node
node -v
```

```output regex
v[0-9]+\.
```

## Step 1: Create a New Eleventy Site

```bash exec id=create-project
mkdir hop3-tuto-eleventy && cd hop3-tuto-eleventy && npm init -y
```

```output contains
package.json
```

Install Eleventy:

```bash exec id=install-eleventy dir=hop3-tuto-eleventy timeout=60
npm install @11ty/eleventy
```

```output contains
added
```

## Step 2: Create Site Structure

Create the source directory:

```bash exec id=create-dirs dir=hop3-tuto-eleventy
mkdir -p src/_includes src/_data src/posts
```

Create the base layout:

```file path=hop3-tuto-eleventy/src/_includes/base.njk
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }} | My Site</title>
    <style>
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
        }
        .hero {
            background: linear-gradient(135deg, #222 0%, #444 100%);
            color: white;
            padding: 3rem;
            border-radius: 8px;
            text-align: center;
            margin-bottom: 2rem;
        }
        .hero h1 { font-size: 2.5rem; margin-bottom: 0.5rem; }
    </style>
</head>
<body>
    <header>
        <nav>
            <a href="/">Home</a>
            <a href="/about/">About</a>
            <a href="/posts/">Blog</a>
        </nav>
    </header>
    <main>
        {{ content | safe }}
    </main>
    <footer>
        <p>&copy; {{ site.year }} My Eleventy Site on Hop3</p>
    </footer>
</body>
</html>
```

Create site data:

```file path=hop3-tuto-eleventy/src/_data/site.json
{
  "name": "My Eleventy Site",
  "description": "An Eleventy site deployed on Hop3",
  "year": "2024"
}
```

## Step 3: Create Content

Create the home page:

```file path=hop3-tuto-eleventy/src/index.njk
---
layout: base.njk
title: Home
---

<div class="hero">
    <h1>Hello from Hop3!</h1>
    <p>Your Eleventy site is running.</p>
</div>

<h2>Welcome</h2>
<p>This is an Eleventy static site deployed on Hop3.</p>

<h2>Recent Posts</h2>
<ul>
{%- for post in collections.posts | reverse | limit(5) %}
    <li><a href="{{ post.url }}">{{ post.data.title }}</a></li>
{%- endfor %}
</ul>
```

Create the about page:

```file path=hop3-tuto-eleventy/src/about.md
---
layout: base.njk
title: About
permalink: /about/
---

## About This Site

This Eleventy site demonstrates static site deployment on Hop3.

### Features

- **Simple** - Zero-config by default
- **Flexible** - Multiple template languages
- **Fast** - Minimal JavaScript, maximum performance
```

Create a blog post:

```file path=hop3-tuto-eleventy/src/posts/hello-world.md
---
layout: base.njk
title: Hello World
date: 2024-01-01
tags: posts
---

Welcome to our Eleventy site on Hop3!

## Getting Started

Eleventy supports multiple template languages:

- Markdown
- Nunjucks
- Liquid
- JavaScript

Create content in the `src/` directory and Eleventy will build your site.
```

Create a posts listing page:

```file path=hop3-tuto-eleventy/src/posts/index.njk
---
layout: base.njk
title: Blog
permalink: /posts/
---

<h1>Blog Posts</h1>

<ul>
{%- for post in collections.posts | reverse %}
    <li>
        <a href="{{ post.url }}">{{ post.data.title }}</a>
        <small>({{ post.date | date }})</small>
    </li>
{%- endfor %}
</ul>
```

## Step 4: Configure Eleventy

```file path=hop3-tuto-eleventy/eleventy.config.js
module.exports = function(eleventyConfig) {
  // Copy static assets
  eleventyConfig.addPassthroughCopy("src/assets");

  // Add date filter
  eleventyConfig.addFilter("date", (date, format) => {
    return new Date(date).toISOString().split('T')[0];
  });

  // Add limit filter
  eleventyConfig.addFilter("limit", (arr, limit) => arr.slice(0, limit));

  return {
    dir: {
      input: "src",
      output: "_site",
      includes: "_includes",
      data: "_data"
    },
    markdownTemplateEngine: "njk"
  };
};
```

Update package.json:

```file path=hop3-tuto-eleventy/package.json
{
  "name": "hop3-tuto-eleventy",
  "version": "1.0.0",
  "scripts": {
    "build": "eleventy",
    "start": "eleventy --serve",
    "serve": "npx serve _site"
  },
  "dependencies": {
    "@11ty/eleventy": "^2.0.0"
  }
}
```

## Step 5: Build and Test

Build the site:

```bash exec id=build-site dir=hop3-tuto-eleventy
npm run build
```

```output contains
Wrote
```

Verify the build:

```bash exec id=verify-build dir=hop3-tuto-eleventy
ls -la _site/
```

```output contains
index.html
```

Test the build:

```bash exec id=test-site dir=hop3-tuto-eleventy timeout=10
grep -o "Hello from Hop3" _site/index.html || cat _site/index.html | head -50
```

```output contains
Hello from Hop3
```

## Step 6: Create Deployment Configuration

```file path=hop3-tuto-eleventy/Procfile
prebuild: npm install && npm run build
web: npx serve _site -l $PORT
```

```file path=hop3-tuto-eleventy/hop3.toml
[metadata]
id = "hop3-tuto-eleventy"
version = "1.0.0"
title = "My Eleventy Site"

[build]
before-build = ["npm install", "npm run build"]
packages = ["nodejs", "npm"]

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

```bash exec id=deploy dir=hop3-tuto-eleventy timeout=120
hop3 deploy hop3-tuto-eleventy
```

```output contains
deployed successfully
```

### Set Hostname

Configure the hostname for nginx proxy:

```bash exec id=set-hostname timeout=30
hop3 config set --app hop3-tuto-eleventy HOST_NAME=hop3-tuto-eleventy.$HOP3_TEST_DOMAIN
```

### Wait for Process Stop

Wait for the previous deployment to fully stop:

```bash exec id=wait-before-redeploy timeout=10
sleep 5
```

### Apply Configuration

Redeploy to apply the hostname configuration:

```bash exec id=redeploy dir=hop3-tuto-eleventy timeout=120
hop3 deploy hop3-tuto-eleventy
```

```output contains
deployed successfully
```

### Verify Deployment

```bash exec id=check-status timeout=30
hop3 status --app hop3-tuto-eleventy
```

```output contains
hop3-tuto-eleventy
```

```bash exec id=check-health timeout=30
curl -s http://hop3-tuto-eleventy.$HOP3_TEST_DOMAIN/
```

```output contains
Hello from Hop3
```

### Managing Your Application

```bash skip
# Restart the application
hop3 restart --app hop3-tuto-eleventy

# View logs
hop3 logs --app hop3-tuto-eleventy

# View/set environment variables
hop3 config show --app hop3-tuto-eleventy
hop3 config set --app hop3-tuto-eleventy NEW_VAR=value

# Scale workers
hop3 ps scale --app hop3-tuto-eleventy web=2
```

## Advanced Configuration

### Custom Filters

```javascript
// eleventy.config.js
eleventyConfig.addFilter("readableDate", (date) => {
  return new Date(date).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  });
});
```

### Collections

```javascript
eleventyConfig.addCollection("featured", (collectionApi) => {
  return collectionApi.getFilteredByTag("featured").reverse();
});
```

### Image Optimization

```bash skip
npm install @11ty/eleventy-img
```

```javascript
const Image = require("@11ty/eleventy-img");

eleventyConfig.addShortcode("image", async function(src, alt) {
  let metadata = await Image(src, {
    widths: [300, 600],
    formats: ["webp", "jpeg"]
  });
  return Image.generateHTML(metadata, { alt });
});
```

### RSS Feed

```bash skip
npm install @11ty/eleventy-plugin-rss
```

```javascript
const pluginRss = require("@11ty/eleventy-plugin-rss");
eleventyConfig.addPlugin(pluginRss);
```

## Troubleshooting

### Build Errors
Check for template syntax errors in Nunjucks files.

### Missing Pages
Ensure frontmatter is valid YAML.

### CSS Not Loading
Add passthrough copy for assets.

## Example hop3.toml

```toml
[metadata]
id = "hop3-tuto-eleventy"
version = "1.0.0"
title = "My Eleventy Site"

[build]
before-build = ["npm install", "npm run build"]
packages = ["nodejs", "npm"]

[run]
start = "npx serve _site -l $PORT -s"

[port]
web = 3000

[healthcheck]
path = "/"
```
