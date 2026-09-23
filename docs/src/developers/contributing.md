# Hop3 Contribution Guidelines

You're reading this because you're interested in contributing to Hop3, and that makes us happy! Your contributions make Hop3 a better platform and strengthen the open source community around it.

These guidelines keep collaboration smooth for everyone.

## Getting Started

Before you start, read the [core values of Hop3](core-values.md) document. These principles keep your contributions aligned with the project's goals.

## Contribution Process

### 1. Open an Issue

If you've identified a bug, have a feature suggestion, or have a question, start by opening an issue. Describe the bug, feature, or question in detail, providing as much context as possible. Context helps us understand and address your concern or proposal.

### 2. Fork and Clone the Repository

Once you're ready to work on an issue, fork the Hop3 repository to your GitHub account and clone it to your local development environment. This will allow you to work on the code changes on your machine.

### 3. Create a New Branch

For each set of changes, create a new branch in your forked repository. Use a descriptive name for your branch that reflects the changes you intend to make.

### Guidelines for Contributions

- **Small and Focused Pull Requests (PRs)**: Keep each PR focused on a single issue or feature request. Unrelated changes make it harder to review and merge your contributions.

- **Code Style**: Follow the project's coding style. For Python code, we adhere to PEP8 guidelines, except where explicitly stated otherwise. When importing functions, import them directly: `from os.path import abspath`.

- **Write Meaningful Commit Messages**: Commit messages should clearly describe what changed and why. This helps maintainers understand your changes and speeds up review.

- **Update Documentation**: If your changes require updates to the documentation, include those in your PR. Users and contributors depend on the documentation being accurate and current.

- **Testing**: Include tests for your changes to ensure that the new code works as expected and does not break existing functionality. Add new tests if you're introducing new features or fixing bugs. See the [Testing](#testing) section below for detailed requirements.

- **Review Process**: After you submit your PR, a project maintainer will review it. Be open to feedback and prepared to adjust your code. The review is a collaborative effort, and constructive dialogue is welcome.

### 4. Submitting Your Pull Request

Once your changes are complete and pushed to your fork, submit a pull request to the main Hop3 repository with a clear description of the changes and references to any related issues.

## Testing

Hop3 uses a three-layer testing strategy (see ADR 043). All contributions should include appropriate tests. A test's layer is decided by what it *needs*: Docker, root, or host mutation. Duplicating a test across layers is allowed.

### Test Requirements

**For Bug Fixes:**
- Add a test that reproduces the bug (should fail before your fix)
- Verify the test passes after your fix
- Add tests at the appropriate layer (usually unit or integration)

**For New Features:**
- Add unit tests (`a_unit/`) for new functions/classes
- Add integration tests (`b_integration/`) for component interactions that need a real in-memory DB
- Add E2E tests (`c_e2e/`) if the feature needs a real Docker deploy or host mutation

### Running Tests

Before submitting a PR, ensure all tests pass:

```bash
# Fast tests (unit only, no Docker) - the inner loop, run constantly
make test-fast

# Check tier (unit + integration, all packages, no Docker) - run before pushing
make test

# Docker e2e layer (real deploys, backups, git-push) - needs Docker
make test-e2e
```

### Test Layers

Each package's `tests/` directory holds up to three layers. Each layer gets a marker from the root `conftest.py` (`fast`, `integration`, `e2e`, `needs_docker`), so `pytest -m fast` and `pytest -m "not needs_docker"` work across all packages.

1. **Unit Tests** (`tests/a_unit/`): fast, isolated tests of individual functions
   - No Docker or other external dependencies
   - Counts toward coverage
   - Tier: `fast` (the inner loop, < 1 min for the whole suite)

2. **Integration Tests** (`tests/b_integration/`): component interaction tests
   - In-process, against a real in-memory database; no Docker
   - Counts toward coverage
   - Tier: `check`

3. **E2E Tests** (`tests/c_e2e/`): complete workflow tests
   - **Requires Docker**: real application deploys, backups, git-push
   - Does *not* count toward coverage
   - Runs in the check tier (Docker) and nightly

> Earlier versions of this doc described a four-layer model with a `c_system` layer and a `d_e2e` layer. That has been consolidated: `c_system` was dissolved (its in-process test moved into `b_integration`) and `d_e2e` was renamed `c_e2e`. See ADR 043.

### Docker Requirement

E2E tests require Docker to be installed and running:

```bash
# Check Docker is installed
docker --version

# Check Docker daemon is running
docker ps
```

