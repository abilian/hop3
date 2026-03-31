# 040-sinatra

## Purpose

Tests Hop3's **Ruby Sinatra deployment** with Bundler.

## What It Validates

- Ruby toolchain with Sinatra framework
- Bundler dependency installation
- Direct Ruby script execution (not Rack config.ru)
- Sinatra's built-in web server

## Structure

```
Procfile    # web: bundle exec ruby app.rb
Gemfile     # sinatra dependency
app.rb      # Sinatra application
```

## Technical Details

- **Toolchain**: Ruby (detected via Gemfile)
- **Deployer**: uWSGI (generic process management)
- **Framework**: Sinatra (lightweight Ruby web framework)
- **Procfile syntax**: `web: bundle exec ruby app.rb`

## Why This Test Matters

Sinatra is a popular lightweight Ruby framework. This tests Ruby deployment without the complexity of Rails, validating the core Ruby toolchain functionality.
