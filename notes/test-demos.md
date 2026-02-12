# How to test the demos

## Directly

```
# First, (re)deploy the server (warning: this erases everyting)
uv run hop3-deploy --local --with all --clean

# Docker backend
python demos/demo.py --backend docker --local

# SSH backend
python demos/demo.py --host <your-server> --local

# Single demo
python demos/demo.py --backend docker --local demo01

# List available demos
python demos/demo.py --list
```

Alt:

```
# Single demo
python -m demos.demo --host hop3.dev --verbose demo29

# All demos
python -m demos.demo --host hop3.dev all
```

## Or using `make`

```
# Run demos on Docker backend
make test-demos-docker

# Run demos on SSH backend (requires HOP3_DEV_HOST)
make test-demos-ssh

# Run both
make test-demos
```
