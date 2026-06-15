# Deploying Gin (Go) on Hop3

This guide walks you through deploying a Gin web application on Hop3. By the end, you'll have a production-ready, high-performance Go API running on your own infrastructure.

## Prerequisites

Before you begin, ensure you have:

1. **A Hop3 server** - Follow the [Installation Guide](../../get-started/server-setup.md) if you haven't set one up yet
2. **The Hop3 CLI** - Installed on your local machine
3. **Go 1.21+** - Install from [go.dev](https://go.dev/)
4. **Git** - For version control and deployment

Verify your local setup:

```bash
go version
```

## Step 1: Create a New Gin Application

Create the project directory and initialize Go module:

```bash
mkdir hop3-tuto-gin && cd hop3-tuto-gin && go mod init hop3-tuto-gin
```

Install Gin:

```bash
go get -u github.com/gin-gonic/gin
```

## Step 2: Create the Application

Create the main application file:

```go
package main

import (
	"net/http"
	"os"
	"runtime"
	"time"

	"github.com/gin-gonic/gin"
)

var startTime = time.Now()

func main() {
	// Set Gin to release mode in production
	if os.Getenv("GIN_MODE") == "release" {
		gin.SetMode(gin.ReleaseMode)
	}

	r := gin.Default()

	// Welcome page
	r.GET("/", func(c *gin.Context) {
		c.Header("Content-Type", "text/html")
		c.String(http.StatusOK, `
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
            background: linear-gradient(135deg, #00ADD8 0%, #5DC9E2 100%);
            color: white;
        }
        .container { text-align: center; padding: 2rem; }
        h1 { font-size: 3rem; margin-bottom: 1rem; }
        p { font-size: 1.25rem; opacity: 0.9; }
        a {
            display: inline-block;
            margin-top: 1rem;
            padding: 0.75rem 1.5rem;
            background: rgba(255,255,255,0.2);
            border-radius: 8px;
            color: white;
            text-decoration: none;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Hello from Hop3!</h1>
        <p>Your Gin application is running.</p>
        <p>Current time: `+time.Now().Format(time.RFC3339)+`</p>
        <a href="/api/info">API Info</a>
    </div>
</body>
</html>`)
	})

	// Health check endpoint
	r.GET("/up", func(c *gin.Context) {
		c.String(http.StatusOK, "OK")
	})

	r.GET("/health", func(c *gin.Context) {
		var m runtime.MemStats
		runtime.ReadMemStats(&m)

		c.JSON(http.StatusOK, gin.H{
			"status":    "ok",
			"timestamp": time.Now().Format(time.RFC3339),
			"uptime":    time.Since(startTime).String(),
			"memory": gin.H{
				"alloc":      m.Alloc / 1024 / 1024,
				"totalAlloc": m.TotalAlloc / 1024 / 1024,
				"sys":        m.Sys / 1024 / 1024,
			},
		})
	})

	// API info endpoint
	r.GET("/api/info", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{
			"name":       "hop3-tuto-gin",
			"version":    "1.0.0",
			"go_version": runtime.Version(),
			"os":         runtime.GOOS,
			"arch":       runtime.GOARCH,
		})
	})

	// Example CRUD endpoints
	r.GET("/api/items", getItems)
	r.GET("/api/items/:id", getItem)
	r.POST("/api/items", createItem)
	r.PUT("/api/items/:id", updateItem)
	r.DELETE("/api/items/:id", deleteItem)

	// Get port from environment
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	r.Run(":" + port)
}

// Item represents a simple data model
type Item struct {
	ID          string  `json:"id"`
	Name        string  `json:"name"`
	Description string  `json:"description,omitempty"`
	Price       float64 `json:"price"`
}

// In-memory storage
var items = map[string]Item{
	"1": {ID: "1", Name: "Item 1", Description: "First item", Price: 9.99},
	"2": {ID: "2", Name: "Item 2", Description: "Second item", Price: 19.99},
}

func getItems(c *gin.Context) {
	itemList := make([]Item, 0, len(items))
	for _, item := range items {
		itemList = append(itemList, item)
	}
	c.JSON(http.StatusOK, itemList)
}

func getItem(c *gin.Context) {
	id := c.Param("id")
	if item, ok := items[id]; ok {
		c.JSON(http.StatusOK, item)
		return
	}
	c.JSON(http.StatusNotFound, gin.H{"error": "Item not found"})
}

func createItem(c *gin.Context) {
	var item Item
	if err := c.ShouldBindJSON(&item); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	items[item.ID] = item
	c.JSON(http.StatusCreated, item)
}

func updateItem(c *gin.Context) {
	id := c.Param("id")
	if _, ok := items[id]; !ok {
		c.JSON(http.StatusNotFound, gin.H{"error": "Item not found"})
		return
	}
	var item Item
	if err := c.ShouldBindJSON(&item); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	item.ID = id
	items[id] = item
	c.JSON(http.StatusOK, item)
}

func deleteItem(c *gin.Context) {
	id := c.Param("id")
	if _, ok := items[id]; !ok {
		c.JSON(http.StatusNotFound, gin.H{"error": "Item not found"})
		return
	}
	delete(items, id)
	c.Status(http.StatusNoContent)
}
```

## Step 3: Tidy Dependencies

```bash
go mod tidy
```

```bash
cat go.mod
```

```console
github.com/gin-gonic/gin
```

## Step 4: Build and Test

Build the application:

```bash
go build -o hop3-tuto-gin .
```

Test the application:

```bash
./hop3-tuto-gin &
APP_PID=$!
sleep 2
curl -s http://localhost:8080/health | head -1 || echo "Test completed"
kill $APP_PID 2>/dev/null || true
```

```console
status
```

## Step 5: Create Deployment Configuration

### Create a Procfile

```procfile
# Pre-build: Build the binary
prebuild: go build -o hop3-tuto-gin .

# Main web process
web: ./hop3-tuto-gin
```

### Create hop3.toml

```toml
[metadata]
id = "hop3-tuto-gin"
version = "1.0.0"
title = "My Gin Application"

[build]
before-build = ["go build -ldflags='-s -w' -o hop3-tuto-gin ."]
packages = ["golang"]

[run]
start = "./hop3-tuto-gin"

[env]
GIN_MODE = "release"

[port]
web = 8080

[healthcheck]
path = "/up"
timeout = 30
interval = 60
```

Verify the deployment files:

```bash
ls -la Procfile hop3.toml
```

```console
Procfile
```

```console
hop3.toml
```

## Step 6: Initialize Git Repository

```text
# Binary
hop3-tuto-gin

# Dependencies
vendor/

# IDE
.idea/
.vscode/
*.swp

# OS
.DS_Store

# Environment
.env
```

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
git commit -m "Initial Gin application"
```

```console
Initial Gin application
```

## Step 7: Deploy to Hop3

### Initialize (First Time Only)

```bash
hop3 init --ssh root@your-server.example.com
```

### Set Environment Variables

```bash
hop3 config set --app hop3-tuto-gin GIN_MODE=release
```

### Deploy

Deploy the application (first deployment creates the app):

```bash
hop3 deploy hop3-tuto-gin
```

### Set Hostname

Configure the hostname for nginx proxy:

```bash
hop3 config set --app hop3-tuto-gin HOST_NAME=hop3-tuto-gin.$HOP3_TEST_DOMAIN
```

### Apply Configuration

Redeploy to apply the hostname configuration:

```bash
hop3 deploy hop3-tuto-gin
```

Wait for the application to start:

```bash
sleep 5
```

### Verify Deployment

```bash
hop3 app status --app hop3-tuto-gin
```

```console
hop3-tuto-gin
```

```bash
curl -s http://hop3-tuto-gin.$HOP3_TEST_DOMAIN/up
```

```console
OK
```

### Managing Your Application

```bash
# Restart the application
hop3 app restart --app hop3-tuto-gin

# View logs
hop3 app logs --app hop3-tuto-gin

# View/set environment variables
hop3 config show --app hop3-tuto-gin
hop3 config set --app hop3-tuto-gin NEW_VAR=value

# Scale workers
hop3 ps scale --app hop3-tuto-gin web=2
```

## Advanced Configuration

### Adding PostgreSQL with GORM

```bash
go get -u gorm.io/gorm
go get -u gorm.io/driver/postgres
```

```go
package main

import (
    "os"
    "gorm.io/driver/postgres"
    "gorm.io/gorm"
)

var db *gorm.DB

func initDB() {
    dsn := os.Getenv("DATABASE_URL")
    var err error
    db, err = gorm.Open(postgres.Open(dsn), &gorm.Config{})
    if err != nil {
        panic("failed to connect database")
    }

    // Auto-migrate models
    db.AutoMigrate(&Item{})
}
```

### Adding Redis

```bash
go get -u github.com/redis/go-redis/v9
```

```go
import "github.com/redis/go-redis/v9"

var rdb *redis.Client

func initRedis() {
    opt, _ := redis.ParseURL(os.Getenv("REDIS_URL"))
    rdb = redis.NewClient(opt)
}
```

### JWT Authentication

```bash
go get -u github.com/golang-jwt/jwt/v5
```

```go
func authMiddleware() gin.HandlerFunc {
    return func(c *gin.Context) {
        tokenString := c.GetHeader("Authorization")
        if tokenString == "" {
            c.AbortWithStatusJSON(401, gin.H{"error": "unauthorized"})
            return
        }

        token, err := jwt.Parse(tokenString, func(token *jwt.Token) (interface{}, error) {
            return []byte(os.Getenv("JWT_SECRET")), nil
        })

        if err != nil || !token.Valid {
            c.AbortWithStatusJSON(401, gin.H{"error": "invalid token"})
            return
        }

        c.Next()
    }
}
```

### Structured Logging

```bash
go get -u go.uber.org/zap
```

```go
import "go.uber.org/zap"

var logger *zap.Logger

func initLogger() {
    var err error
    if os.Getenv("GIN_MODE") == "release" {
        logger, err = zap.NewProduction()
    } else {
        logger, err = zap.NewDevelopment()
    }
    if err != nil {
        panic(err)
    }
}
```

### Graceful Shutdown

```go
func main() {
    // ... setup routes ...

    srv := &http.Server{
        Addr:    ":" + port,
        Handler: r,
    }

    go func() {
        if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
            log.Fatalf("listen: %s\n", err)
        }
    }()

    quit := make(chan os.Signal, 1)
    signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
    <-quit
    log.Println("Shutting down server...")

    ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
    defer cancel()

    if err := srv.Shutdown(ctx); err != nil {
        log.Fatal("Server forced to shutdown:", err)
    }
}
```

## Troubleshooting

### Build Failures
- Check Go version: `go version`
- Verify dependencies: `go mod tidy`
- Check for syntax errors: `go build -v`

### Runtime Errors
- Verify PORT environment variable
- Check GIN_MODE for production

### Memory Usage
Go applications are typically memory-efficient, but monitor with `/health` endpoint.

## Example Files

### Complete hop3.toml

```toml
[metadata]
id = "hop3-tuto-gin"
version = "1.0.0"
title = "My Gin Application"

[build]
before-build = ["go build -ldflags='-s -w' -o hop3-tuto-gin ."]
packages = ["golang"]

[run]
start = "./hop3-tuto-gin"

[env]
GIN_MODE = "release"

[port]
web = 8080

[healthcheck]
path = "/up"
timeout = 30
interval = 60

[[provider]]
name = "postgres"
plan = "standard"

[[provider]]
name = "redis"
plan = "basic"
```

### Complete Procfile

```procfile
prebuild: go build -ldflags='-s -w' -o hop3-tuto-gin .
prerun: ./hop3-tuto-gin migrate || true
web: ./hop3-tuto-gin
```
