# Deploying Elixir on Hop3

Deploying Elixir on Hop3 means building an OTP *release* with Mix and running it as a long-lived BEAM process. Hop3 compiles your project on the server, packages it into a self-contained release with `mix release`, and runs that release binary as a managed worker. The BEAM listens on the dynamic `$PORT` Hop3 assigns, and nginx proxies your hostname to it — the same model as every other language on Hop3, with the BEAM's supervision trees and clustering available on top.

This page covers what every Elixir deployment has in common. Read it first, then follow the framework guide below for a complete, runnable walkthrough.

## How Hop3 builds and runs Elixir

Hop3 installs the toolchain your build needs — declare it in `[build].packages` (typically `erlang`, `elixir`, and `nodejs` for asset bundling). On each deploy, the `before-build` steps run on the server: install Hex/Rebar, fetch production deps, build assets, and cut the release with `mix release`. The result lands in `_build/prod/rel/<app>/`, and `[run].start` launches the release binary as the `web` worker.

The release process must bind to the port Hop3 gives it. Hop3 exports `$PORT` into the run environment; your app reads it (Phoenix does this in `config/runtime.exs`) and listens on `0.0.0.0:$PORT`. Hop3 then configures nginx to forward your `HOST_NAME` to that process — you never bind a fixed public port yourself.

A representative `hop3.toml`:

```toml
[metadata]
id = "my-elixir-app"
version = "1.0.0"

[build]
before-build = [
    "mix local.hex --force --if-missing",
    "mix local.rebar --force --if-missing",
    "mix deps.get --only prod",
    "MIX_ENV=prod mix assets.deploy",
    "MIX_ENV=prod mix release --overwrite",
]
packages = ["erlang", "elixir", "nodejs"]

[run]
start = "_build/prod/rel/my-elixir-app/bin/my-elixir-app start"

[env]
MIX_ENV = "prod"
MIX_HOME = "/home/hop3/apps/my-elixir-app/.mix"
HEX_HOME = "/home/hop3/apps/my-elixir-app/.hex"

[port]
web = 4000

[healthcheck]
path = "/up"
timeout = 30
interval = 60
```

## Notes that apply to every Elixir app

- **Releases, not `mix phx.server`.** Production deploys run a compiled OTP release, which bundles the Erlang runtime and your compiled code into one artifact — no Mix or source needed at runtime. Build it in `before-build`, run it in `[run].start`.
- **Set `SECRET_KEY_BASE`.** Releases refuse to start without it. Declare `SECRET_KEY_BASE = { generate = "urlsafe", length = 64 }` in `hop3.toml` `[env]` and Hop3 generates one on the first deploy, persists it, and reuses it on every later deploy — no `mix phx.gen.secret`, no manual step, nothing committed.
- **Hostname and host config.** Set `HOST_NAME` so nginx routes to your app, and `PHX_HOST` so the framework builds correct URLs. After setting them, deploy once more so the changes take effect.
- **Databases via addons.** Add a PostgreSQL addon and Hop3 injects `DATABASE_URL`; read it in `config/runtime.exs` and run migrations from a `before-run` release-eval step so they apply before the new release serves traffic.
- **Health checks.** Expose a cheap endpoint (Phoenix ships `/up`) and point `[healthcheck].path` at it so Hop3 knows when the BEAM is actually ready.
- **Build cost.** The first deploy fetches and compiles all dependencies, which is slow; subsequent deploys reuse `_build` and `deps` and are much faster.

## Choose a framework

| Framework | Description |
|-----------|-------------|
| [Phoenix](phoenix.md) | The standard Elixir web framework — real-time apps with LiveView, channels, and an OTP release, proxied by nginx on the dynamic `$PORT`. |
