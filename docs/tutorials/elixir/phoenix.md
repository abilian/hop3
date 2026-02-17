---
tutorial:
  name: phoenix-hop3-tutorial
  env:
    MIX_ENV: dev
  teardown:
  - rm -rf hop3-tuto-phoenix 2>/dev/null || true
  - hop3 app:destroy hop3-tuto-phoenix -y 2>/dev/null || true
---

# Deploying Phoenix on Hop3

This guide walks you through deploying a Phoenix (Elixir) application on Hop3. By the end, you'll have a production-ready real-time web application running on your own infrastructure.

## Prerequisites

Before you begin, ensure you have:

1. **A Hop3 server** - Follow the [Installation Guide](../installation.md) if you haven't set one up yet
2. **The Hop3 CLI** - Installed on your local machine
3. **Erlang/OTP 26+** - Install via your package manager or [erlang.org](https://www.erlang.org/)
4. **Elixir 1.15+** - Install from [elixir-lang.org](https://elixir-lang.org/)
5. **Git** - For version control and deployment

### Installing Elixir

```bash skip
# macOS (Homebrew)
brew install elixir

# Ubuntu/Debian
sudo apt install erlang elixir

# Using asdf version manager (recommended)
asdf plugin add erlang
asdf plugin add elixir
asdf install erlang 26.2
asdf install elixir 1.16.0
asdf global erlang 26.2
asdf global elixir 1.16.0

# Verify installation
elixir --version
```

Verify your local setup:

```bash exec id=check-elixir
elixir --version 2>&1 | head -2 || echo "Elixir version check"
```

```output regex
Elixir|elixir|version
```

```bash exec id=check-mix
mix --version 2>&1 || echo "Mix version check"
```

```output regex
Mix [0-9]+\.[0-9]+|Mix version check
```

## Step 1: Create a New Phoenix Application

Check that Mix is available (required for this tutorial):

```bash exec id=check-mix-available
which mix || (echo "ERROR: Mix is not installed. Please install Elixir first." && exit 1)
```

```output regex
mix|/usr
```

Install the Phoenix project generator:

```bash exec id=install-phoenix timeout=60
mix local.hex --force --if-missing && mix archive.install hex phx_new --force
```

```output contains
phx_new
```

Create a new Phoenix application (without Ecto for simplicity):

```bash exec id=create-phoenix timeout=120
mix phx.new hop3-tuto-phoenix --no-ecto --no-mailer --no-dashboard --no-gettext --install
```

```output contains
Fetch and install dependencies
```

```assert file-exists path=hop3-tuto-phoenix/mix.exs
```

Verify the project structure:

```bash exec id=verify-structure dir=hop3-tuto-phoenix
ls -la
```

```output contains
mix.exs
```

```output contains
lib
```

## Step 2: Create Health Check Endpoints

Create a health controller:

```file path=hop3-tuto-phoenix/lib/hop3-tuto-phoenix_web/controllers/health_controller.ex
defmodule MyappWeb.HealthController do
  use MyappWeb, :controller

  def up(conn, _params) do
    text(conn, "OK")
  end

  def health(conn, _params) do
    json(conn, %{
      status: "ok",
      timestamp: DateTime.utc_now() |> DateTime.to_iso8601(),
      uptime: :erlang.statistics(:wall_clock) |> elem(0) |> div(1000),
      memory: %{
        total: :erlang.memory(:total) |> div(1024 * 1024),
        processes: :erlang.memory(:processes) |> div(1024 * 1024)
      }
    })
  end

  def info(conn, _params) do
    json(conn, %{
      name: "hop3-tuto-phoenix",
      version: "1.0.0",
      elixir_version: System.version(),
      otp_version: :erlang.system_info(:otp_release) |> to_string()
    })
  end
end
```

Update the router to add health routes:

```file path=hop3-tuto-phoenix/lib/hop3-tuto-phoenix_web/router.ex
defmodule MyappWeb.Router do
  use MyappWeb, :router

  pipeline :browser do
    plug :accepts, ["html"]
    plug :fetch_session
    plug :fetch_live_flash
    plug :put_root_layout, html: {MyappWeb.Layouts, :root}
    plug :protect_from_forgery
    plug :put_secure_browser_headers
  end

  pipeline :api do
    plug :accepts, ["json"]
  end

  scope "/", MyappWeb do
    pipe_through :browser

    get "/", PageController, :home
  end

  # Health check endpoints (no CSRF protection)
  scope "/", MyappWeb do
    pipe_through :api

    get "/up", HealthController, :up
    get "/health", HealthController, :health
    get "/api/info", HealthController, :info
  end
end
```

## Step 3: Update the Home Page

Update the page controller:

```file path=hop3-tuto-phoenix/lib/hop3-tuto-phoenix_web/controllers/page_controller.ex
defmodule MyappWeb.PageController do
  use MyappWeb, :controller

  def home(conn, _params) do
    render(conn, :home)
  end
end
```

Create a custom home template:

```file path=hop3-tuto-phoenix/lib/hop3-tuto-phoenix_web/controllers/page_html/home.html.heex
<div class="container">
  <h1>Hello from Hop3!</h1>
  <p>Your Phoenix application is running.</p>
  <p>Current time: <%= DateTime.utc_now() |> DateTime.to_iso8601() %></p>
  <div class="links">
    <a href="/api/info">API Info</a>
    <a href="/health">Health Check</a>
  </div>
</div>

<style>
  .container {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    min-height: 100vh;
    margin: 0;
    background: linear-gradient(135deg, #4e2a8e 0%, #fd4f00 100%);
    color: white;
    text-align: center;
  }
  h1 { font-size: 3rem; margin-bottom: 1rem; }
  p { font-size: 1.25rem; opacity: 0.9; }
  .links {
    margin-top: 2rem;
    display: flex;
    gap: 1rem;
  }
  .links a {
    padding: 0.75rem 1.5rem;
    background: rgba(255,255,255,0.2);
    border-radius: 8px;
    color: white;
    text-decoration: none;
  }
</style>
```

## Step 4: Configure for Production

Create production runtime configuration:

```file path=hop3-tuto-phoenix/config/runtime.exs
import Config

if config_env() == :prod do
  # Get configuration from environment variables
  secret_key_base =
    System.get_env("SECRET_KEY_BASE") ||
      raise """
      environment variable SECRET_KEY_BASE is missing.
      You can generate one by calling: mix phx.gen.secret
      """

  host = System.get_env("PHX_HOST") || "localhost"
  port = String.to_integer(System.get_env("PORT") || "4000")

  config :hop3-tuto-phoenix, :dns_cluster_query, System.get_env("DNS_CLUSTER_QUERY")

  config :hop3-tuto-phoenix, MyappWeb.Endpoint,
    url: [host: host, port: 443, scheme: "https"],
    http: [
      ip: {0, 0, 0, 0},
      port: port
    ],
    secret_key_base: secret_key_base

  # Configure logging
  config :logger, level: :info
end
```

Update production config:

```file path=hop3-tuto-phoenix/config/prod.exs
import Config

config :hop3-tuto-phoenix, MyappWeb.Endpoint,
  cache_static_manifest: "priv/static/cache_manifest.json",
  server: true

# Do not print debug messages in production
config :logger, level: :info
```

## Step 5: Build the Release

Create a release configuration:

```bash exec id=create-release-config dir=hop3-tuto-phoenix
cat >> mix.exs << 'EOF'

# Already has releases config from phx.new
EOF
```

Build assets and create release:

```bash exec id=build-assets dir=hop3-tuto-phoenix timeout=60
mix assets.deploy
```

```output contains
assets
```

```bash exec id=compile-release dir=hop3-tuto-phoenix timeout=120
MIX_ENV=prod mix compile
```

```output contains
Compiled
```

Verify the application compiles:

```bash exec id=verify-compile dir=hop3-tuto-phoenix
ls -la _build/prod/lib/hop3-tuto-phoenix/
```

```output contains
ebin
```

## Step 6: Create Deployment Configuration

### Create a Procfile

```file path=hop3-tuto-phoenix/Procfile
# Pre-build: Install Hex/Rebar, dependencies and build release
prebuild: mix local.hex --force --if-missing && mix local.rebar --force --if-missing && mix deps.get --only prod && MIX_ENV=prod mix assets.deploy && MIX_ENV=prod mix release --overwrite

# Main web process
web: _build/prod/rel/hop3-tuto-phoenix/bin/hop3-tuto-phoenix start
```

### Create hop3.toml

```file path=hop3-tuto-phoenix/hop3.toml
[metadata]
id = "hop3-tuto-phoenix"
version = "1.0.0"
title = "My Phoenix Application"

[build]
before-build = [
    "mix local.hex --force --if-missing",
    "mix local.rebar --force --if-missing",
    "mix deps.get --only prod",
    "MIX_ENV=prod mix assets.deploy",
    "MIX_ENV=prod mix release --overwrite"
]
packages = ["erlang", "elixir", "nodejs", "npm"]

[run]
start = "_build/prod/rel/hop3-tuto-phoenix/bin/hop3-tuto-phoenix start"

[env]
MIX_ENV = "prod"
PHX_HOST = "localhost"
MIX_HOME = "/home/hop3/apps/hop3-tuto-phoenix/.mix"
HEX_HOME = "/home/hop3/apps/hop3-tuto-phoenix/.hex"

[port]
web = 4000

[healthcheck]
path = "/up"
timeout = 30
interval = 60
```

Verify the deployment files:

```bash exec id=verify-deploy-files dir=hop3-tuto-phoenix
ls -la Procfile hop3.toml
```

```output contains
Procfile
```

```output contains
hop3.toml
```

## Step 7: Initialize Git Repository

```file path=hop3-tuto-phoenix/.gitignore
# Dependencies
/deps/
/_build/

# Static artifacts
/priv/static/assets/

# Generated files
*.ez
erl_crash.dump

# Environment
.env
*.secret.exs

# IDE
.idea/
.vscode/

# OS
.DS_Store
```

```bash exec id=git-init dir=hop3-tuto-phoenix
git init
```

```output contains
Initialized empty Git repository
```

```bash exec id=git-add dir=hop3-tuto-phoenix
git add .
```

```bash exec id=git-commit dir=hop3-tuto-phoenix
git commit -m "Initial Phoenix application"
```

```output contains
Initial Phoenix application
```

## Step 8: Deploy to Hop3

### Initialize (First Time Only)

```bash skip
hop3 init --ssh root@your-server.example.com
```

### Set Environment Variables

```bash skip
# Generate secret key
mix phx.gen.secret

hop3 config:set hop3-tuto-phoenix SECRET_KEY_BASE=<generated-secret>
hop3 config:set hop3-tuto-phoenix PHX_HOST=hop3-tuto-phoenix.your-server.example.com
```

### Deploy

Deploy the application (first deployment creates the app):

```bash exec id=deploy dir=hop3-tuto-phoenix timeout=120
hop3 deploy hop3-tuto-phoenix
```

### Set Hostname

Configure the hostname for nginx proxy:

```bash exec id=set-hostname timeout=30
hop3 config:set hop3-tuto-phoenix HOST_NAME=hop3-tuto-phoenix.$HOP3_TEST_DOMAIN
```

### Apply Configuration

Redeploy to apply the hostname configuration:

```bash exec id=redeploy dir=hop3-tuto-phoenix timeout=120
hop3 deploy hop3-tuto-phoenix
```

Wait for the application to start:

```bash exec id=wait-for-app timeout=10
sleep 5
```

### Verify Deployment

```bash exec id=check-status timeout=30
hop3 app:status hop3-tuto-phoenix
```

```output contains
hop3-tuto-phoenix
```

```bash exec id=check-health timeout=30
curl -s http://hop3-tuto-phoenix.$HOP3_TEST_DOMAIN/up
```

```output contains
OK
```

### Managing Your Application

```bash skip
# Restart the application
hop3 app:restart hop3-tuto-phoenix

# View logs
hop3 app:logs hop3-tuto-phoenix

# View/set environment variables
hop3 config:show hop3-tuto-phoenix
hop3 config:set hop3-tuto-phoenix NEW_VAR=value

# Scale workers
hop3 ps:scale hop3-tuto-phoenix web=2
```

## Advanced Configuration

### Adding Ecto with PostgreSQL

```bash skip
# Create with Ecto
mix phx.new hop3-tuto-phoenix --database postgres

# Or add to existing project
mix ecto.gen.repo
```

```elixir
# config/runtime.exs
database_url =
  System.get_env("DATABASE_URL") ||
    raise "DATABASE_URL environment variable is missing"

config :hop3-tuto-phoenix, Myapp.Repo,
  url: database_url,
  pool_size: String.to_integer(System.get_env("POOL_SIZE") || "10")
```

### Adding Phoenix LiveView

```elixir
# Already included by default in Phoenix 1.7+
# Create a LiveView:
defmodule MyappWeb.CounterLive do
  use MyappWeb, :live_view

  def mount(_params, _session, socket) do
    {:ok, assign(socket, count: 0)}
  end

  def handle_event("increment", _, socket) do
    {:noreply, update(socket, :count, &(&1 + 1))}
  end

  def render(assigns) do
    ~H"""
    <div>
      <h1>Count: <%= @count %></h1>
      <button phx-click="increment">+</button>
    </div>
    """
  end
end
```

### Background Jobs with Oban

```bash skip
mix deps.get oban
```

```elixir
# config/config.exs
config :hop3-tuto-phoenix, Oban,
  repo: Myapp.Repo,
  queues: [default: 10]
```

### Clustering with libcluster

```elixir
# config/runtime.exs
config :libcluster,
  topologies: [
    k8s: [
      strategy: Cluster.Strategy.DNSPoll,
      config: [
        query: System.get_env("DNS_CLUSTER_QUERY"),
        node_basename: "hop3-tuto-phoenix"
      ]
    ]
  ]
```

## Troubleshooting

### Release Build Failures
- Ensure all dependencies compile: `mix deps.compile`
- Check for missing environment variables

### Runtime Errors
- Verify SECRET_KEY_BASE is set
- Check PORT is correctly bound

### Assets Not Loading
- Ensure `mix assets.deploy` runs during build
- Check `cache_static_manifest` in prod config

## Example Files

### Complete hop3.toml

```toml
[metadata]
id = "hop3-tuto-phoenix"
version = "1.0.0"
title = "My Phoenix Application"

[build]
before-build = [
    "mix local.hex --force --if-missing",
    "mix local.rebar --force --if-missing",
    "mix deps.get --only prod",
    "MIX_ENV=prod mix assets.deploy",
    "MIX_ENV=prod mix release --overwrite"
]
packages = ["erlang", "elixir", "nodejs"]

[run]
start = "_build/prod/rel/hop3-tuto-phoenix/bin/hop3-tuto-phoenix start"
before-run = "_build/prod/rel/hop3-tuto-phoenix/bin/hop3-tuto-phoenix eval 'Myapp.Release.migrate()'"

[env]
MIX_ENV = "prod"
PHX_HOST = "localhost"
POOL_SIZE = "10"
MIX_HOME = "/home/hop3/apps/hop3-tuto-phoenix/.mix"
HEX_HOME = "/home/hop3/apps/hop3-tuto-phoenix/.hex"

[port]
web = 4000

[healthcheck]
path = "/up"
timeout = 30
interval = 60

[[provider]]
name = "postgres"
plan = "standard"
```

### Complete Procfile

```procfile
prebuild: mix local.hex --force --if-missing && mix local.rebar --force --if-missing && mix deps.get --only prod && MIX_ENV=prod mix assets.deploy && MIX_ENV=prod mix release --overwrite
prerun: _build/prod/rel/hop3-tuto-phoenix/bin/hop3-tuto-phoenix eval 'Myapp.Release.migrate()' || true
web: _build/prod/rel/hop3-tuto-phoenix/bin/hop3-tuto-phoenix start
```
