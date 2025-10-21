# Manual E2E Testing Scripts

This directory contains shell scripts for manually testing Hop3 E2E workflows without pytest. These scripts replicate the automated test logic from `packages/hop3-server/tests/d_e2e/`.

## Quick Start

Run all steps automatically:

```bash
bash scripts/manual-testing/run-all.sh
```

This will:
1. Build the Docker image
2. Start the container
3. Extract SSH keys
4. Create a test Flask app
5. Deploy it via hop3 CLI
6. Verify HTTP access through nginx

## Individual Steps

You can also run steps individually for debugging:

### Step 1: Build Docker Image
```bash
bash scripts/manual-testing/01-build-image.sh
```

### Step 2: Start Container
```bash
bash scripts/manual-testing/02-start-container.sh
```

Starts container with port mappings:
- Host 2222 → Container 22 (SSH)
- Host 8080 → Container 80 (HTTP Proxy)
- Host 8008 → Container 8000 (Hop3 API)

### Step 3: Extract SSH Key
```bash
bash scripts/manual-testing/03-extract-ssh-key.sh
```

Extracts SSH key from container to `/tmp/hop3-debug-key`.

### Step 4: Create Test App
```bash
bash scripts/manual-testing/04-create-test-app.sh
```

Creates a simple Flask app in `/tmp/flask-manual-test/` and saves environment variables to `.env-manual-test`.

### Step 5: Deploy App
```bash
bash scripts/manual-testing/05-deploy-app.sh
```

**Dependencies**: Requires step 3 and 4 to be run first (needs `.env-manual-test`).

Packages the app into a tarball and deploys via `hop3 deploy` CLI command.

### Step 6: Verify Deployment
```bash
bash scripts/manual-testing/06-verify-deployment.sh
```

**Dependencies**: Requires steps 3-5 to be run first.

Checks app status and verifies HTTP access through nginx with retry logic.

### Step 7: Cleanup
```bash
bash scripts/manual-testing/07-cleanup.sh
```

Stops the container and removes all temporary files including the `.env-manual-test` file.

## How Variable Sharing Works

Scripts 4-7 share environment variables via `.env-manual-test` file in this directory:

- **04-create-test-app.sh**: Creates `.env-manual-test` with `APP_NAME`, `APP_DIR`, `HOSTNAME`, etc.
- **05-deploy-app.sh**: Sources `.env-manual-test` and adds `TARBALL_PATH`
- **06-verify-deployment.sh**: Sources `.env-manual-test` to get app info
- **07-cleanup.sh**: Sources `.env-manual-test` to clean up properly

## Deployment Command

The correct hop3 deploy syntax is:

```bash
hop3 deploy app-name /path/to/app/directory
```

The CLI automatically creates a tarball from the directory. Do NOT use stdin redirection - it will be ignored and the current directory will be deployed instead!

## Prerequisites

- Docker installed and running
- `hop3` CLI available in PATH (from hop3-cli package)
- Run from the project root directory

## Troubleshooting

### "hop3: command not found"
Install the hop3-cli package:
```bash
uv pip install -e packages/hop3-cli
```

### "Environment file not found"
Run steps in sequence (3 → 4 → 5 → 6), or use `run-all.sh`.

### HTTP 502 errors
The app may take 20-30 seconds to start. Script 06 has retry logic built in.

## Files

- `01-build-image.sh` - Build E2E Docker image
- `02-start-container.sh` - Start container with port mappings
- `03-extract-ssh-key.sh` - Extract SSH key for CLI access
- `04-create-test-app.sh` - Create Flask test app and save environment
- `05-deploy-app.sh` - Deploy app via hop3 CLI
- `06-verify-deployment.sh` - Verify deployment and HTTP access
- `07-cleanup.sh` - Clean up container and temp files
- `run-all.sh` - Run all steps sequentially (recommended)
- `.env-manual-test` - Shared environment variables (created by scripts)
