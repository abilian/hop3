PKG:=hop3_installer

## Default: run lint and test
all: lint test

#
# testing & checking
#

## Run python tests
test:
	@echo "--> Running Python tests"
	pytest -x -p no:randomly
	@echo ""

test-randomly:
	@echo "--> Running Python tests in random order"
	pytest
	@echo ""

test-with-coverage:
	@echo "--> Running Python tests"
	py.test --cov $(PKG)
	@echo ""

test-with-typeguard:
	@echo "--> Running Python tests with typeguard"
	pytest --typeguard-packages=${PKG}
	@echo ""


## Lint / check typing
lint:
	ruff check
	ty check


## Format
format:
	ruff format
	ruff check --fix
	ruff format

.PHONY: all test test-randomly test-with-coverage test-with-typeguard lint
