.PHONY: all develop test lint clean doc format
.PHONY: clean clean-build clean-pyc clean-test coverage dist docs install lint lint/flake8

# For tests
# Either uncomment and set the following variables or set them in the environment
# HOP3_DEV_HOST=XXX

all: lint test

#
#
#
## Cleanup repository
clean:
	rm -f **/*.pyc
	find . -type d -empty -delete
	rm -rf *.egg-info *.egg .coverage .eggs .cache .mypy_cache .pyre \
		.pytest_cache .pytest .DS_Store  docs/_build docs/cache docs/tmp \
		dist build pip-wheel-metadata junit-*.xml htmlcov coverage.xml \
		tmp
	-fish -c "rm -rf */dist"
	adt clean

clean-and-deploy:
	make clean-server
	make deploy

clean-server:
	echo "--> Cleaning server (warning: this removes everything)"
	-ssh root@${HOP3_DEV_HOST} apt-get purge -y nginx nginx-core nginx-common
	ssh root@${HOP3_DEV_HOST} rm -rf /home/hop3 /etc/nginx

deploy:
	echo "--> Deploying"
	@make clean
	cd hop3-agent && poetry build
	poetry run pyinfra -y --user root ${HOP3_DEV_HOST} installer/install-hop.py

#
# Setup
#

## Install development dependencies and pre-commit hook (env must be already activated)
develop: install-deps activate-pre-commit configure-git

install-deps:
	@echo "--> Installing dependencies"
	uv venv
	uv pip install -U pip setuptools wheel
	uv pip install -e .
	poetry install

activate-pre-commit:
	@echo "--> Activating pre-commit hook"
	pre-commit install

configure-git:
	@echo "--> Configuring git"
	git config branch.autosetuprebase always


#
# testing & checking
#
.PHONY: test test-randomly test-with-coverage test-with-typeguard clean-test lint audit

## Run python tests
test:
	@echo "--> Running Python tests"
	pytest -x -p no:randomly src tests
	@echo ""

test-e2e:
	@echo "--> Running e2e tests"
	make clean-and-deploy
	hop-test
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

## Cleanup tests artifacts
clean-test: ## remove test and coverage artifacts
	rm -fr .tox/
	rm -f .coverage
	rm -fr htmlcov/
	rm -fr .pytest_cache

## Lint / check typing
lint:
	fish -c "ruff check */src tests */tests"
	# mypy --show-error-codes src
	# pyright src
	reuse lint -q


# Alt
#lint:
#	ruff src tests/test*.py
#	mypy --show-error-codes src
#	flake8 src tests/test*.py
#	# python -m pyanalyze --config-file pyproject.toml src
#	lint-imports
#	make hadolint
#	vulture --min-confidence 80 src
#	deptry . --extend-exclude .nox --extend-exclude .tox
#	# TODO later
#	# mypy --check-untyped-defs src


## Run a security audit
audit:
	pip-audit
	safety check


#
# Formatting
#
.PHONY: format

## Format / beautify code
format:
	# docformatter -i -r src
	fish -c "black src */src tests */tests"
	fish -c "isort src */src tests */tests"
	fish -c "ruff format src */src tests */tests"
	markdown-toc -i README.md

## Format / beautify apps
format-apps:
	@echo "You need the Fish shell to run the following commands:"
	fish -c "gofmt -w apps/**/*.go"
	fish -c "prettier -w apps/**/*.js"


## Add copyright mention
add-copyright:
	fish -c 'reuse annotate --copyright "Copyright (c) 2023-2024, Abilian SAS" \
		tests/**/*.py src/**/*.py */src/**/*.py */tests/**/*.py'

#
# Everything else
#
.PHONY: help install doc doc-html doc-pdf clean tidy update-deps publish

help:
	adt help-make

install:
	poetry install

doc: doc-html doc-pdf

doc-html:
	sphinx-build -W -b html docs/ docs/_build/html

doc-pdf:
	sphinx-build -W -b latex docs/ docs/_build/latex
	make -C docs/_build/latex all-pdf


## Cleanup harder
tidy: clean
	rm -rf .nox .tox
	-fish -c 'rm -rf */.tox'
	-fish -c 'rm -rf */.nox'
	rm -rf node_modules
	rm -rf instance

## Update dependencies
update-deps:
	pip install -U pip setuptools wheel
	poetry update
	pre-commit autoupdate
	poetry show -o

## Publish to PyPI
publish: clean
	git push
	git push --tags
	poetry build
	twine upload dist/*
