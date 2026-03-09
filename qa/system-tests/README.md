# Hop3 Daily System Tests

End-to-end system test framework for Hop3, running comprehensive tests on real Hetzner Cloud infrastructure.

## Overview

This framework orchestrates the complete testing lifecycle:

1. **Server Reset**: Rebuilds a Hetzner server with a fresh OS image
2. **Deployment**: Clones the Hop3 repo and runs `hop3-deploy`
3. **Test Execution**: Runs all test suites (apps, Docker apps, demos, tutorials)
4. **Reporting**: Generates HTML reports with detailed results

## Prerequisites

- Python 3.12+
- Hetzner Cloud account with API token
- A Hetzner server dedicated for testing
- SSH key registered with Hetzner

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
ssh_key_name = "hop3-ci"

[deployment]
branch = "devel"
domain = "test.hop3.dev"
acme_email = "admin@hop3.dev"
use_local_code = true
clean_before = true

[tests]
suites = ["test-apps", "docker-apps", "demos", "tutorials"]
timeout_per_test = 300
fail_fast = false

[tests.docker_apps_subset]
# Run only these Docker apps in daily tests
include = ["isso", "kanboard", "radicale", "searxng"]
```

## Usage

### Run Full Daily Test

```bash
# Using environment variables
export HETZNER_API_TOKEN="your-token"
export HETZNER_SERVER_ID="12345678"

hop3-daily-test run

# Or with explicit options
hop3-daily-test run --server-id 12345678 --branch main
```

### Individual Commands

```bash
# Check server status
hop3-daily-test status --server-id 12345678

# Reset server only (no deployment or tests)
hop3-daily-test reset --server-id 12345678 --image debian-12

# Deploy without reset
hop3-daily-test deploy --server-id 12345678 --branch devel
```

### Partial Runs

```bash
# Skip server reset (re-use existing state)
hop3-daily-test run --skip-reset

# Skip reset and deployment (just run tests)
hop3-daily-test run --skip-reset --skip-deploy

# Run only reset and deployment (no tests)
hop3-daily-test run --skip-tests
```

### Select Specific Test Suites

```bash
# Run only test-apps
hop3-daily-test run --suites test-apps

# Run multiple suites
hop3-daily-test run --suites test-apps --suites docker-apps
```

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

## Architecture

```
src/hop3_system_tests/
├── __init__.py       # Public API exports
├── cli.py            # Click CLI commands
├── config.py         # Configuration management
├── hetzner.py        # Hetzner Cloud API integration
├── ssh.py            # SSH key management
├── deployment.py     # Hop3 deployment orchestration
└── orchestrator.py   # Main test orchestrator
```

### Module Responsibilities

| Module | Purpose |
|--------|---------|
| `config` | Load and validate configuration from files/environment |
| `hetzner` | Manage Hetzner server lifecycle (rebuild, reset, status) |
| `ssh` | SSH known_hosts management and connectivity testing |
| `deployment` | Clone repo and run hop3-deploy |
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
          uv run hop3-daily-test run --report-dir ./reports

      - name: Upload Report
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: daily-report
          path: qa/system-tests/reports/
```

## Roadmap

### Phase 1 (Current)
- [x] Hetzner API integration
- [x] Server reset (rebuild)
- [x] SSH key management
- [x] Deployment orchestration
- [x] CLI interface

### Phase 2 (Next)
- [ ] Test runner integration with hop3-testing
- [ ] Docker apps testing
- [ ] Demo/tutorial testing

### Phase 3
- [ ] HTML report generation
- [ ] Log archiving
- [ ] Historical tracking

### Phase 4
- [ ] Notification hooks (Slack, email)
- [ ] Performance regression tracking
- [ ] Multi-provider support

## See Also

- [VISION.md](VISION.md) - Detailed design document
- [hop3-testing](../../packages/hop3-testing/) - Test framework
- [hop3-installer](../../packages/hop3-installer/) - Deployment tools
