# Deploying Axum on Hop3

This guide walks you through deploying an Axum application on Hop3. Axum is a modern, ergonomic web framework built on Tokio, Tower, and Hyper.

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

## Step 1: Create a New Axum Application

```bash
cargo new hop3-tuto-axum
```

Update Cargo.toml:

```toml
[package]
name = "hop3-tuto-axum"
version = "1.0.0"
edition = "2021"

[dependencies]
axum = "0.7"
tokio = { version = "1", features = ["full"] }
tower = "0.4"
tower-http = { version = "0.5", features = ["cors", "trace"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
chrono = { version = "0.4", features = ["serde"] }
tracing = "0.1"
tracing-subscriber = { version = "0.3", features = ["env-filter"] }

[profile.release]
lto = true
codegen-units = 1
panic = "abort"
```

## Step 2: Create the Application

```rust
use axum::{
    extract::{Path, State},
    http::StatusCode,
    response::{Html, IntoResponse},
    routing::{get, post},
    Json, Router,
};
use chrono::Utc;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::env;
use std::net::SocketAddr;
use std::sync::{Arc, Mutex};
use std::time::Instant;
use tower_http::cors::CorsLayer;
use tower_http::trace::TraceLayer;

#[derive(Clone)]
struct AppState {
    items: Arc<Mutex<HashMap<u32, Item>>>,
    next_id: Arc<Mutex<u32>>,
    start_time: Instant,
}

#[derive(Serialize, Deserialize, Clone)]
struct Item {
    id: u32,
    name: String,
    price: f64,
}

#[derive(Deserialize)]
struct CreateItem {
    name: String,
    price: f64,
}

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

async fn index() -> Html<String> {
    Html(format!(
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
            background: linear-gradient(135deg, #f74c00 0%, #7b3f00 100%);
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
        <p>Your Axum application is running.</p>
        <p>Current time: {}</p>
    </div>
</body>
</html>"#,
        Utc::now().to_rfc3339()
    ))
}

async fn up() -> &'static str {
    "OK"
}

async fn health(State(state): State<AppState>) -> Json<HealthResponse> {
    Json(HealthResponse {
        status: "ok".to_string(),
        timestamp: Utc::now().to_rfc3339(),
        uptime_secs: state.start_time.elapsed().as_secs(),
    })
}

async fn info() -> Json<InfoResponse> {
    Json(InfoResponse {
        name: "hop3-tuto-axum".to_string(),
        version: "1.0.0".to_string(),
        rust_version: "1.70+".to_string(),
    })
}

async fn get_items(State(state): State<AppState>) -> Json<Vec<Item>> {
    let items = state.items.lock().unwrap();
    Json(items.values().cloned().collect())
}

async fn get_item(
    State(state): State<AppState>,
    Path(id): Path<u32>,
) -> Result<Json<Item>, StatusCode> {
    let items = state.items.lock().unwrap();
    items
        .get(&id)
        .cloned()
        .map(Json)
        .ok_or(StatusCode::NOT_FOUND)
}

async fn create_item(
    State(state): State<AppState>,
    Json(input): Json<CreateItem>,
) -> impl IntoResponse {
    let mut items = state.items.lock().unwrap();
    let mut next_id = state.next_id.lock().unwrap();

    let item = Item {
        id: *next_id,
        name: input.name,
        price: input.price,
    };
    items.insert(*next_id, item.clone());
    *next_id += 1;

    (StatusCode::CREATED, Json(item))
}

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "info".into()),
        )
        .init();

    let mut initial_items = HashMap::new();
    initial_items.insert(1, Item { id: 1, name: "Item 1".to_string(), price: 9.99 });
    initial_items.insert(2, Item { id: 2, name: "Item 2".to_string(), price: 19.99 });

    let state = AppState {
        items: Arc::new(Mutex::new(initial_items)),
        next_id: Arc::new(Mutex::new(3)),
        start_time: Instant::now(),
    };

    let app = Router::new()
        .route("/", get(index))
        .route("/up", get(up))
        .route("/health", get(health))
        .route("/api/info", get(info))
        .route("/api/items", get(get_items).post(create_item))
        .route("/api/items/:id", get(get_item))
        .layer(CorsLayer::permissive())
        .layer(TraceLayer::new_for_http())
        .with_state(state);

    let port: u16 = env::var("PORT")
        .unwrap_or_else(|_| "3000".to_string())
        .parse()
        .expect("PORT must be a number");

    let addr = SocketAddr::from(([0, 0, 0, 0], port));
    tracing::info!("Listening on {}", addr);

    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    axum::serve(listener, app).await.unwrap();
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
./target/release/hop3-tuto-axum &
APP_PID=$!
sleep 3
curl -s http://localhost:3000/health || echo "Test completed"
kill "$APP_PID" 2>/dev/null || true
```

