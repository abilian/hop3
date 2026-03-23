# Flask Hello - Nix Integration Demo

Simple Flask "Hello World" app for testing Hop3's Nix integration.

## Files

- `app.py` - Flask application
- `hop3.nix` - Nix expression for Hop3 deployment
- `Procfile` - Worker definition (for non-Nix deployment)
- `requirements.txt` - Python dependencies (for non-Nix deployment)

## hop3.nix Format

The `hop3.nix` file produces:
1. A `package` derivation with the built application
2. A `hop3/runtime.json` file inside the package with runtime configuration

```nix
{
  package = <derivation>;  # Required: the built package
  env = { ... };           # Optional: static env vars (no derivation refs)
}
```

The `runtime.json` inside the built package contains:
```json
{
  "workers": { "web": "/nix/store/.../bin/app --bind unix:$HOP3_SOCKET" },
  "env": { "KEY": "value" },
  "path": [ "/nix/store/.../bin" ]
}
```

## Testing with Nix

```bash
# Build the package
nix-build hop3.nix -A package --no-out-link
# Output: /nix/store/xxx-flask-hello-0.1.0

# Check the runtime config
cat /nix/store/xxx-flask-hello-0.1.0/hop3/runtime.json

# Test the app manually
STORE_PATH=$(nix-build hop3.nix -A package --no-out-link)
$STORE_PATH/bin/flask-hello --bind 127.0.0.1:5000 --chdir $STORE_PATH/app --daemon
curl http://localhost:5000/
curl http://localhost:5000/health
pkill -f gunicorn
```

## How NixBuilder Will Use This

1. Check `hop3.nix` exists → `accept()` returns True
2. Run `nix-build hop3.nix -A package` → get store path
3. Read `$STORE_PATH/hop3/runtime.json` → extract RuntimeConfig
4. Return `BuildArtifact` with kind="nix", location=store_path

## Expected Output

```
$ curl http://flask-hello.local/
Hello from Nix-built Flask!

$ curl http://flask-hello.local/health
OK
```

## Validated

Tested 2026-03-23:
- nix-build succeeds
- runtime.json contains correct store paths
- gunicorn runs and serves requests correctly
