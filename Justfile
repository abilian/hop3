# This Justfile is currently experimental.
# We're keeping the make-based workflow for now, but we're also trying to
# improve it with Just, eventually.
# Variables

PKG := "hop3,hop3_agent,hop3_server,hop3_web,hop3_lib"

# Default recipe
default: test lint
all: default

# Setup
develop: install-deps activate-pre-commit configure-git

install: install-deps

install-deps:
    echo "--> Installing dependencies"
    uv sync

activate-pre-commit:
    echo "--> Activating pre-commit hook"
    uv run pre-commit install

configure-git:
    echo "--> Configuring git"
    git config branch.autosetuprebase always

# Check development environment
check-dev-env:
    python3 scripts/check-dev-env.py

# Update dependencies
update-deps:
    echo "--> Updating dependencies"
    uv sync -U
    uv run pre-commit autoupdate
    uv pip list --outdated
    uv pip list --format=freeze > compliance/requirements-full.txt

# Generate Software Bill of Materials (SBOM) from venv for CRA compliance
generate-sbom:
    echo "--> Generating SBOM (assuming syft is installed)"
    just clean
    rm -rf .venv
    uv sync -q --no-dev
    uv pip list --format=freeze > compliance/requirements-prod.txt
    syft .venv \
        -o spdx-json=compliance/sbom-spdx.json \
        -o cyclonedx-json=compliance/sbom-cyclonedx.json \
        -o syft-text=compliance/sbom-syft.txt
    npx prettier -w compliance/sbom-spdx.json
    npx prettier -w compliance/sbom-cyclonedx.json
    uv sync -q

# Testing & checking
test:
    echo "--> Running Python tests"
    uv run pytest
    echo ""

test-randomly:
    @echo "--> Running Python tests in random order"
    uv run pytest --random-order
    @echo ""

test-e2e:
    echo "--> Running e2e tests (legacy)"
    just clean-and-deploy
    uv run hop-test
    echo ""

test-system:
    echo "--> Running system integration tests"
    echo "This requires a running hop3-server (local or HOP3_DEV_HOST)"
    uv run pytest packages/hop3-server/tests/c_system/ -v
    echo ""

test-e2e-cli:
    echo "--> Running full E2E tests (Docker-based)"
    echo "This requires Docker"
    uv run pytest packages/hop3-server/tests/d_e2e/ -v
    echo ""

test-with-coverage:
    echo "--> Running Python tests"
    uv run pytest --cov=hop3 --cov-report term-missing
    echo ""

test-with-typeguard:
    echo "--> Running Python tests with typeguard"
    uv run pytest --typeguard-packages={{ PKG }}
    echo ""

# Lint / check typing
lint:
    uv run ruff check packages/*/src packages/*/tests
    # uv run pyright packages/hop3-server
    # uv run mypy packages/hop3-server
    # uv run reuse lint -q
    cd packages/hop3-server && uv run deptry src
    # vulture --min-confidence 80 packages/hop3-agent/src

audit:
    # We're using `nox` to run the audit tools because we don't want
    # the dependencies of the audit tools to be installed in the main
    # environment.
    nox -e audit

# Formatting
format:
    uv run ruff format packages/*/src packages/*/tests installer
    uv run ruff check --fix packages/*/src packages/*/tests installer
    uv run markdown-toc --maxdepth 3 -i README.md
    python scripts/update-copyright.py

format-apps:
    bash -c "shopt -s globstar && gofmt -w apps/**/*.go"
    bash -c "shopt -s globstar && prettier -w apps/**/*.js"

# Fix using ruff with unsafe fixes
fix:
    uv run ruff check packages/hop3-agent --fix --unsafe-fixes

add-copyright:
    python scripts/update-copyright.py


# Clean up
clean:
    bash -c "shopt -s globstar && rm -f **/*.pyc"
    find . -type d -empty -delete
    rm -rf *.egg-info *.egg .coverage .eggs .cache .mypy_cache .pyre \
    	.pytest_cache .pytest .DS_Store  docs/_build docs/cache docs/tmp \
    	dist build pip-wheel-metadata junit-*.xml htmlcov coverage.xml \
    	tmp
    rm -rf packages/*/dist packages/*/.pdm-build
    rm -rf .nox
    rm -rf site
    adt clean

# Clean test artifacts
clean-test:
    rm -rf .pytest_cache .coverage htmlcov coverage.xml junit-*.xml

# Cleanup harder
tidy: clean
    rm -rf .nox .tox .venv
    bash -c "shopt -s globstar && rm -rf **/.tox **/.nox"
    rm -rf node_modules

# Build & Deployment

# Build the python packages
build:
    just clean
    uv build packages/hop3-server
    uv build packages/hop3-cli

# Run server (in development mode)
serve:
    hop-server serve

# Alias for serve
run: serve

# Documentation
doc:
    duty docs-build

doc-serve:
    duty docs

#
# Used by tests
#

# Clean and deploy the server
clean-and-deploy:
    just clean-server
    just deploy

# Clean the server
clean-server:
    echo "--> Cleaning server (warning: this removes everything)"
    -ssh root@${HOP3_DEV_HOST} apt-get purge -y nginx nginx-core nginx-common
    ssh root@${HOP3_DEV_HOST} rm -rf /home/hop3 /etc/nginx

# Deploy to the server
deploy:
    echo "--> Deploying to ${HOP3_DEV_HOST}"
    uv build packages/hop3-server
    uv run pyinfra -y --user root ${HOP3_DEV_HOST} installer/install-hop.py


# Git tasks
sync-code:
    git pull origin
    @just push-code

push-code:
    git push origin
    git push ci
    git push eclipse
