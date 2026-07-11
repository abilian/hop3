# How to Test the Demos

## Using hop3-test (Recommended)

```bash
# List available demos
hop3-test list --category demo

# Run all demos against Docker
hop3-test system --docker

# Run specific demo
hop3-test run demo01 --docker
```

## Using demo.py Directly

```bash
# First, (re)deploy the server (warning: this erases everything)
uv run hop3-deploy --local --with all --clean

# Docker backend
python demos/demo.py run --backend docker --local

# SSH backend
python demos/demo.py run --host <your-server> --local

# Single demo
python demos/demo.py run --backend docker --local demo01

# List available demos
python demos/demo.py list
```

Alternative module syntax:

```bash
# Single demo
python -m demos.demo --host hop3.dev --verbose demo29

# All demos
python -m demos.demo --host hop3.dev all
```

## Using Make

```bash
# Run demos on Docker backend
make test-demos

# Run demos on SSH backend (pass the server explicitly with --host)
python demos/demo.py run --host <your-server> --local
```

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `HOP3_LOCAL` | Use local code instead of git |

> The SSH demo target is passed explicitly via `--host` — it is not read from an env var. `HOP3_DEV_HOST` / `HOP3_TEST_HOST` are retired as target selectors (ADR 043); the demo runner even strips `HOP3_DEV_HOST` from the CLI subprocess env so a stray value can't redirect it.
