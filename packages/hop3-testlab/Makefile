.PHONY: all test build format check lint clean

all: test lint

check: lint

lint:
	uv run --active ruff check
	uv run --active ruff format --check
	uv run --active ty check src
	uv run --active pyrefly check src
	uv run --active mypy src
	# uv run --active mypy --strict src

format:
	uv run --active ruff format src tests
	uv run --active ruff check src tests --fix
	uv run --active ruff format src tests

test:
	uv run pytest

test-cov:
	uv run pytest --cov=hop3-testlab --cov-report=html --cov-report=term tests

clean:
	rm -rf .pytest_cache .ruff_cache dist build __pycache__ .mypy_cache \
		.coverage htmlcov .coverage.* *.egg-info
	adt clean

build: clean
	uv build

publish: build
	uv publish
