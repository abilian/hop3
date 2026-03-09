# Hop3 Daily System Tests

End-to-end system test framework for Hop3, running comprehensive tests on real Hetzner Cloud infrastructure.

## Overview

This framework orchestrates the complete testing lifecycle:

1. **Server Reset**: Rebuilds a Hetzner server with a fresh OS image
2. **Deployment**: Runs `hop3-deploy` to install Hop3 with Docker support
3. **Test Execution**: Runs all test suites via hop3-testing framework
4. **Reporting**: Generates results summary (HTML reports planned)

## Architecture

### Key Principle: Client-Side CLI, Server-Side Builds

The test framework runs the `hop3` CLI **locally** on your machine, which connects to the remote server via SSH tunnel. All builds (including Docker) happen **on the server**, not locally.

```
┌─────────────────────────────────────────────────────────────────┐
│                  LOCAL MACHINE (Mac/Linux)                       │
│                                                                  │
│  hop3-daily-test  ──▶  hop3 CLI  ──▶  hop3-testing framework    │
│                            │                                     │
│                            │ SSH Tunnel (implicit auth)          │
│                            ▼                                     │
└─────────────────────────────────────────────────────────────────┘
                             │
                             │ Source code sent as tarball
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                  REMOTE SERVER (Hetzner)                         │
│                                                                  │
│  hop3-server  ──▶  Builders (Docker/Local)  ──▶  Deployers      │
│                                                                  │
│  All builds happen HERE, where Docker is installed               │
└─────────────────────────────────────────────────────────────────┘
```

This is exactly how a real user would deploy applications to Hop3.

## Prerequisites

- Python 3.12+
- Hetzner Cloud account with API token
- A Hetzner server dedicated for testing
- SSH key registered with Hetzner (for authentication)

## Installation

```bash
# From the repository root
cd qa/system-tests
uv sync

# Or install directly
uv pip install -e .
```

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `HETZNER_API_TOKEN` | Yes | Hetzner Cloud API token |
| `HETZNER_SERVER_ID` | Yes | Server ID to use for testing |
| `HOP3_BRANCH` | No | Git branch to test (default: `devel`) |
| `HOP3_REPORT_DIR` | No | Report output directory (default: `./reports`) |

### Configuration File (optional)

Create `config.toml`:

```toml
[hetzner]
api_token = "$HETZNER_API_TOKEN"
server_id = "$HETZNER_SERVER_ID"
image = "debian-12"

[deployment]
branch = "devel"
use_local_code = true
clean_before = true
features = ["docker"]  # Install Docker on server for containerized apps

[tests]
suites = ["test-apps", "demos"]
timeout_per_test = 300
fail_fast = false
```

## Usage

### Run Full Daily Test

```bash
# Set required environment variables
export HETZNER_API_TOKEN="your-token"
export HETZNER_SERVER_ID="12345678"

# Run full test cycle: reset server → deploy Hop3 → run tests
hop3-daily-test run

# Use local repository instead of cloning from git
hop3-daily-test run --use-local-repo
```

### Partial Runs

```bash
# Skip server reset (re-use existing server state)
hop3-daily-test run --skip-reset

# Skip reset and deployment (just run tests on already-deployed server)
hop3-daily-test run --skip-reset --skip-deploy

# Skip tests (only reset and deploy)
hop3-daily-test run --skip-tests
```

### Individual Commands

```bash
# Check server status
hop3-daily-test status

# Run tests only (assumes Hop3 already deployed)
hop3-daily-test test
```

### Select Specific Test Suites

```bash
# Run only test-apps suite
hop3-daily-test run --suites test-apps

# Run multiple suites
hop3-daily-test run --suites test-apps --suites demos
```

## Test Execution Flow

When tests run, the following happens for each app:

1. **Local**: `hop3` CLI packages app source into tarball
2. **Local**: CLI connects to server via SSH tunnel
3. **Local→Server**: Tarball sent to server
4. **Server**: hop3-server receives code, builds (Docker if needed), deploys
5. **Local**: Test framework verifies app responds to HTTP
6. **Server**: App destroyed via `hop3 app:destroy`

This ensures tests run exactly as a real deployment would work.

## Programmatic Usage

```python
from hop3_system_tests import Config, run_daily_test

# Load configuration from environment
config = Config.from_env()

# Run the daily test
result = run_daily_test(config)

# Check results
if result.success:
    print("All tests passed!")
else:
    print(f"Failed at phase: {result.failed_phase}")
    for phase in result.phase_results:
        print(f"  {phase.phase.value}: {phase.message}")
```

## Module Structure

```
src/hop3_system_tests/
├── __init__.py       # Public API exports
├── cli.py            # Click CLI commands
├── config.py         # Configuration management
├── hetzner.py        # Hetzner Cloud API integration
├── ssh.py            # SSH key management
├── deployment.py     # Hop3 deployment orchestration
├── orchestrator.py   # Main test orchestrator
└── runner.py         # Test runner (uses hop3-testing)
```

| Module | Purpose |
|--------|---------|
| `config` | Load and validate configuration from files/environment |
| `hetzner` | Manage Hetzner server lifecycle (rebuild, status) |
| `ssh` | SSH known_hosts management and connectivity testing |
| `deployment` | Run hop3-deploy with features (--with docker) |
| `runner` | Execute tests via hop3-testing framework |
| `orchestrator` | Coordinate all phases of the daily test |
| `cli` | Command-line interface |

## Development

```bash
# Install with dev dependencies
uv sync --dev

# Run linting
uv run ruff check src/

# Run tests
uv run pytest tests/

# Format code
uv run ruff format src/
```

## CI Integration

For GitHub Actions:

```yaml
name: Daily System Test

on:
  schedule:
    - cron: '0 4 * * *'  # 4 AM daily
  workflow_dispatch:

jobs:
  daily-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4

      - name: Run Daily Test
        env:
          HETZNER_API_TOKEN: ${{ secrets.HETZNER_API_TOKEN }}
          HETZNER_SERVER_ID: ${{ secrets.HETZNER_SERVER_ID }}
        run: |
          cd qa/system-tests
          uv sync
          uv run hop3-daily-test run --use-local-repo

      - name: Upload Report
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: daily-report
          path: qa/system-tests/reports/
```

## Implementation Status

### Complete
- [x] Hetzner API integration (rebuild, status)
- [x] SSH connectivity management
- [x] Deployment orchestration via hop3-deploy
- [x] Docker feature installation (`--with docker`)
- [x] Test runner integration with hop3-testing
- [x] CLI interface

### Planned
- [ ] HTML report generation
- [ ] Log archiving
- [ ] Historical tracking
- [ ] Notification hooks (Slack, email)

## Troubleshooting

### "Docker command not found" during tests

This means Docker wasn't installed on the server. Ensure:
1. Your deployment config includes `features = ["docker"]`
2. Or run with a fresh deployment: `hop3-daily-test run` (without `--skip-deploy`)

### Tests fail with SSH connection errors

1. Check your SSH key is registered with Hetzner
2. Verify the server is running: `hop3-daily-test status`
3. Try a fresh server: `hop3-daily-test run` (without `--skip-reset`)

### "hop3-server is not responding"

The server might not have Hop3 installed. Run without `--skip-deploy`:
```bash
hop3-daily-test run --skip-reset  # Keeps server, redeploys Hop3
```

## See Also

- [VISION.md](local-notes/VISION.md) - Detailed design document
- [hop3-testing](../../packages/hop3-testing/) - Test framework
- [hop3-installer](../../packages/hop3-installer/) - Deployment tools
