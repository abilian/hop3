PKG:=hop3

.PHONY: all develop install-deps activate-pre-commit configure-git update-deps

# For tests
# Either uncomment and set the following variables or set them in the environment
# HOP3_DEV_HOST=XXX

all: lint test

#
# Setup
#

## Install development dependencies and pre-commit hook (env must be already activated)
develop: install-deps activate-pre-commit configure-git

install-deps:
	@echo "--> Installing dependencies"
	uv venv
	uv sync

activate-pre-commit:
	@echo "--> Activating pre-commit hook"
	pre-commit install

configure-git:
	@echo "--> Configuring git"
	git config branch.autosetuprebase always

## Update dependencies
update-deps:
	uv sync -U

#
# testing & checking
#
.PHONY: test test-e2e test-cov clean-test lint audit format

## Run tests
test:
	uv run pytest

## Run e2e tests
test-e2e:
	@echo "--> Running e2e tests"
	make clean-and-deploy
	hop3-test
	@echo ""

## Run tests with coverage
test-cov:
	uv run pytest --cov=$(PKG) --cov-report term-missing

## Cleanup tests artifacts
clean-test:
	rm -fr .tox/
	rm -f .coverage
	rm -fr htmlcov/
	rm -fr .pytest_cache

## Lint and type-check
lint:
	uv run ruff check src tests
	uv run ruff format --check src tests
	uv run pyrefly check src

## Run a security audit
audit:
	uvx pip-audit
	safety check

## Format code
format:
	uv run ruff format src tests
	uv run ruff check --fix src tests

## Add copyright mention
add-copyright:
	bash -c 'shopt -s globstar && reuse annotate --copyright "Copyright (c) 2023-2024, Abilian SAS" src/**/*.py tests/**/*.py'

#
# Everything else
#
.PHONY: add-copyright help install doc doc-html doc-pdf clean tidy publish

help:
	adt help-make

install:
	uv sync

doc: doc-html doc-pdf

doc-html:
	sphinx-build -W -b html docs/ docs/_build/html

doc-pdf:
	sphinx-build -W -b latex docs/ docs/_build/latex
	make -C docs/_build/latex all-pdf

## Cleanup repository
clean:
	rm -f **/*.pyc
	find . -type d -empty -delete
	rm -rf *.egg-info *.egg .coverage .eggs .cache .mypy_cache .pyre \
		.pytest_cache .pytest .DS_Store  docs/_build docs/cache docs/tmp \
		dist build pip-wheel-metadata junit-*.xml htmlcov coverage.xml \
		tmp
	adt clean

## Cleanup harder
tidy: clean
	rm -rf .nox .tox
	rm -rf node_modules
	rm -rf instance

## Publish to PyPI
publish: clean
	git push
	git push --tags
	uv build
	twine upload dist/*
