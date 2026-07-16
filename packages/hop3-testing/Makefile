PKG:=hop3_testing

.PHONY: all develop install-deps activate-pre-commit configure-git update-deps

all: lint test

#
# Setup
#

## Install development dependencies and pre-commit hook (env must be already activated)
develop: install-deps activate-pre-commit configure-git

install-deps:
	@echo "--> Installing dependencies"
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
.PHONY: test test-cov lint format

## Run tests
test:
	uv run pytest

## Run tests with coverage
test-cov:
	uv run pytest --cov=$(PKG) --cov-report term-missing

## Lint and type-check
lint:
	uv run ruff check src tests
	uv run ruff format --check src tests
	uv run pyrefly check src

## Format code
format:
	uv run ruff format src tests
	uv run ruff check --fix src tests

#
# Everything else
#
.PHONY: help clean tidy publish release

help:
	adt help-make

## Cleanup repository
clean:
	adt clean
	rm -f **/*.pyc
	find . -type d -empty -delete
	rm -rf *.egg-info *.egg .coverage .eggs .cache .mypy_cache .pyre \
		.pytest_cache .pytest .DS_Store  docs/_build docs/cache docs/tmp \
		dist build pip-wheel-metadata junit-*.xml htmlcov coverage.xml

## Cleanup harder
tidy: clean
	rm -rf .nox
	rm -rf node_modules
	rm -rf instance

## Publish to PyPI
publish: clean
	git push
	git push --tags
	uv build
	twine upload dist/*

## Tag release and publish
release: clean
	adt bump-version
	git push
	git push --tags
	uv build
	twine upload dist/*
