# Hop3 Daily System Tests

End-to-end system test framework for Hop3, running comprehensive tests on real Hetzner Cloud infrastructure.

## Quick Start

```bash
# Set required environment variables
export HETZNER_API_TOKEN="your-token"
export HETZNER_SERVER_ID="12345678"

cd qa/system-tests
uv sync

# Full test cycle: reset server → deploy Hop3 → run tests
uv run hop3-daily-test run --suites test-apps -v

# Other example:
uv run hop3-daily-test run --use-local-repo -x -v --random --suites native-apps
```

## Commands

| Command | Description |
|---------|-------------|
| `run` | Full pipeline: reset server, deploy Hop3, run tests |
| `test` | Run tests only (requires Hop3 already deployed) |
| `deploy` | Deploy Hop3 only (no tests) |
| `reset` | Reset server to fresh OS only |
| `status` | Check server status and connectivity |

### Common Workflows

```bash
# Full run with specific suites
uv run hop3-daily-test run --suites test-apps --suites demos -v

# Re-run tests after fixing a bug (skip reset, skip deploy)
uv run hop3-daily-test run --skip-reset --skip-deploy --suites test-apps

# Deploy Hop3 then run tests separately
uv run hop3-daily-test deploy
uv run hop3-daily-test test --suites test-apps
```

### Run vs Test

- **`run`**: The main command. Does everything: reset → deploy → test. Use `--skip-*` flags to skip phases.
- **`test`**: Runs tests only. **Requires Hop3 to be already deployed.** Use after `deploy` or `run --skip-tests`.

If you get "hop3-server not responding", you need to deploy first:
```bash
uv run hop3-daily-test run --skip-reset --suites test-apps
```

## Test Suites

| Suite | Source | Description |
|-------|--------|-------------|
| `test-apps` | `apps/test-apps/` | Lightweight test apps (Python, Node, Go, etc.) |
| `docker-apps` | `apps/docker-apps/` | Containerized applications |
| `native-apps` | `apps/native-apps/` | System-level applications |
| `demos` | `demos/` | Integration demos |
| `tutorials` | `docs/src/tutorials/` | Step-by-step tutorials |

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `HETZNER_API_TOKEN` | Yes | Hetzner Cloud API token |
| `HETZNER_SERVER_ID` | Yes | Server ID to use for testing |
| `HOP3_BRANCH` | No | Git branch to test (default: `devel`) |

## Architecture

Tests run the `hop3` CLI **locally**, which connects to the remote server via SSH tunnel. All builds happen **on the server**.

```
LOCAL (Mac/Linux)                    REMOTE (Hetzner)
┌─────────────────┐                  ┌─────────────────┐
│ hop3-daily-test │                  │ hop3-server     │
│       ↓         │                  │       ↓         │
│   hop3 CLI      │ ──SSH tunnel──▶  │ Builders        │
│       ↓         │   (tarball)      │       ↓         │
│ hop3-testing    │ ◀──HTTP verify── │ Deployed app    │
└─────────────────┘                  └─────────────────┘
```

## Troubleshooting

### "hop3-server is not responding"

Hop3 isn't installed on the server. Deploy it first:
```bash
uv run hop3-daily-test run --skip-reset --suites test-apps
```

### Stuck on "Waiting for SSH..."

The server rebuild is taking time. Wait up to 5 minutes, or Ctrl+C and check:
```bash
uv run hop3-daily-test status
```

### "Duplicate test name" warnings

Some tests have both `hop3.toml` and `test.toml` files. This is a known issue being fixed.

### Test fails with HTTPS redirect

Some apps incorrectly redirect to HTTPS. Check the nginx config on the server:
```bash
ssh root@<IP> cat /home/hop3/nginx/<app-name>.conf
```

## See Also

- [local-notes/VISION.md](local-notes/VISION.md) - Design document
- [local-notes/PLAN.md](local-notes/PLAN.md) - Current development plan
- [hop3-testing](../../packages/hop3-testing/) - Test framework
