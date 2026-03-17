# Hop3 Contribution Guidelines

If you're reading this, this means that you're interested in contributing to Hop3, and this alone makes us happy! Your contributions will help make Hop3 a better platform and strengthen the open source community around it.

To ensure a smooth collaboration process for everyone involved, we've established some guidelines for contributing to the project.

## Getting Started

Before you start, it's important to familiarize yourself with Hop3's core values and objectives. Please take a moment to read the [core values of Hop3](core-values.md) document. Understanding these principles will help you make meaningful contributions that align with the project's goals.

## Contribution Process

### 1. Open an Issue

If you've identified a bug, have a feature suggestion, or have any question, start by opening an issue. Describe the bug, feature, or question in detail, providing as much context as possible. This helps us understand your concern or proposal and address it effectively.

### 2. Fork and Clone the Repository

Once you're ready to work on an issue, fork the Hop3 repository to your GitHub account and clone it to your local development environment. This will allow you to work on the code changes on your machine.

### 3. Create a New Branch

For each set of changes, create a new branch in your forked repository. Use a descriptive name for your branch that reflects the changes you intend to make.

### Guidelines for Contributions

- **Small and Focused Pull Requests (PRs)**: Please ensure your PRs are focused on a single issue or feature request. Avoid including unrelated changes, as this makes it harder to review and merge your contributions.

- **Code Style**: Follow the project's coding style. For Python code, we adhere to PEP8 guidelines, except where explicitly stated otherwise. When importing functions, prefer to import them directly (e.g., `from os.path import abspath`) rather than importing the entire module.

- **Write Meaningful Commit Messages**: Your commit messages should clearly describe what changes have been made and why. This helps maintainers understand the purpose of your changes and speeds up the review process.

- **Update Documentation**: If your changes require updates to the documentation, include those in your PR. Accurate and up-to-date documentation is crucial for users and contributors.

- **Testing**: Include tests for your changes to ensure that the new code works as expected and does not break existing functionality. Add new tests if you're introducing new features or fixing bugs. See the [Testing](#testing) section below for detailed requirements.

- **Review Process**: After submitting your PR, one of the project maintainers will review your changes. Be open to feedback and be prepared to make adjustments to your code. The review process is a collaborative effort, and constructive dialogue is welcome.

### 4. Submitting Your Pull Request

Once you've completed your changes, pushed them to your fork, and ensured they align with the contribution guidelines, you're ready to submit a pull request to the main Hop3 repository. In your PR, provide a clear description of the changes and reference any related issues.

## Testing

Hop3 uses a comprehensive four-layer testing strategy. All contributions should include appropriate tests.

### Test Requirements

**For Bug Fixes:**
- Add a test that reproduces the bug (should fail before your fix)
- Verify the test passes after your fix
- Add tests at the appropriate layer (usually unit or integration)

**For New Features:**
- Add unit tests for new functions/classes
- Add integration tests for component interactions
- Add system tests if the feature involves CLI commands
- Add E2E tests if the feature involves complete workflows

### Running Tests

Before submitting a PR, ensure all tests pass:

```bash
# Quick tests (unit + integration) - run before every commit
pytest packages/hop3-server/tests/a_unit/ packages/hop3-server/tests/b_integration/

# System tests - run before pushing
pytest packages/hop3-server/tests/c_system/

# All tests (takes longer)
pytest
```

### Test Layers

1. **Unit Tests** (`tests/a_unit/`): Fast, isolated tests of individual functions
   - No external dependencies
   - Mock all I/O operations
   - Should run in < 1 second

2. **Integration Tests** (`tests/b_integration/`): Component interaction tests
   - Uses in-memory database
   - Uses Starlette TestClient
   - Should run in ~10 seconds

3. **System Tests** (`tests/c_system/`): CLI ↔ Server communication tests
   - **Requires Docker**
   - Tests use isolated Docker containers
   - Should run in ~20 seconds (after initial image build)

4. **E2E Tests** (`tests/d_e2e/`): Complete workflow tests
   - **Requires Docker**
   - Tests real application deployments
   - Should run in 10-20 minutes

### Docker Requirement

System and E2E tests require Docker to be installed and running:

```bash
# Check Docker is installed
docker --version

# Check Docker daemon is running
docker ps
```

