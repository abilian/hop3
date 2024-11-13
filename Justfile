# This Justfile is currently experimental.
# We're keeping the make-based workflow for now, but we're also trying to
# improve it with Just, eventually.
# Variables

PKG := "hop3,hop3_agent,hop3_server,hop3_web,hop3_lib"

# Default recipe
default: lint test

# Cleanup repository
clean:
    bash -c "shopt -s globstar && rm -f **/*.pyc"
    find . -type d -empty -delete
    rm -rf *.egg-info *.egg .coverage .eggs .cache .mypy_cache .pyre \
        .pytest_cache .pytest .DS_Store docs/_build docs/cache docs/tmp \
        dist build pip-wheel-metadata junit-*.xml htmlcov coverage.xml \
        tmp
    rm -rf */dist
    adt clean

clean-and-deploy:
    just clean-server
    just deploy

clean-server:
    echo "--> Cleaning server (warning: this removes everything)"
    -ssh root@${HOP3_DEV_HOST} apt-get purge -y nginx nginx-core nginx-common
    ssh root@${HOP3_DEV_HOST} rm -rf /home/hop3 /etc/nginx

deploy:
    echo "--> Deploying"
    just clean
    uv build packages/hop3-agent
    uv run pyinfra -y --user root ${HOP3_DEV_HOST} installer/install-hop.py

# Setup
develop: install-deps activate-pre-commit configure-git

install: install-deps

install-deps:
    echo "--> Installing dependencies"
    uv venv
    uv sync --inexact
    uv run invoke install

activate-pre-commit:
    echo "--> Activating pre-commit hook"
    pre-commit install

configure-git:
    echo "--> Configuring git"
    git config branch.autosetuprebase always

# Update dependencies
update-deps:
    uv sync -U
    pre-commit autoupdate
    uv pip list --outdated

# Testing & checking
test:
    echo "--> Running Python tests"
    pytest -x -p no:randomly
    echo ""

test-e2e:
    echo "--> Running e2e tests"
    just clean-and-deploy
    hop-test
    echo ""

test-randomly:
    echo "--> Running Python tests in random order"
    pytest
    echo ""

test-with-coverage:
    echo "--> Running Python tests"
    pytest --cov=. --cov-report term-missing
    echo ""

test-with-typeguard:
    echo "--> Running Python tests with typeguard"
    pytest --typeguard-packages={{ PKG }}
    echo ""

clean-test:
    rm -fr .tox/
    rm -f .coverage
    rm -fr htmlcov/
    rm -fr .pytest_cache

# Lint / check typing
lint:
    ruff check packages
    pyright packages/hop3-agent
    mypy packages/hop3-agent
    reuse lint -q
    cd packages/hop3-agent && deptry src
    # vulture --min-confidence 80 packages/hop3-agent/src

audit:
    # We're using `nox` to run the audit tools because we don't want
    # the dependencies of the audit tools to be installed in the main
    # environment.
    nox -e audit

# Formatting
format:
    ruff format packages/*/src packages/*/tests
    ruff check --fix packages/*/src packages/*/tests
    markdown-toc -i README.md

format-apps:
    bash -c "shopt -s globstar && gofmt -w apps/**/*.go"
    bash -c "shopt -s globstar && prettier -w apps/**/*.js"

add-copyright:
    bash -c 'shopt -s globstar && reuse annotate --copyright "Copyright (c) 2023-2024, Abilian SAS" \
        packages/*/src/**/*.py packages/*/tests/**/*.py'

# Documentation
doc: doc-html doc-pdf

doc-html:
    sphinx-build -W -b html docs/ docs/_build/html

doc-pdf:
    sphinx-build -W -b latex docs/ docs/_build/latex
    make -C docs/_build/latex all-pdf

# Cleanup harder
tidy: clean
    rm -rf .nox .tox .venv
    bash -c "shopt -s globstar && rm -rf **/.tox **/.nox"
    rm -rf node_modules

# Publish to PyPI
publish: clean
    git push
    git push --tags
    poetry build
    twine upload dist/*
