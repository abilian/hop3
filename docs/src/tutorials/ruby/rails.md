# Deploying Ruby on Rails on Hop3

This guide walks you through deploying a Ruby on Rails 8 application on Hop3. By the end, you'll have a live, production-ready Rails application running on your own infrastructure.

## Prerequisites

Before you begin, ensure you have:

1. **A Hop3 server** - Follow the [Installation Guide](../../get-started/installation.md) if you haven't set one up yet
2. **The Hop3 CLI** - Installed on your local machine
3. **Ruby 3.2+** and **Rails 8+** - Install with `gem install rails`
4. **PostgreSQL** - Installed locally for development
5. **Git** - For version control and deployment

### Installing Ruby and Rails

```bash
# macOS (Homebrew)
brew install ruby postgresql
echo 'export PATH="/opt/homebrew/opt/ruby/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
gem install rails

# Ubuntu/Debian
sudo apt install ruby ruby-dev build-essential libpq-dev postgresql
gem install rails

# Verify installation
rails -v
```

Verify your local setup:

```bash
ruby -v
```

```console
ruby 3.
```

```bash
rails -v 2>&1 || echo "Rails not installed - will install"
```

## Step 1: Install Rails and Create Application

Install Rails if not already installed:

```bash
gem install rails --no-document 2>&1 | tail -5 || echo "Rails installation completed"
```

Verify Rails is available:

```bash
rails -v
```

Create a new Rails application. For production deployment, you should use PostgreSQL (`--database=postgresql`), but for this tutorial we'll use SQLite locally and configure PostgreSQL for production:

```bash
rails new hop3-tuto-rails --skip-git --skip-docker --skip-action-mailer --skip-action-mailbox --skip-action-text --skip-active-job --skip-active-storage --skip-action-cable --skip-hotwire --skip-jbuilder --skip-test --skip-system-test --skip-thruster --skip-rubocop --skip-brakeman --skip-ci --skip-kamal
```

```console
create
```

Install the dependencies:

```bash
bundle install
```

```console
Bundle complete!
```

Move into the application directory and verify the structure:

```bash
ls -la
```

```console
Gemfile
```

```console
config
```

```console
app
```

## Step 2: Create a Welcome Page

Rails 8 doesn't include a default welcome page in production. Let's create one:

```bash
bin/rails generate controller welcome index
```

```console
create  app/controllers/welcome_controller.rb
```

Create the welcome view:

```text
<h1>Hello from Hop3!</h1>
<p>Your Rails application is running.</p>
<p>Current time: <%= Time.current %></p>
```

Set the root route in `config/routes.rb`:

```ruby
Rails.application.routes.draw do
  root "welcome#index"

  # Health check endpoint for Hop3
  get "/up", to: ->(env) { [200, {}, ["OK"]] }
  get "/health", to: "health#show"
end
```

Create a health check controller:

```ruby
class HealthController < ApplicationController
  def show
    ActiveRecord::Base.connection.execute("SELECT 1")
    render json: { status: "ok", database: "connected" }
  rescue StandardError => e
    render json: { status: "error", message: e.message }, status: :service_unavailable
  end
end
```

## Step 3: Configure for Production

### Configure the Database for Production

Update `config/database.yml` to use `DATABASE_URL` in production:

```yaml
default: &default
  adapter: sqlite3
  pool: <%= ENV.fetch("RAILS_MAX_THREADS", 5) %>
  timeout: 5000

development:
  <<: *default
  database: storage/development.sqlite3

test:
  <<: *default
  database: storage/test.sqlite3

production:
  adapter: postgresql
  encoding: unicode
  pool: <%= ENV.fetch("RAILS_MAX_THREADS", 5) %>
  url: <%= ENV["DATABASE_URL"] %>
```

!!! tip "Dev/Prod Parity"
    For real projects, use PostgreSQL locally during development to avoid subtle bugs from database differences. Install PostgreSQL and use `rails new myapp --database=postgresql`.

### Configure Environment-Based Secrets

Update `config/environments/production.rb` to use environment variables:

```bash
cat >> config/environments/production.rb << 'RUBY'

# Use environment variable for secret key base
config.secret_key_base = ENV["SECRET_KEY_BASE"] if ENV["SECRET_KEY_BASE"].present?

# Ensure logs go to stdout for Hop3
if ENV["RAILS_LOG_TO_STDOUT"].present?
  logger = ActiveSupport::Logger.new($stdout)
  logger.formatter = config.log_formatter
  config.logger = ActiveSupport::TaggedLogging.new(logger)
end
RUBY
```