If you don't have Docker installed:
- **macOS**: Install [Docker Desktop](https://www.docker.com/products/docker-desktop)
- **Linux**: Install via your package manager (e.g., `apt install docker.io`)
- **Windows**: Install [Docker Desktop](https://www.docker.com/products/docker-desktop)

### Test Environment Setup

```bash
# Install test dependencies
uv sync --dev

# Ensure HOP3_DEV_HOST is not set (for Docker-based testing)
unset HOP3_DEV_HOST

# Run tests
pytest
```

### Writing Tests

Follow these guidelines when writing tests:

1. **Place tests in the correct layer**: Unit tests for isolated functions, integration tests for component interactions, etc.

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

System and E2E tests run in Docker containers with `HOP3_UNSAFE=true` to bypass authentication. This is **only** safe because:
- Tests run in completely isolated Docker containers
- Containers are destroyed after tests complete
- Containers are not exposed to any network

**Never** use `HOP3_UNSAFE` outside of isolated test containers. See the [Security Policy](../../policies/security-policy.md#hop3_unsafe-mode) for more details.

### Additional Testing Resources

For comprehensive testing documentation, see:
- [Testing Strategy](./testing-strategy.md) - Complete testing guide
- [Testing Documentation](./testing.md) - Quick reference
- [TEST-STATUS.md](/notes/test-status.md) - Current test status

## Continuous Integration

Hop3 uses GitHub Actions for continuous integration. All pull requests must pass CI checks before being merged.

### CI Workflows

**Main Test Workflow** (`.github/workflows/test.yml`):
- Runs on every push and pull request to `main` and `devel` branches
- Tests on Python 3.12 and 3.13
- Includes:
  - Unit tests
  - Integration tests
  - CLI tests
  - Linting (Ruff)
  - Dependency health checks
  - Security scanning (pip-audit, safety)
  - Code coverage reporting

**E2E Test Workflow** (`.github/workflows/e2e.yml`):
- Runs on schedule (nightly at 2 AM UTC)
- Runs on manual trigger
- Runs on pushes to `main` (but not PRs to keep CI times reasonable)
- Includes:
  - E2E tests with Docker
  - System tests with Docker
  - Log artifact upload for debugging

### Viewing CI Results

After submitting a PR:
1. Wait for CI checks to complete (usually 5-10 minutes for main tests)
2. Check the "Checks" tab on your PR to see results
3. If tests fail, click on the failed check for detailed logs
4. Fix any issues and push new commits (CI will automatically re-run)

### Running CI Checks Locally

Before submitting a PR, you can run the same checks locally:

```bash
# Run the same checks as CI
make lint          # Linting
make test          # Unit + integration tests
pytest packages/hop3-server/tests/d_e2e  # E2E tests (slow)

# Code coverage (like CI)
pytest --cov=hop3 --cov-report=term-missing \
  packages/hop3-server/tests/a_unit \
  packages/hop3-server/tests/b_integration \
  packages/hop3-cli/tests
```

### Coverage Requirements

Code coverage is tracked and reported by CI. While we don't enforce strict coverage requirements, we expect:
- New features to include tests that cover the main code paths
- Bug fixes to include regression tests
- Coverage not to decrease significantly with new changes

Coverage reports are uploaded to Codecov and available as artifacts on the GitHub Actions run.

## CLI Message Types and Rich Output

When developing CLI commands or modifying server responses, follow these message type conventions for consistent, user-friendly output.

### Message Format

All CLI output is formatted as a list of message dictionaries. Each message has a `"t"` (type) field that determines how it's rendered:

```python
from hop3.core.result import ok

# Return a list of messages
return ok([
    {"t": "success", "text": "Operation completed successfully"},
    {"t": "table", "headers": ["App", "Status"], "rows": [["myapp", "RUNNING"]]},
])
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

Here's a complete example of a well-formatted command response:

```python
from hop3.core.result import ok

def backup_create(app_name: str) -> dict:
    """Create a backup of an application."""
    try:
        # Show progress
        messages = [
            {"t": "progress", "text": f"Creating backup for '{app_name}'..."},
        ]

        # Perform backup operations...
        backup_id = perform_backup(app_name)

        # Success message
        messages.append({
            "t": "success",
            "text": "Backup created successfully"
        })

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
            "text": f"To restore: hop3 backup:restore {backup_id}"
        })

        return ok(messages)

    except Exception as e:
        return ok([{
            "t": "error",
            "text": f"Failed to create backup: {e}"
        }])
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
- All message types are preserved in JSON
- Scripts can parse the `"t"` field to filter message types
- Errors are still included in the JSON array
- JSON output is always valid JSON (no partial output)

### Quiet Mode Behavior

In quiet mode (`--quiet`), most message types are suppressed:

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

**Design rationale:** Only errors are shown in quiet mode to ensure critical failures are never silently ignored.

### Implementation Reference

The message type system is implemented in:
- **Server:** `packages/hop3-server/src/hop3/core/result.py` - Result helpers
- **CLI:** `packages/hop3-cli/src/hop3_cli/rich_printer.py` - Message rendering

**Key classes:**
- `RichPrinter` - Renders messages with Rich library
- `ok()` function - Creates successful result with messages
- `error()` function - Creates error result with messages

### Testing Message Types

When writing tests for commands, verify message types:

```python
def test_backup_create_success():
    """Test backup creation shows correct messages."""
    result = backup_create("myapp")

    assert result["status"] == "success"
    messages = result["data"]

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
5. **Respect quiet mode:** Only show errors in quiet mode unless absolutely necessary
6. **Use tables for lists:** Lists of items should use `table` type, not multiple `text` messages
7. **Group related info:** Use `panel` to group related information together
8. **Show progress:** Use `progress` type for operations that take >1 second

## Community and Conduct

Hop3 is committed to fostering an inclusive and welcoming community. We expect all contributors to adhere to our Code of Conduct, which outlines our expectations for behavior within our community. Respect, collaboration, and constructive communication are key to our community's health and success.

## Questions and Support

If you have any questions or need help with your contributions, don't hesitate to reach out to the Hop3 community. You can open an issue for questions related to contributing or seek help on our community forums or chat channels.

Thank you for contributing to Hop3! Your efforts will help make Hop3 stronger and more successful.
