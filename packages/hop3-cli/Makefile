PKG:=hop3_cli

## Default: run lint and test
all: lint test

#
# testing & checking
#

## Run python tests
test:
	@echo "--> Running Python tests"
	pytest -x -p no:randomly src tests
	@echo ""

test-randomly:
	@echo "--> Running Python tests in random order"
	pytest tests src
	@echo ""

test-with-coverage:
	@echo "--> Running Python tests"
	py.test --cov $(PKG) tests src
	@echo ""

test-with-typeguard:
	@echo "--> Running Python tests with typeguard"
	pytest --typeguard-packages=${PKG} tests src
	@echo ""


## Lint / check typing
lint:
	ruff check src tests
	ty check src tests


.PHONY: all test test-randomly test-with-coverage test-with-typeguard lint
