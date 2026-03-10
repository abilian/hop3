# 030-golang-gin

## Purpose

Tests Hop3's **Go deployment** with the Gin web framework.

## What It Validates

- Go toolchain detection via `go.mod`
- Go module dependency resolution
- Go compilation and execution
- PORT environment variable injection

## Structure

```
Procfile    # web: go run server.go
go.mod      # module definition with gin dependency
go.sum      # dependency checksums
server.go   # Gin HTTP server
```

## Technical Details

- **Toolchain**: Go (detected via go.mod)
- **Deployer**: uWSGI (generic process management)
- **Procfile syntax**: `web: go run server.go`

## Why This Test Matters

Go applications are increasingly common in cloud deployments. This test validates that Hop3 can handle Go module resolution and compilation.
