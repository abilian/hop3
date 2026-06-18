---
tutorial:
  name: fiber-hop3-tutorial
  teardown:
  - rm -rf hop3-tuto-fiber 2>/dev/null || true
  - hop3 app destroy --app hop3-tuto-fiber -y 2>/dev/null || true
---

# Deploying Fiber on Hop3

This guide walks you through deploying a Fiber application on Hop3. Fiber is an Express-inspired web framework built on Fasthttp, the fastest HTTP engine for Go.

## Prerequisites

Before you begin, ensure you have:

1. **A Hop3 server** - Follow the [Installation Guide](../../get-started/server-setup.md)
2. **The Hop3 CLI** - Installed on your local machine
3. **Go 1.21+** - Install from [go.dev](https://go.dev/)
4. **Git** - For version control and deployment

Verify your local setup:

```bash exec id=check-go
go version
```

```output regex
go version go[0-9]+\.[0-9]+
```

## Step 1: Create a New Fiber Application

```bash exec id=create-project
mkdir hop3-tuto-fiber && cd hop3-tuto-fiber && go mod init hop3-tuto-fiber
```

```assert file-exists path=hop3-tuto-fiber/go.mod
```

Install Fiber:

```bash exec id=install-fiber dir=hop3-tuto-fiber timeout=60
go get github.com/gofiber/fiber/v2
```

## Step 2: Create the Application

```file path=hop3-tuto-fiber/main.go
package main

import (
	"os"
	"runtime"
	"time"

	"github.com/gofiber/fiber/v2"
	"github.com/gofiber/fiber/v2/middleware/cors"
	"github.com/gofiber/fiber/v2/middleware/logger"
	"github.com/gofiber/fiber/v2/middleware/recover"
)

var startTime = time.Now()

func main() {
	app := fiber.New(fiber.Config{
		AppName: "hop3-tuto-fiber v1.0.0",
	})

	// Middleware
	app.Use(recover.New())
	app.Use(logger.New())
	app.Use(cors.New())

	// Welcome page
	app.Get("/", func(c *fiber.Ctx) error {
		c.Set("Content-Type", "text/html")
		return c.SendString(`
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
            background: linear-gradient(135deg, #00ACD7 0%, #5DC9E2 100%);
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
        <p>Your Fiber application is running.</p>
        <p>Current time: ` + time.Now().Format(time.RFC3339) + `</p>
    </div>
</body>
</html>`)
	})

	// Health endpoints
	app.Get("/up", func(c *fiber.Ctx) error {
		return c.SendString("OK")
	})

	app.Get("/health", func(c *fiber.Ctx) error {
		var m runtime.MemStats
		runtime.ReadMemStats(&m)
		return c.JSON(fiber.Map{
			"status":    "ok",
			"timestamp": time.Now().Format(time.RFC3339),
			"uptime":    time.Since(startTime).String(),
			"memory_mb": m.Alloc / 1024 / 1024,
		})
	})

	app.Get("/api/info", func(c *fiber.Ctx) error {
		return c.JSON(fiber.Map{
			"name":       "hop3-tuto-fiber",
			"version":    "1.0.0",
			"go_version": runtime.Version(),
			"fiber":      fiber.Version,
		})
	})

	// Example CRUD API
	type Item struct {
		ID    int     `json:"id"`
		Name  string  `json:"name"`
		Price float64 `json:"price"`
	}

	items := map[int]*Item{
		1: {ID: 1, Name: "Item 1", Price: 9.99},
		2: {ID: 2, Name: "Item 2", Price: 19.99},
	}
	nextID := 3

	app.Get("/api/items", func(c *fiber.Ctx) error {
		result := make([]*Item, 0, len(items))
		for _, item := range items {
			result = append(result, item)
		}
		return c.JSON(result)
	})

	app.Get("/api/items/:id", func(c *fiber.Ctx) error {
		id, _ := c.ParamsInt("id")
		if item, ok := items[id]; ok {
			return c.JSON(item)
		}
		return c.Status(404).JSON(fiber.Map{"error": "Not found"})
	})

	app.Post("/api/items", func(c *fiber.Ctx) error {
		item := new(Item)
		if err := c.BodyParser(item); err != nil {
			return c.Status(400).JSON(fiber.Map{"error": err.Error()})
		}
		item.ID = nextID
		nextID++
		items[item.ID] = item
		return c.Status(201).JSON(item)
	})

	// Get port from environment
	port := os.Getenv("PORT")
	if port == "" {
		port = "3000"
	}

	app.Listen(":" + port)
}
```

## Step 3: Build and Test

```bash exec id=tidy-deps dir=hop3-tuto-fiber
go mod tidy
```

```bash exec id=build-app dir=hop3-tuto-fiber timeout=60
go build -o hop3-tuto-fiber .
```

```assert file-exists path=hop3-tuto-fiber/hop3-tuto-fiber
```

```bash exec id=test-app dir=hop3-tuto-fiber timeout=10
./hop3-tuto-fiber &
APP_PID=$!
sleep 2
curl -s http://localhost:3000/health || echo "Test completed"
kill "$APP_PID" 2>/dev/null || true
```

```output contains
status
```

## Step 4: Create Deployment Configuration

```file path=hop3-tuto-fiber/Procfile
prebuild: go build -ldflags='-s -w' -o hop3-tuto-fiber .
web: ./hop3-tuto-fiber
```

```file path=hop3-tuto-fiber/hop3.toml
[metadata]
id = "hop3-tuto-fiber"
version = "1.0.0"
title = "My Fiber Application"

[build]
before-build = ["go build -ldflags='-s -w' -o hop3-tuto-fiber ."]
packages = ["golang"]

[run]
start = "./hop3-tuto-fiber"

[port]
web = 3000

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

### Deploy

Deploy the application (first deployment creates the app):

```bash exec id=deploy dir=hop3-tuto-fiber timeout=120
hop3 deploy --app hop3-tuto-fiber
```

```output contains
deployed successfully
```

### Set Hostname

Configure the hostname for nginx proxy:

```bash exec id=set-hostname timeout=30
hop3 config set --app hop3-tuto-fiber HOST_NAME=hop3-tuto-fiber.$HOP3_TEST_DOMAIN
```

### Apply Configuration

Redeploy to apply the hostname configuration:

```bash exec id=redeploy dir=hop3-tuto-fiber timeout=120
hop3 deploy --app hop3-tuto-fiber
```

```output contains
deployed successfully
```

### Verify Deployment

```bash exec id=check-status timeout=30
hop3 app status --app hop3-tuto-fiber
```

```output contains
hop3-tuto-fiber
```

```bash exec id=check-health timeout=30
curl -s http://hop3-tuto-fiber.$HOP3_TEST_DOMAIN/up
```

```output contains
OK
```

View logs:

```bash skip
# View logs
hop3 app logs --app hop3-tuto-fiber

# Your app will be available at:
# http://hop3-tuto-fiber.your-hop3-server.example.com
```

### Managing Your Application

```bash skip
# Restart the application
hop3 app restart --app hop3-tuto-fiber

# View/set environment variables
hop3 config show --app hop3-tuto-fiber
hop3 config set --app hop3-tuto-fiber NEW_VAR=value

# Scale workers
hop3 ps scale --app hop3-tuto-fiber web=2
```

## Advanced Configuration

### Database with GORM

```go
import "gorm.io/driver/postgres"
import "gorm.io/gorm"

db, err := gorm.Open(postgres.Open(os.Getenv("DATABASE_URL")), &gorm.Config{})
```

### JWT Authentication

```go
import "github.com/gofiber/fiber/v2/middleware/keyauth"

app.Use(keyauth.New(keyauth.Config{
    Validator: func(c *fiber.Ctx, key string) (bool, error) {
        return key == os.Getenv("API_KEY"), nil
    },
}))
```

## Example hop3.toml

```toml
[metadata]
id = "hop3-tuto-fiber"
version = "1.0.0"

[build]
before-build = ["go build -ldflags='-s -w' -o hop3-tuto-fiber ."]

[run]
start = "./hop3-tuto-fiber"

[port]
web = 3000

[healthcheck]
path = "/up"

[[provider]]
name = "postgres"
plan = "standard"
```
