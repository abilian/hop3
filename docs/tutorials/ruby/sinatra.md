---
tutorial:
  name: sinatra-hop3-tutorial
  teardown:
  - rm -rf hop3-tuto-sinatra 2>/dev/null || true
  - hop3 app:destroy hop3-tuto-sinatra -y 2>/dev/null || true
---

# Deploying Sinatra on Hop3

This guide walks you through deploying a Sinatra application on Hop3. Sinatra is a lightweight Ruby web framework perfect for small applications and APIs.

## Prerequisites

Before you begin, ensure you have:

1. **A Hop3 server** - Follow the [Installation Guide](../installation.md)
2. **The Hop3 CLI** - Installed on your local machine
3. **Ruby 3.2+** - Install via your package manager or [ruby-lang.org](https://www.ruby-lang.org/)
4. **Bundler** - Install with `gem install bundler`
5. **Git** - For version control and deployment

Verify your local setup:

```bash exec id=check-ruby
ruby -v
```

```output regex
ruby 3\.
```

```bash exec id=check-bundler
bundle -v
```

```output regex
[0-9]+\.[0-9]+
```

## Step 1: Create a New Sinatra Application

Create the project directory:

```bash exec id=create-project
mkdir hop3-tuto-sinatra && cd hop3-tuto-sinatra
```

```assert file-exists path=hop3-tuto-sinatra
```

Create the Gemfile:

```file path=hop3-tuto-sinatra/Gemfile
source 'https://rubygems.org'

gem 'sinatra', '~> 3.0'
gem 'puma'
gem 'json'
```

Install dependencies:

```bash exec id=bundle-install dir=hop3-tuto-sinatra timeout=120
bundle install
```

```output contains
Bundle complete!
```

## Step 2: Create the Application

```file path=hop3-tuto-sinatra/app.rb
require 'sinatra'
require 'json'

# Configuration
set :bind, '0.0.0.0'
set :port, ENV['PORT'] || 4567

# Disable Rack protection (nginx handles security)
# This prevents "Host not permitted" errors when behind a reverse proxy
disable :protection

# Welcome page
get '/' do
  content_type :html
  <<-HTML
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
        background: linear-gradient(135deg, #CC342D 0%, #9B1B1B 100%);
        color: white;
      }
      .container { text-align: center; padding: 2rem; }
      h1 { font-size: 3rem; margin-bottom: 1rem; }
      p { font-size: 1.25rem; opacity: 0.9; }
    </style>
  </head>
  <body>
    <div class="container">
      <h1>Hello from Hop3!</h1>
      <p>Your Sinatra application is running.</p>
      <p>Current time: #{Time.now.iso8601}</p>
    </div>
  </body>
  </html>
  HTML
end

# Health endpoints
get '/up' do
  'OK'
end

get '/health' do
  content_type :json
  {
    status: 'ok',
    timestamp: Time.now.iso8601,
    ruby_version: RUBY_VERSION
  }.to_json
end

get '/api/info' do
  content_type :json
  {
    name: 'hop3-tuto-sinatra',
    version: '1.0.0',
    ruby_version: RUBY_VERSION,
    sinatra_version: Sinatra::VERSION
  }.to_json
end

# Example API
items = {
  1 => { id: 1, name: 'Item 1', price: 9.99 },
  2 => { id: 2, name: 'Item 2', price: 19.99 }
}

get '/api/items' do
  content_type :json
  items.values.to_json
end

get '/api/items/:id' do
  item = items[params[:id].to_i]
  halt 404, { error: 'Not found' }.to_json unless item
  content_type :json
  item.to_json
end

post '/api/items' do
  data = JSON.parse(request.body.read)
  id = items.keys.max.to_i + 1
  items[id] = { id: id, name: data['name'], price: data['price'] }
  status 201
  content_type :json
  items[id].to_json
end
```

Create a config.ru for Rack:

```file path=hop3-tuto-sinatra/config.ru
require './app'
run Sinatra::Application
```

```assert file-exists path=hop3-tuto-sinatra/app.rb
```

## Step 3: Test the Application

Test that the application starts correctly (skipped in automated tests - local server tests are flaky):

```bash skip
bundle exec ruby app.rb &
sleep 3
curl -s http://localhost:4567/health
pkill -f "ruby app.rb" 2>/dev/null || true
```

Verify the project structure:

```bash exec id=verify-structure dir=hop3-tuto-sinatra
ls -la app.rb Gemfile config.ru
```

```output contains
app.rb
```

## Step 4: Create Deployment Configuration

```file path=hop3-tuto-sinatra/Procfile
web: bundle exec puma -C config/puma.rb
```

```file path=hop3-tuto-sinatra/config/puma.rb
port ENV.fetch('PORT', 4567)
workers ENV.fetch('WEB_CONCURRENCY', 2)
threads_count = ENV.fetch('RAILS_MAX_THREADS', 5)
threads threads_count, threads_count
preload_app!
```

```bash exec id=create-config-dir dir=hop3-tuto-sinatra
mkdir -p config
```

```file path=hop3-tuto-sinatra/hop3.toml
[metadata]
id = "hop3-tuto-sinatra"
version = "1.0.0"
title = "My Sinatra Application"

[build]
packages = ["ruby", "ruby-dev"]

[run]
start = "bundle exec puma -C config/puma.rb"

[port]
web = 4567

[healthcheck]
path = "/up"
timeout = 30
interval = 60
```

## Deploy to Hop3

The following steps require a Hop3 server.

### Initialize (First Time Only)

```bash skip
hop3 init --ssh root@your-server.example.com
```

### Set Environment Variables

```bash skip
hop3 config:set hop3-tuto-sinatra RACK_ENV=production
```

### Prepare for Deployment

Remove the Gemfile.lock to avoid bundler version conflicts between local and server:

```bash exec id=prep-deploy dir=hop3-tuto-sinatra
rm -f Gemfile.lock
```

### Deploy

Deploy the application (first deployment creates the app):

```bash exec id=deploy dir=hop3-tuto-sinatra timeout=120
hop3 deploy hop3-tuto-sinatra
```

```output contains
deployed successfully
```

### Set Hostname

Configure the hostname for nginx proxy:

```bash exec id=set-hostname timeout=30
hop3 config:set hop3-tuto-sinatra HOST_NAME=hop3-tuto-sinatra.$HOP3_TEST_DOMAIN
```

### Wait for Process Stop

Wait for the previous deployment to fully stop:

```bash exec id=wait-before-redeploy timeout=10
sleep 5
```

### Apply Configuration

Redeploy to apply the hostname configuration:

```bash exec id=redeploy dir=hop3-tuto-sinatra timeout=120
hop3 deploy hop3-tuto-sinatra
```

```output contains
deployed successfully
```

### Verify Deployment

```bash exec id=check-status timeout=30
hop3 app:status hop3-tuto-sinatra
```

```output contains
hop3-tuto-sinatra
```

```bash exec id=check-health timeout=30
curl -s http://hop3-tuto-sinatra.$HOP3_TEST_DOMAIN/up
```

```output contains
OK
```

View logs:

```bash skip
# View logs
hop3 app:logs hop3-tuto-sinatra

# Your app will be available at:
# http://hop3-tuto-sinatra.your-hop3-server.example.com
```

### Managing Your Application

```bash skip
# Restart the application
hop3 app:restart hop3-tuto-sinatra

# View/set environment variables
hop3 config:show hop3-tuto-sinatra
hop3 config:set hop3-tuto-sinatra NEW_VAR=value

# Scale workers
hop3 ps:scale hop3-tuto-sinatra web=2
```

## Example hop3.toml

```toml
[metadata]
id = "hop3-tuto-sinatra"
version = "1.0.0"

[build]
before-build = ["bundle install"]

[run]
start = "bundle exec puma -C config/puma.rb"

[port]
web = 4567

[healthcheck]
path = "/up"

[[provider]]
name = "postgres"
plan = "standard"
```
