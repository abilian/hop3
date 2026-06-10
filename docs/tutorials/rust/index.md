# Deploying Rust on Hop3

A Rust web app on Hop3 is a single compiled binary. Hop3 runs `cargo build --release` on the server, the resulting executable listens on the dynamic `$PORT` Hop3 hands it, and nginx proxies your domain to that port. There is no runtime to install on the server and no language server in front of your process — the binary *is* the server, and it sits behind nginx exactly like every other Hop3 app.

This page covers what is common to every Rust deployment. Each tutorial below is a complete, runnable walkthrough for one framework; read this first, then follow the guide for the framework you use.

## How Hop3 builds and runs Rust

Hop3 uses the Rust toolchain (`rustc` + `cargo`) on the server. You declare it with `packages = ["rust", "cargo"]` under `[build]`, so the toolchain is present even on a server that has never built Rust before.

The build is a single command: `before-build = ["cargo build --release"]`. Cargo compiles your crate with optimizations into `target/release/<binary-name>`, where `<binary-name>` is the `name` from your `Cargo.toml`. The release profile matters — debug builds are large and slow — so the tutorials also set `lto = true`, `codegen-units = 1`, and `panic = "abort"` in `[profile.release]` for smaller, faster binaries.

At runtime, Hop3 starts the binary directly (`start = "./target/release/<binary-name>"`), injects a `$PORT` environment variable, and expects the process to bind it. Your `main` reads `PORT`, binds `0.0.0.0:$PORT`, and serves; nginx forwards public traffic to it. A representative `hop3.toml`:

```toml
[metadata]
id = "my-rust-app"
version = "1.0.0"

[build]
before-build = ["cargo build --release"]
packages = ["rust", "cargo"]

[run]
start = "./target/release/my-rust-app"

[env]
RUST_LOG = "info"

[port]
web = 8080

[healthcheck]
path = "/up"
timeout = 30
interval = 60
```

The `[port] web` value is just the local default your binary falls back to when run by hand; in production Hop3 overrides it with `$PORT`. Always read `PORT` from the environment and bind `0.0.0.0` — binding `127.0.0.1` or a hardcoded port will leave nginx unable to reach you.

## Cross-cutting notes

A few things apply no matter which framework you pick:

- **Bind the dynamic port.** Read `std::env::var("PORT")` and bind `0.0.0.0`. A local fallback (e.g. `3000` or `8080`) is fine for `cargo run`, but Hop3 supplies the real port at deploy time.
- **Add a cheap health endpoint.** The tutorials expose `/up` returning `OK` and point `[healthcheck] path` at it. Keep it dependency-free so a slow database can't fail your healthcheck.
- **Addons arrive as env vars.** Attach a provider (e.g. PostgreSQL or Redis) and Hop3 injects `DATABASE_URL` / `REDIS_URL`. Read them at startup — for example with `sqlx::postgres::PgPoolOptions::connect(&env::var("DATABASE_URL")?)` or `deadpool_redis::Config::from_url(env::var("REDIS_URL")?)`. Do not hardcode connection strings.
- **Set `RUST_LOG`.** Logging crates (`env_logger`, `tracing-subscriber`) honor `RUST_LOG`; the tutorials set it to `info` under `[env]`.
- **Builds are slow the first time.** Compiling Rust release builds and all dependencies can take minutes. Subsequent deploys reuse cached compilation where possible, so they are much faster.
- **Don't commit `target/`.** Keep build artifacts out of git (`.gitignore` `target/`); Hop3 builds from source on the server.

## Choose a framework

| Framework | Tutorial | Description |
|-----------|----------|-------------|
| Axum | [Axum](axum.md) | Modern, ergonomic framework built on Tokio, Tower, and Hyper. |
| Actix Web | [Actix-web](actix-web.md) | Powerful, pragmatic, and extremely fast actor-based framework. |

Both follow the same build-and-run model above; pick the one whose API and ecosystem you prefer.
