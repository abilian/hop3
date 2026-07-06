# Deploying Actix Web on Hop3

This guide walks you through deploying an Actix Web application on Hop3. Actix Web is a powerful, pragmatic, and extremely fast web framework for Rust.

## Prerequisites

Before you begin, ensure you have:

1. **A Hop3 server** - Follow the [Installation Guide](../../get-started/server-setup.md)
2. **The Hop3 CLI** - Installed on your local machine
3. **Rust 1.70+** - Install from [rustup.rs](https://rustup.rs/)
4. **Git** - For version control and deployment

Verify your local setup:

```bash
rustc --version
```

```bash
cargo --version
```

## Step 1: Create a New Actix Web Application

```bash
cargo new hop3-tuto-actix-web
```

Update Cargo.toml with dependencies:

```toml
[package]
name = "hop3-tuto-actix-web"
version = "1.0.0"
edition = "2021"

[dependencies]
# Disable the default brotli compression feature: brotli 8.0.3 pulls two
# incompatible alloc-no-stdlib versions and fails to compile. The reverse proxy
# handles compression anyway; keep gzip for completeness.
actix-web = { version = "4", default-features = false, features = ["macros", "compress-gzip"] }
actix-cors = "0.7"
serde = { version = "1", features = ["derive"] }
serde_json = "1"
tokio = { version = "1", features = ["full"] }
chrono = { version = "0.4", features = ["serde"] }
env_logger = "0.11"
log = "0.4"

[profile.release]
lto = true
codegen-units = 1
panic = "abort"
```

## Step 2: Create the Application

```rust
use actix_cors::Cors;
use actix_web::{get, post, web, App, HttpResponse, HttpServer, Responder};
use chrono::Utc;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::env;
use std::sync::Mutex;
use std::time::Instant;

static START_TIME: std::sync::OnceLock<Instant> = std::sync::OnceLock::new();

#[derive(Serialize)]
struct HealthResponse {
    status: String,
    timestamp: String,
    uptime_secs: u64,
}

#[derive(Serialize)]
struct InfoResponse {
    name: String,
    version: String,
    rust_version: String,
}

#[derive(Serialize, Deserialize, Clone)]
struct Item {
    id: u32,
    name: String,
    price: f64,
}

struct AppState {
    items: Mutex<HashMap<u32, Item>>,
    next_id: Mutex<u32>,
}

#[get("/")]
async fn index() -> impl Responder {
    HttpResponse::Ok().content_type("text/html").body(format!(
        r#"<!DOCTYPE html>
<html>
<head>
    <title>Welcome to Hop3</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            background: linear-gradient(135deg, #f74c00 0%, #b7410e 100%);
            color: white;
        }}
        .container {{ text-align: center; padding: 2rem; }}
        h1 {{ font-size: 3rem; margin-bottom: 1rem; }}
        p {{ font-size: 1.25rem; opacity: 0.9; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Hello from Hop3!</h1>
        <p>Your Actix Web application is running.</p>
        <p>Current time: {}</p>
    </div>
</body>
</html>"#,
        Utc::now().to_rfc3339()
    ))
}

#[get("/up")]
async fn up() -> impl Responder {
    "OK"
}

#[get("/health")]
async fn health() -> impl Responder {
    let start = START_TIME.get().unwrap();
    let response = HealthResponse {
        status: "ok".to_string(),
        timestamp: Utc::now().to_rfc3339(),
        uptime_secs: start.elapsed().as_secs(),
    };
    HttpResponse::Ok().json(response)
}

#[get("/api/info")]
async fn info() -> impl Responder {
    let response = InfoResponse {
        name: "hop3-tuto-actix-web".to_string(),
        version: "1.0.0".to_string(),
        rust_version: env!("CARGO_PKG_RUST_VERSION").to_string(),
    };
    HttpResponse::Ok().json(response)
}

#[get("/api/items")]
async fn get_items(data: web::Data<AppState>) -> impl Responder {
    let items = data.items.lock().unwrap();
    let items_vec: Vec<Item> = items.values().cloned().collect();
    HttpResponse::Ok().json(items_vec)
}

#[get("/api/items/{id}")]
async fn get_item(data: web::Data<AppState>, path: web::Path<u32>) -> impl Responder {
    let id = path.into_inner();
    let items = data.items.lock().unwrap();
    match items.get(&id) {
        Some(item) => HttpResponse::Ok().json(item),
        None => HttpResponse::NotFound().json(serde_json::json!({"error": "Not found"})),
    }
}

#[derive(Deserialize)]
struct CreateItem {
    name: String,
    price: f64,
}

#[post("/api/items")]
async fn create_item(data: web::Data<AppState>, body: web::Json<CreateItem>) -> impl Responder {
    let mut items = data.items.lock().unwrap();
    let mut next_id = data.next_id.lock().unwrap();

    let item = Item {
        id: *next_id,
        name: body.name.clone(),
        price: body.price,
    };
    items.insert(*next_id, item.clone());
    *next_id += 1;

    HttpResponse::Created().json(item)
}

#[actix_web::main]
async fn main() -> std::io::Result<()> {
    env_logger::init();
    START_TIME.get_or_init(Instant::now);

    let port: u16 = env::var("PORT")
        .unwrap_or_else(|_| "8080".to_string())
        .parse()
        .expect("PORT must be a number");

    let mut initial_items = HashMap::new();
    initial_items.insert(1, Item { id: 1, name: "Item 1".to_string(), price: 9.99 });
    initial_items.insert(2, Item { id: 2, name: "Item 2".to_string(), price: 19.99 });

    let app_state = web::Data::new(AppState {
        items: Mutex::new(initial_items),
        next_id: Mutex::new(3),
    });

    log::info!("Starting server on port {}", port);

    // SECURITY: Configure CORS explicitly in production - never use Cors::permissive()
    let allowed_origin = env::var("ALLOWED_ORIGIN").ok();

    HttpServer::new(move || {
        let cors = match &allowed_origin {
            Some(origin) => Cors::default().allowed_origin(origin),
            None => Cors::default(), // No CORS headers if not configured
        };

        App::new()
            .wrap(cors)
            .app_data(app_state.clone())
            .service(index)
            .service(up)
            .service(health)
            .service(info)
            .service(get_items)
            .service(get_item)
            .service(create_item)
    })
    .bind(("0.0.0.0", port))?
    .run()
    .await
}
```

## Step 3: Build and Test

```bash
cargo build --release 2>&1
```

```console
Finished
```

```bash
./target/release/hop3-tuto-actix-web &
APP_PID=$!
sleep 3
curl -s http://localhost:8080/health || echo "Test completed"
kill "$APP_PID" 2>/dev/null || true
```

```console
status
```

## Step 4: Create Deployment Configuration

```procfile
prebuild: cargo build --release
web: ./target/release/hop3-tuto-actix-web
```

```toml
[metadata]
id = "hop3-tuto-actix-web"
version = "1.0.0"
title = "My Actix Web Application"

[build]
before-build = ["cargo build --release"]
packages = ["rust", "cargo"]

[run]
start = "./target/release/hop3-tuto-actix-web"

[env]
RUST_LOG = "info"

[port]
web = 8080

[healthcheck]
path = "/up"
timeout = 30
interval = 60
```

## Step 5: Initialize Git Repository

Create a `.gitignore` file:

```text
# Build artifacts
target/
Cargo.lock

# Environment
.env
```

Initialize the repository:

```bash
git init
```

```bash
git add .
```

```bash
git commit -m "Initial Actix Web application"
```

```console
Initial Actix Web application
```

## Deploy to Hop3

The following steps require a Hop3 server.

### Initialize (First Time Only)

```bash
hop3 init --ssh root@your-server.example.com
```

### Set Environment Variables

```bash
hop3 env set --app hop3-tuto-actix-web RUST_LOG=info
hop3 env set --app hop3-tuto-actix-web ALLOWED_ORIGIN=https://hop3-tuto-actix-web.your-hop3-server.example.com
```

### Deploy

Deploy the application (first deployment creates the app):

```bash
hop3 deploy --app hop3-tuto-actix-web
```

```console
deployed successfully
```

### Set Hostname

Configure the hostname for nginx proxy:

```bash
hop3 env set --app hop3-tuto-actix-web HOST_NAME=hop3-tuto-actix-web.$HOP3_TEST_DOMAIN
```

### Wait for Process Stop

Wait for the previous deployment to fully stop:

```bash
sleep 5
```

### Apply Configuration

Redeploy to apply the hostname configuration:

```bash
hop3 deploy --app hop3-tuto-actix-web
```

```console
deployed successfully
```

### Verify Deployment

```bash
hop3 app status --app hop3-tuto-actix-web
```

```console
hop3-tuto-actix-web
```

```bash
curl -s http://hop3-tuto-actix-web.$HOP3_TEST_DOMAIN/up
```

```console
OK
```

View logs:

```bash
# View logs
hop3 app logs --app hop3-tuto-actix-web

# Your app will be available at:
# http://hop3-tuto-actix-web.your-hop3-server.example.com
```

### Managing Your Application

```bash
# Restart the application
hop3 app restart --app hop3-tuto-actix-web

# View/set environment variables
hop3 env show --app hop3-tuto-actix-web
hop3 env set --app hop3-tuto-actix-web NEW_VAR=value

# Scale workers
hop3 ps scale --app hop3-tuto-actix-web web=2
```

## Advanced Configuration

### Database with SQLx

```toml
[dependencies]
sqlx = { version = "0.7", features = ["runtime-tokio", "postgres"] }
```

```rust
let pool = sqlx::postgres::PgPoolOptions::new()
    .connect(&env::var("DATABASE_URL").unwrap())
    .await?;
```

### Redis with deadpool-redis

```rust
use deadpool_redis::{Config, Runtime};
let cfg = Config::from_url(env::var("REDIS_URL").unwrap());
let pool = cfg.create_pool(Some(Runtime::Tokio1)).unwrap();
```

## Example hop3.toml

```toml
[metadata]
id = "hop3-tuto-actix-web"
version = "1.0.0"

[build]
before-build = ["cargo build --release"]

[run]
start = "./target/release/hop3-tuto-actix-web"

[env]
RUST_LOG = "info"

[port]
web = 8080

[healthcheck]
path = "/up"

[[provider]]
name = "postgres"
plan = "standard"
```