### Create Static Directories

```bash
mkdir -p storage tmp/pids tmp/cache tmp/sockets log
```

## Step 4: Create Deployment Configuration

### Create a Procfile

Create a `Procfile` in your project root:

```procfile
# Pre-build: Compile assets (bundle install is handled by Ruby toolchain)
prebuild: bin/rails assets:precompile

# Pre-run: Run migrations before starting
prerun: bin/rails db:migrate

# Main web process
web: bundle exec puma -C config/puma.rb
```

### Create hop3.toml

Create a `hop3.toml` for advanced configuration:

```toml
[metadata]
id = "hop3-tuto-rails"
version = "1.0.0"
title = "My Rails Application"

[build]
before-build = ["bin/rails assets:precompile"]
packages = ["postgresql-dev", "nodejs"]

[run]
start = "bundle exec puma -C config/puma.rb"
before-run = "bin/rails db:migrate"

[env]
RAILS_ENV = "production"
RAILS_LOG_TO_STDOUT = "true"
RAILS_SERVE_STATIC_FILES = "true"

[port]
web = 3000

[healthcheck]
path = "/up"
timeout = 30
interval = 60

[[provider]]
name = "postgres"
plan = "standard"
```

## Step 5: Configure Puma

Update `config/puma.rb` for production:

```ruby
# Puma configuration for Hop3

# Use the PORT environment variable (Hop3 sets this automatically)
port ENV.fetch("PORT", 3000)

# Configure worker count based on available resources
workers ENV.fetch("WEB_CONCURRENCY", 2)

# Configure threads per worker
max_threads = ENV.fetch("RAILS_MAX_THREADS", 5)
min_threads = ENV.fetch("RAILS_MIN_THREADS") { max_threads }
threads min_threads, max_threads

# Specifies the `environment` that Puma will run in
environment ENV.fetch("RAILS_ENV", "development")

# Specifies the `pidfile` that Puma will use
pidfile ENV.fetch("PIDFILE", "tmp/pids/server.pid")

# Preload the application for better memory usage with workers
preload_app!

# Allow Puma to be restarted by `bin/rails restart`
plugin :tmp_restart

on_worker_boot do
  ActiveRecord::Base.establish_connection if defined?(ActiveRecord)
end
```

## Step 6: Verify the Application Works

Create the database and run migrations:

```bash
bin/rails db:create db:migrate
```

Run Rails system checks:

```bash
bin/rails runner "puts 'Rails is working!'"
```

```console
Rails is working!
```

Verify the project structure is complete:

```bash
ls -la
```

```console
Procfile
```

```console
hop3.toml
```

```console
Gemfile
```

## Step 7: Initialize Git Repository

Create a `.gitignore` file:

```text
# Ignore bundler config
/.bundle

# Ignore all logfiles and tempfiles
/log/*
/tmp/*
!/log/.keep
!/tmp/.keep

# Ignore pidfiles
/tmp/pids/*
!/tmp/pids/.keep

# Ignore storage
/storage/*
!/storage/.keep

# Ignore master key for decrypting credentials and more
/config/master.key

# Ignore node_modules
/node_modules

# Ignore precompiled assets
/public/assets

# Ignore OS files
.DS_Store
```

Initialize the repository:

```bash
git init
```

```console
Initialized empty Git repository
```

```bash
git add .
```

```bash
git commit -m "Initial Rails 8 application"
```

```console
Initial Rails 8 application
```

## Step 8: Deploy to Hop3

The following steps require a Hop3 server. Set the `HOP3_SERVER` environment variable to your server address before running these commands.

### Configure the CLI

If this is your first deployment, initialize Hop3:

```bash
hop3 init --ssh root@your-server.example.com
```

### Create and Attach a Database

```bash
hop3 addons create postgres myapp-db
hop3 addons attach hop3-tuto-rails myapp-db
```

### Set Environment Variables

```bash
# Generate and set the secret key
hop3 config set --app hop3-tuto-rails SECRET_KEY_BASE=$(bin/rails secret)

# Set Rails environment variables
hop3 config set --app hop3-tuto-rails RAILS_ENV=production
hop3 config set --app hop3-tuto-rails RAILS_LOG_TO_STDOUT=true
hop3 config set --app hop3-tuto-rails RAILS_SERVE_STATIC_FILES=true
```

### Deploy

Deploy the application (first deployment creates the app):

```bash
hop3 deploy hop3-tuto-rails
```

