# This Justfile is currently experimental.
# We're keeping the make-based workflow for now, but we're also trying to
# improve it with Just, eventually.
# Variables

PKG := "hop3,hop3_agent,hop3_server,hop3_web,hop3_lib"

# Default recipe
default: lint test

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

# Update dependencies
update-deps:
    uv sync -U
    uv run pre-commit autoupdate
    uv pip list --outdated

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
    echo "--> Running e2e tests"
    just clean-and-deploy
    uv run hop-test
    echo ""

test-with-coverage:
    echo "--> Running Python tests"
    uv run pytest --cov=. --cov-report term-missing
    echo ""

test-with-typeguard:
    echo "--> Running Python tests with typeguard"
    uv run pytest --typeguard-packages={{ PKG }}
    echo ""

# Lint / check typing
lint:
    # We keep 'make lint' in the Makefile for now, because it's used in CI.
    make lint

audit:
    # We're using `nox` to run the audit tools because we don't want
    # the dependencies of the audit tools to be installed in the main
    # environment.
    nox -e audit

# Formatting
format:
    uv run ruff format packages/*/src packages/*/tests
    uv run ruff check --fix packages/*/src packages/*/tests
    uv run markdown-toc -i README.md

format-apps:
    bash -c "shopt -s globstar && gofmt -w apps/**/*.go"
    bash -c "shopt -s globstar && prettier -w apps/**/*.js"

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
    rm -rf */dist
    rm -rf .nox
    rm -rf site
    adt clean

# Cleanup harder
tidy: clean
    rm -rf .nox .tox .venv
    bash -c "shopt -s globstar && rm -rf **/.tox **/.nox"
    rm -rf node_modules

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
    echo "--> Deploying"
    just clean
    uv build packages/hop3-agent
    uv run pyinfra -y --user root ${HOP3_DEV_HOST} installer/install-hop.py
