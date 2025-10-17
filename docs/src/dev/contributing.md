# Hop3 Contribution Guidelines

If you're readning this, this means that you're interested in contributing to Hop3, and this alone makes us happy! Your contributions will help make Hop3 a better platform and strengthen the open source community around it.

To ensure a smooth collaboration process for everyone involved, we've established some guidelines for contributing to the project.

## Getting Started

Before you start, it's important to familiarize yourself with Hop3's core values and objectives. Please take a moment to read the [core values of Hop3](../README.md#core-values) outlined in our README. Understanding these principles will help you make meaningful contributions that align with the project's goals.

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
- [TEST-STATUS.md](/TEST-STATUS.md) - Current test status

## Community and Conduct

Hop3 is committed to fostering an inclusive and welcoming community. We expect all contributors to adhere to our Code of Conduct, which outlines our expectations for behavior within our community. Respect, collaboration, and constructive communication are key to our community's health and success.

## Questions and Support

If you have any questions or need help with your contributions, don't hesitate to reach out to the Hop3 community. You can open an issue for questions related to contributing or seek help on our community forums or chat channels.

Thank you for contributing to Hop3! Your efforts will help make Hop3 stronger and more successful.