### Set Hostname

Configure the hostname for nginx proxy:

```bash
hop3 config set --app hop3-tuto-rails HOST_NAME=hop3-tuto-rails.$HOP3_TEST_DOMAIN
```

### Apply Configuration

Redeploy to apply the hostname configuration:

```bash
hop3 deploy hop3-tuto-rails
```

Wait for the application to start:

```bash
sleep 5
```

You'll see output showing:
- Code upload
- Dependency installation (`bundle install`)
- Asset compilation
- Database migration
- Application startup

## Step 9: Verify Deployment

Check your application status:

```bash
hop3 status --app hop3-tuto-rails
```

```console
hop3-tuto-rails
```

```bash
curl -s http://hop3-tuto-rails.$HOP3_TEST_DOMAIN/up
```

```console
OK
```

View logs:

```bash
hop3 logs --app hop3-tuto-rails
```

Open your application:

```bash
# Your app will be available at:
# http://hop3-tuto-rails.your-hop3-server.example.com
```

## Managing Your Application

### Run Database Migrations

Migrations run automatically during deployment via `prerun`. To run manually:

```bash
hop3 run hop3-tuto-rails bin/rails db:migrate
```

### Run Rails Console

```bash
hop3 run hop3-tuto-rails bin/rails console
```

### Run Rake Tasks

```bash
hop3 run hop3-tuto-rails bin/rails db:seed
hop3 run hop3-tuto-rails bin/rake custom:task
```

### View and Manage Environment Variables

```bash
# List all variables
hop3 config show --app hop3-tuto-rails

# Set a variable
hop3 config set --app hop3-tuto-rails NEW_VARIABLE=value

# Remove a variable
hop3 config unset --app hop3-tuto-rails OLD_VARIABLE

# Restart to apply changes
hop3 restart --app hop3-tuto-rails
```

### Scaling

```bash
# Check current processes
hop3 ps hop3-tuto-rails

# Scale web workers
hop3-tuto-rails web=2
```

## Advanced Configuration

### Background Jobs with Sidekiq

Add Sidekiq to your `Gemfile`:

```ruby
gem "sidekiq"
```

Configure Redis in `config/initializers/sidekiq.rb`:

```ruby
Sidekiq.configure_server do |config|
  config.redis = { url: ENV.fetch("REDIS_URL", "redis://localhost:6379/0") }
end

Sidekiq.configure_client do |config|
  config.redis = { url: ENV.fetch("REDIS_URL", "redis://localhost:6379/0") }
end
```

Add a worker process to your `Procfile`:

```procfile
web: bundle exec puma -C config/puma.rb
worker: bundle exec sidekiq -C config/sidekiq.yml
```

Attach a Redis addon:

```bash
hop3 addons create redis myapp-redis
hop3 addons attach hop3-tuto-rails myapp-redis
```

### Active Storage with Local Storage

For file uploads using local storage, configure `config/storage.yml`:

```yaml
local:
  service: Disk
  root: <%= Rails.root.join("storage") %>

production:
  service: Disk
  root: <%= ENV.fetch("STORAGE_PATH", Rails.root.join("storage")) %>
```

Set the storage path:

```bash
hop3 config set --app hop3-tuto-rails STORAGE_PATH=/var/hop3/apps/myapp/data/storage
```

### Health Checks

Rails 8 includes a built-in health check endpoint at `/up`. Configure it in `hop3.toml`:

```toml
[healthcheck]
path = "/up"
timeout = 30
interval = 60
```

For a custom health check that verifies database connectivity:

```ruby
# config/routes.rb
get "/health", to: "health#show"

# app/controllers/health_controller.rb
class HealthController < ApplicationController
  def show
    ActiveRecord::Base.connection.execute("SELECT 1")
    render json: { status: "ok", database: "connected" }
  rescue StandardError => e
    render json: { status: "error", message: e.message }, status: :service_unavailable
  end
end
```

### Action Cable (WebSockets)

For real-time features, configure Action Cable in `config/cable.yml`:

```yaml
production:
  adapter: redis
  url: <%= ENV.fetch("REDIS_URL") { "redis://localhost:6379/1" } %>
  channel_prefix: myapp_production
```

Ensure you have Redis attached and set the allowed origins:

```ruby
# config/environments/production.rb
config.action_cable.allowed_request_origins = [
  "https://myapp.your-hop3-server.example.com"
]
```

### Solid Queue (Rails 8 Default)

Rails 8 includes Solid Queue for background jobs using the database. If you prefer this over Sidekiq:

