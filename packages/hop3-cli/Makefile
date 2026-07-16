PKG:=hop3_cli

.PHONY: all test test-cov lint format

## Default: run lint and test
all: lint test

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
