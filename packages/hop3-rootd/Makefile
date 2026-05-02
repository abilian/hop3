PKG:=hop3_rootd

## Default: run lint and test
all: lint test

#
# testing & checking
#

## Run unit tests (no privileges needed)
test:
	@echo "--> Running Python unit tests"
	pytest -x -p no:randomly tests/a_unit
	@echo ""

## Run integration tests (requires root + nftables)
test-integration:
	@echo "--> Running integration tests (requires root)"
	pytest -x tests/b_integration
	@echo ""

test-with-coverage:
	@echo "--> Running tests with coverage"
	pytest --cov $(PKG) tests/a_unit
	@echo ""


## Lint / check typing
lint:
	ruff check


## Format
format:
	ruff format
	ruff check --fix
	ruff format

.PHONY: all test test-integration test-with-coverage lint format
