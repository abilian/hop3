## Default: run lint and test
all: lint test
.PHONY: all

## Run flak app
run:
	honcho -f Procfile-dev start
.PHONY: run

#
# testing & checking
#
.PHONY: test test-randomly test-with-coverage test-with-typeguard lint audit

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
	# adt check src tests
	ruff check src tests
	# mypy --show-error-codes src
	# pyright src
	reuse lint -q

## Run a security audit
audit:
	pip-audit
	safety check


#
# Formatting
#
.PHONY: format add-copyright

## Format / beautify code
format:
	docformatter -i -r src
	adt format
	ruff format src
	ruff check --fix src

## Add copyright mention
add-copyright:
	bash -c 'shopt -s globstar && reuse annotate --copyright "Copyright (c) 2023-2024, Abilian SAS" src/**/*.py tests/**/*.py'

#
# Everything else
#
.PHONY: help clean tidy

## Help message
help:
	adt help-make

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
