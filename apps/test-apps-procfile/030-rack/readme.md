# 030-rack

## Purpose

Tests Hop3's **Ruby Rack deployment** with Bundler and Puma.

## What It Validates

- Ruby toolchain detection via `Gemfile`
- Bundler dependency installation (`bundle install`)
- Puma web server execution
- Rack application loading via `config.ru`

## Structure

```
Procfile     # web: bundle exec puma -p $PORT config.ru
Gemfile      # rack, puma dependencies
config.ru    # Rack configuration
hello.rb     # Application logic
```

## Technical Details

- **Toolchain**: Ruby (detected via Gemfile)
- **Deployer**: uWSGI (generic process management)
- **Server**: Puma (Rack-compatible)
- **Procfile syntax**: `web: bundle exec puma ...`

## Local Testing

```bash
bundle install
bundle exec rackup
# Visit http://localhost:9292
```

## Why This Test Matters

Rack is the foundation of Ruby web frameworks (Rails, Sinatra, etc.). Testing bare Rack ensures the Ruby toolchain works correctly before testing higher-level frameworks.
