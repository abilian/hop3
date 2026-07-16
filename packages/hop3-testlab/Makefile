PKG:=hop3_testlab

.PHONY: all check test test-cov lint format clean build publish

## Default: run lint and test
all: lint test

check: lint

## Run tests
test:
	uv run pytest

## Run tests with coverage
test-cov:
	uv run pytest --cov=$(PKG) --cov-report=html --cov-report=term tests

## Lint and type-check
lint:
	uv run ruff check src tests
	uv run ruff format --check src tests
	uv run pyrefly check src

## Format code
format:
	uv run ruff format src tests
	uv run ruff check --fix src tests

## Cleanup
clean:
	rm -rf .pytest_cache .ruff_cache dist build __pycache__ .mypy_cache \
		.coverage htmlcov .coverage.* *.egg-info
	adt clean

## Build wheel + sdist
build: clean
	uv build

## Publish to PyPI
publish: build
	uv publish