```console
status
```

## Step 4: Create Deployment Configuration

```procfile
prebuild: cargo build --release
web: ./target/release/hop3-tuto-axum
```

```toml
[metadata]
id = "hop3-tuto-axum"
version = "1.0.0"
title = "My Axum Application"

[build]
before-build = ["cargo build --release"]
packages = ["rust", "cargo"]

[run]
start = "./target/release/hop3-tuto-axum"

[env]
RUST_LOG = "info"

[port]
web = 3000

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
git commit -m "Initial Axum application"
```

```console
Initial Axum application
```

## Deploy to Hop3

The following steps require a Hop3 server.

### Initialize (First Time Only)

```bash
hop3 init --ssh root@your-server.example.com
```

### Set Environment Variables

```bash
hop3 config set --app hop3-tuto-axum RUST_LOG=info
```

### Deploy

Deploy the application (first deployment creates the app):

```bash
hop3 deploy --app hop3-tuto-axum
```

```console
deployed successfully
```

### Set Hostname

Configure the hostname for nginx proxy:

```bash
hop3 config set --app hop3-tuto-axum HOST_NAME=hop3-tuto-axum.$HOP3_TEST_DOMAIN
```

### Wait for Process Stop

Wait for the previous deployment to fully stop:

```bash
sleep 5
```

### Apply Configuration

Redeploy to apply the hostname configuration:

```bash
hop3 deploy --app hop3-tuto-axum
```

```console
deployed successfully
```

### Verify Deployment

```bash
hop3 app status --app hop3-tuto-axum
```

```console
hop3-tuto-axum
```

```bash
curl -s http://hop3-tuto-axum.$HOP3_TEST_DOMAIN/up
```

```console
OK
```

View logs:

```bash
# View logs
hop3 app logs --app hop3-tuto-axum

# Your app will be available at:
# http://hop3-tuto-axum.your-hop3-server.example.com
```

### Managing Your Application

```bash
# Restart the application
hop3 app restart --app hop3-tuto-axum

# View/set environment variables
hop3 config show --app hop3-tuto-axum
hop3 config set --app hop3-tuto-axum NEW_VAR=value

# Scale workers
hop3 ps scale --app hop3-tuto-axum web=2
```

## Advanced Configuration

### Database with SQLx

```rust
use sqlx::postgres::PgPoolOptions;

let pool = PgPoolOptions::new()
    .max_connections(5)
    .connect(&env::var("DATABASE_URL").unwrap())
    .await?;
```

### Shared State with Extensions

```rust
use axum::extract::Extension;

let app = Router::new()
    .route("/", get(handler))
    .layer(Extension(pool));
```

## Example hop3.toml

```toml
[metadata]
id = "hop3-tuto-axum"
version = "1.0.0"

[build]
before-build = ["cargo build --release"]

[run]
start = "./target/release/hop3-tuto-axum"

[env]
RUST_LOG = "info"

[port]
web = 3000

[healthcheck]
path = "/up"

[[provider]]
name = "postgres"
plan = "standard"
```