Docker is installed differently on each platform:
- **macOS**: Install [Docker Desktop](https://www.docker.com/products/docker-desktop)
- **Linux**: Install via your package manager (e.g., `apt install docker.io`)
- **Windows**: Install [Docker Desktop](https://www.docker.com/products/docker-desktop)

### Test Environment Setup

```bash
# Install test dependencies
uv sync --dev

# Run the check tier (no Docker)
make test
```

pytest e2e runs against Docker by default; the root `conftest.py` strips `HOP3_DEV_HOST` / `HOP3_TEST_HOST` (ADR 043), so an ambient value can't redirect a run at a real box. Pass `--ssh-host` to target a remote server explicitly.

Nothing in the workspace is optional to its test suite. The dev group installs every extra the tests exercise (the WAF engine among them), and in a workspace run `pytest.importorskip` fails instead of skipping: a skipped import used to drop a whole test file from a green run. A skip is kept only for a resource the harness cannot provision, such as `systemctl` on macOS or a MySQL server, and `-ra` prints each one's reason. If a run fails with "missing from the workspace venv", run `make develop`.

### Dependencies and the cooldown

The lock never selects a distribution uploaded in the last seven days (`[tool.uv] exclude-newer = "7 days"` in `pyproject.toml`). A compromised release is usually caught and yanked within days, and `uv lock --upgrade` would otherwise take it the hour it lands. The setting is relative, so there is no date to refresh. A fix you need sooner than a week is a deliberate exception: override it for that one package with `exclude-newer-package`, and say why in the commit.

Servers get the same week. The installer writes it into the server venv's `pip.conf`, so every pip call on that venv resolves dependencies under it. Hop3's own packages are the exception: they are installed first with the cutoff lifted, so a release can be installed the day it ships.

### Secrets

The `gitleaks` pre-commit hook scans every commit's staged diff for tokens, cloud credentials and other secrets, and CI runs `make secrets-scan` over the whole history. A fixture that must look like a secret takes a `gitleaks:allow` comment on its line. `.gitleaksignore` lists historical findings that were triaged and accepted. A new finding never goes there to make a scan pass: rotate the secret first.

### Writing Tests

Follow these guidelines when writing tests:

1. **Place tests in the correct layer**: unit tests for isolated functions, integration tests for component interactions, and so on.

2. **Use descriptive names**: Test names should clearly describe what they test
   ```python
   def test_user_cannot_delete_other_users_apps():
       """Test that users can only delete their own apps."""
   ```

3. **Follow Arrange-Act-Assert pattern**:
   ```python
   def test_app_deployment():
       # Arrange
       app = create_test_app()

       # Act
       result = deploy_app(app)

       # Assert
       assert result.success
       assert result.app.state == "RUNNING"
   ```

4. **Use fixtures for common setup**:
   ```python
   @pytest.fixture
   def sample_app(tmp_path):
       """Create a sample app directory."""
       app_dir = tmp_path / "test-app"
       app_dir.mkdir()
       (app_dir / "Procfile").write_text("web: python app.py")
       return app_dir
   ```

5. **Test both success and failure cases**:
   ```python
   def test_valid_app_name_accepted():
       assert is_valid_app_name("my-app")

   def test_invalid_app_name_rejected():
       assert not is_valid_app_name("my app")  # spaces not allowed
   ```

### Test Configuration

E2E tests run in Docker containers with `HOP3_UNSAFE=true` to bypass authentication. This is **only** safe because tests run in completely isolated Docker containers, which are destroyed after tests complete and never exposed to any network.

**Never** use `HOP3_UNSAFE` outside of isolated test containers. See the [Security Policy](../reference/policies/security-policy.md#hop3_unsafe-mode) for more details.

### Additional Testing Resources

For comprehensive testing documentation, see:
- [Testing Strategy](./testing-strategy.md) for the complete testing guide
- [Testing Documentation](./testing.md) for a quick reference
- test-status for current test status

## Continuous Integration

Hop3 runs CI on [SourceHut builds](https://builds.sr.ht/), driven by the manifests under `.builds/` (one per target distro, e.g. `ubuntu2404.yml`, `rockylinux.yml`). All pull requests should pass these checks before being merged.

### Test Runners

Three runners cover three domains; only pytest produces coverage:

- **pytest**: platform code (unit, integration, e2e).
- **hop3-test**: applications, real apps and demos alike, deployed and verified over the `DeploymentTarget` ABC (Docker, SSH, Hetzner). See `make test-apps` / `uv run hop3-test list`.
- **validoc**: narratives, tutorials-as-tests. See `make test-tutorials`.

On failure of a Docker e2e or app test, a diagnostic bundle is collected; run `hop3-test why <run-id>` to inspect it.

### Running CI Checks Locally

Before submitting a PR, you can run the same checks locally:

```bash
make lint                # Linting and type checks
make secrets-scan        # Committed secrets, whole history (needs gitleaks)
make test                # Check tier: unit + integration, all packages, no Docker
make test-e2e            # Docker e2e layer (real deploys, slow)
make test-cov  # Coverage on the in-process layers (what coverage.py sees)
```

### Coverage Requirements

Coverage is produced by pytest on the in-process layers only (`a_unit` + `b_integration`). The Docker e2e layer contributes none. Run `make test-cov` to reproduce it. We don't enforce strict coverage requirements; we expect:
- New features to include tests covering the main code paths
- Bug fixes to include regression tests
- Coverage not to decrease significantly with new changes

## CLI Message Types and Rich Output

When developing CLI commands or modifying server responses, follow these message type conventions for consistent, user-friendly output.

### Message Format

All CLI output is formatted as a list of message dictionaries. Each message has a `"t"` (type) field that determines how it renders. A command's `call()` method returns a plain `list` of these dictionaries, built with the helpers in `hop3.commands._response`:

```python
from hop3.commands._response import success, table

# Return a list of messages
return [
    success("Operation completed successfully"),
    table(headers=["App", "Status"], rows=[["myapp", "RUNNING"]]),
]
```

### Available Message Types

#### 1. `text` - Plain Text
Default message type for general information.

```python
{"t": "text", "text": "This is plain text output"}
```

**Output:** Plain text without formatting

**Use for:**
- General information
- Command output that doesn't fit other categories
- Default messages when type is omitted

#### 2. `success` - Success Messages
Green checkmark with success message.

```python
{"t": "success", "text": "Application deployed successfully"}
```

**Output:** `✓ Application deployed successfully` (green)

**Use for:**
- Successful completion of operations
- Confirmation messages
- Positive feedback

#### 3. `error` - Error Messages
Red error prefix with error message. **Always shown, even in quiet mode.**

```python
{"t": "error", "text": "Application not found"}
```

**Output:** `ERROR: Application not found` (bold red)

**Use for:**
- Fatal errors
- Validation failures
- Operation failures

**Important:** Errors are always printed to stderr and shown even with `--quiet` flag.

#### 4. `warning` - Warning Messages
Yellow warning symbol with message.

```python
{"t": "warning", "text": "Application is not using HTTPS"}
```

**Output:** `⚠ Application is not using HTTPS` (yellow)

**Use for:**
- Non-fatal issues
- Deprecation notices
- Configuration warnings

#### 5. `info` - Info Messages
Blue info symbol with message.

```python
{"t": "info", "text": "Application will restart after config change"}
```

**Output:** `i Application will restart after config change` (blue)

**Use for:**
- Helpful tips
- Additional context
- Non-critical information

#### 6. `progress` - Progress Indicators
Hourglass symbol for ongoing operations.

```python
{"t": "progress", "text": "Building application..."}
```

**Output:** `⏳ Building application...` (cyan)

**Use for:**
- Long-running operations
- Build/deployment progress
- Processing indicators

**Note:** Future enhancement will add real progress bars.

#### 7. `panel` - Boxed Text
Text displayed in a bordered panel/box.

```python
{
    "t": "panel",
    "title": "Deployment Summary",
    "text": "App: myapp\nURL: myapp.hop3.example.com\nStatus: RUNNING",
    "style": "green"  # Optional: "cyan" (default), "green", "red", "yellow"
}
```

**Output:**
```
╭─────────── Deployment Summary ───────────╮
│ App: myapp                               │
│ URL: myapp.hop3.example.com              │
│ Status: RUNNING                          │
╰──────────────────────────────────────────╯
```

**Use for:**
- Important summaries
- Grouped information
- Highlighted messages

#### 8. `table` - Tabular Data
Data displayed in a formatted table.

```python
{
    "t": "table",
    "headers": ["Application", "Status", "URL"],
    "rows": [
        ["app1", "RUNNING", "app1.hop3.example.com"],
        ["app2", "STOPPED", "app2.hop3.example.com"],
    ]
}
```

**Output:**
```
┏━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Application ┃ Status  ┃ URL                    ┃
┡━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━┩
│ app1        │ RUNNING │ app1.hop3.example.com  │
│ app2        │ STOPPED │ app2.hop3.example.com  │
└─────────────┴─────────┴────────────────────────┘
```

**Use for:**
- List commands (apps, backups, services)
- Status displays
- Any tabular data

### Message Type Guidelines

**When to use each type:**

| Situation | Type | Example |
|-----------|------|---------|
| Operation succeeded | `success` | "Backup created successfully" |
| Operation failed | `error` | "Failed to create backup: disk full" |
| Non-fatal issue | `warning` | "No Procfile found, using defaults" |
| Helpful information | `info` | "Backup will include all environment variables" |
| Long operation | `progress` | "Uploading files..." |
| Summary/highlight | `panel` | Deployment summary with URL |
| Lists/status | `table` | List of applications |
| General output | `text` | Command-specific output |

### Example: Complete Command Output

Here is a complete example of a well-formatted command response. Helpers exist in `hop3.commands._response` for the common types (`text`, `success`, `error`, `warning`, `table`, `code`, `summary`, `data`, `blob`, `log_entry`, `stream`). Types without a helper (`info`, `progress`, `panel`) are emitted as literal dictionaries.

```python
from hop3.commands._response import success, error

def backup_create(app_name: str) -> list:
    """Create a backup of an application."""
    try:
        # Show progress
        messages = [
            {"t": "progress", "text": f"Creating backup for '{app_name}'..."},
        ]

        # Perform backup operations...
        backup_id = perform_backup(app_name)

        # Success message
        messages.append(success("Backup created successfully"))

        # Summary panel
        messages.append({
            "t": "panel",
            "title": "Backup Details",
            "text": f"Backup ID: {backup_id}\nSize: 2.3 MB\nDuration: 1.2s",
            "style": "green"
        })

        # Info about restoration
        messages.append({
            "t": "info",
            "text": f"To restore: hop3 backup restore {backup_id}"
        })

        return messages

    except Exception as e:
        return [error(f"Failed to create backup: {e}")]
```

### JSON Output Mode

When `--json` flag is used, all message types are collected and output as JSON:

```json
[
  {"t": "progress", "text": "Creating backup for 'myapp'..."},
  {"t": "success", "text": "Backup created successfully"},
  {
    "t": "panel",
    "title": "Backup Details",
    "text": "Backup ID: 123\nSize: 2.3 MB",
    "style": "green"
  }
]
```

**Guidelines for JSON mode:**

All message types are preserved in JSON. Scripts can parse the `"t"` field to filter message types. Errors are still included in the JSON array. JSON output is always valid JSON (no partial output).

### Quiet Mode Behavior

In quiet mode (`--quiet`), most message types are suppressed. Only errors are shown, to ensure critical failures are never silently ignored.

| Type | Shown in Quiet Mode? |
|------|---------------------|
| `error` | ✓ Yes (always shown) |
| `success` | ✗ No |
| `warning` | ✗ No |
| `info` | ✗ No |
| `progress` | ✗ No |
| `panel` | ✗ No |
| `table` | ✗ No |
| `text` | ✗ No |

### Implementation Reference

The message type system is implemented in:
- **Server:** `packages/hop3-server/src/hop3/commands/_response.py` - Response builder helpers
- **CLI:** `packages/hop3-cli/src/hop3_cli/ui/rich_printer.py` - Message rendering

**Key components:**
- `RichPrinter` - Renders messages with the Rich library
- `text()`, `success()`, `error()`, `warning()`, `table()`, ... - Build individual response items
- A command's `call()` method returns a plain `list` of these items

### Testing Message Types

When writing tests for commands, verify message types:

```python
def test_backup_create_success():
    """Test backup creation shows correct messages."""
    messages = backup_create("myapp")

    # Check for progress message
    assert any(msg["t"] == "progress" for msg in messages)

    # Check for success message
    assert any(msg["t"] == "success" for msg in messages)

    # Check for panel with details
    panels = [msg for msg in messages if msg["t"] == "panel"]
    assert len(panels) == 1
    assert "Backup ID" in panels[0]["text"]
```

### Best Practices

1. **Be consistent:** Use the same message types for similar operations across commands
2. **Use appropriate types:** Don't use `error` for warnings or `success` for info
3. **Provide context:** Include relevant details in messages (IDs, filenames, etc.)
4. **Test both modes:** Verify output works correctly in both text and JSON modes
5. **Respect quiet mode:** Only show errors in quiet mode unless necessary
6. **Use tables for lists:** Lists of items should use the `table` type
7. **Group related info:** Use `panel` to group related information together
8. **Show progress:** Use `progress` type for operations that take >1 second

## Community and Conduct

Hop3 commits to fostering an inclusive and welcoming community. All contributors adhere to our Code of Conduct, which outlines our expectations for behavior within our community. Respect, collaboration, and constructive communication are key to our community's health and success.

## Questions and Support

If you have questions or need help with your contributions, ask the Hop3 community. Open an issue for questions related to contributing, or seek help on our community forums or chat channels.

Thank you for contributing to Hop3!