```ruby
# config/environments/production.rb
config.active_job.queue_adapter = :solid_queue
```

Add to your `Procfile`:

```procfile
worker: bin/rails solid_queue:start
```

## Backup and Restore

### Create a Backup

Before major changes, always backup:

```bash
hop3 backup create hop3-tuto-rails
```

This backs up:
- Application source code
- Database (PostgreSQL dump)
- Environment variables
- Uploaded files (Active Storage)

### Restore from Backup

```bash
hop3 backup list myapp
hop3 backup restore <backup-id>
hop3 restart --app hop3-tuto-rails
```

## Troubleshooting

### Application Won't Start

Check the logs for errors:

```bash
hop3 logs --app hop3-tuto-rails --tail
```

Common issues:
- **Missing SECRET_KEY_BASE**: Set it with `hop3 config set`
- **Database not connected**: Ensure the addon is attached
- **Asset compilation failed**: Check for JavaScript/CSS errors

### Database Connection Issues

Verify the database is attached:

```bash
hop3 config show --app hop3-tuto-rails | grep DATABASE
```

Test the connection:

```bash
hop3 run hop3-tuto-rails bin/rails db:version
```

### Missing Gems in Production

Ensure all required gems are in the default group (not `:development` or `:test`):

```ruby
# Wrong - won't be installed in production
group :development do
  gem "some_gem_you_need_everywhere"
end

# Correct - installed in all environments
gem "some_gem_you_need_everywhere"
```

### Asset Pipeline Issues

If assets aren't loading:

1. Ensure `RAILS_SERVE_STATIC_FILES=true` is set
2. Check that `assets:precompile` runs during build
3. Verify the asset paths in your views

### Slow Application Startup

For faster boot times:
- Use `bootsnap` (included by default in Rails 8)
- Preload the application in Puma (`preload_app!`)
- Consider using `jemalloc` for better memory management

## Migrating from SQLite

If your existing Rails app uses SQLite:

1. Replace the gem in `Gemfile`:
   ```ruby
   # Remove: gem "sqlite3"
   gem "pg"
   ```

2. Run `bundle install`

3. Update `config/database.yml`:
   ```yaml
   default: &default
     adapter: postgresql
     encoding: unicode
     pool: <%= ENV.fetch("RAILS_MAX_THREADS", 5) %>

   development:
     <<: *default
     database: myapp_development

   production:
     <<: *default
     url: <%= ENV["DATABASE_URL"] %>
   ```

4. Create and migrate the local database:
   ```bash
   bin/rails db:create db:migrate
   ```

## Next Steps

- **[CLI Reference](../../reference/cli.md)** - Complete command reference
- **[hop3.toml Reference](../../reference/config.md)** - Full configuration options
- **[Backup and Restore Guide](../../guides/backup-restore.md)** - Protect your data
- **[Migration Guide](../migration-guide.md)** - Migrate from Heroku or other platforms

## Example Files

### Complete hop3.toml for Rails

```toml
# hop3.toml - Ruby on Rails Application

[metadata]
id = "hop3-tuto-rails"
version = "1.0.0"
title = "My Rails Application"
author = "Your Name <you@example.com>"

[build]
before-build = ["bin/rails assets:precompile"]
packages = ["postgresql-dev", "nodejs", "yarn"]

[run]
start = "bundle exec puma -C config/puma.rb"
before-run = "bin/rails db:migrate"
packages = ["postgresql"]

[env]
RAILS_ENV = "production"
RAILS_LOG_TO_STDOUT = "true"
RAILS_SERVE_STATIC_FILES = "true"
MALLOC_ARENA_MAX = "2"

[port]
web = 3000

[healthcheck]
path = "/up"
timeout = 30
interval = 60

[backup]
enabled = true
schedule = "0 3 * * *"
retention = 14

[[provider]]
name = "postgres"
plan = "standard"
version = "15"

[[provider]]
name = "redis"
plan = "basic"
```

### Complete Procfile for Rails

```procfile
# Procfile - Ruby on Rails Application

# Build phase (bundle install is handled by Ruby toolchain)
prebuild: bin/rails assets:precompile

# Pre-run hooks (database migrations)
prerun: bin/rails db:migrate

# Web server
web: bundle exec puma -C config/puma.rb

# Background job processor (optional)
worker: bundle exec sidekiq -C config/sidekiq.yml

# Scheduled tasks (optional)
scheduler: bundle exec sidekiq-scheduler
```
