# 130-golang-minimal

## Purpose

Tests Hop3's **minimal Go deployment** without external dependencies.

## What It Validates

- Go toolchain with no go.mod (single-file Go program)
- Implicit Go module handling
- Minimal Go application deployment

## Structure

```
Procfile    # web: go run server.go
server.go   # Minimal HTTP server (stdlib only)
```

## Technical Details

- **Toolchain**: Go (detected via .go files)
- **Dependencies**: None (stdlib only)
- **No go.mod**: Tests implicit module handling

## Comparison with 030-golang-gin

| Aspect | 030 (Gin) | 130 (Minimal) |
|--------|-----------|---------------|
| go.mod | Yes | No |
| Dependencies | Gin framework | stdlib only |
| Complexity | Framework | Raw net/http |

## Why This Test Matters

Not all Go applications use modules or external dependencies. This validates that Hop3 can deploy simple Go programs that use only the standard library, which is common for small utilities and microservices.
