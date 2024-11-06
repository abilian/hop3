.PHONY: all develop test lint clean doc format
.PHONY: clean clean-build clean-pyc clean-test coverage dist docs install lint lint/flake8

PKG:=hop3,hop3_agent,hop3_server,hop3_web,hop3_lib

# For tests
# Either uncomment and set the following variables or set them in the environment
# HOP3_DEV_HOST=XXX

all: lint test

#
#
#
## Cleanup repository
clean:
	bash -c "shopt -s globstar && rm -f **/*.pyc"
	find . -type d -empty -delete
	rm -rf *.egg-info *.egg .coverage .eggs .cache .mypy_cache .pyre \
		.pytest_cache .pytest .DS_Store  docs/_build docs/cache docs/tmp \
		dist build pip-wheel-metadata junit-*.xml htmlcov coverage.xml \
		tmp
	rm -rf */dist
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
	uv build packages/hop3-agent
	uv run pyinfra -y --user root ${HOP3_DEV_HOST} installer/install-hop.py

#
# Setup
#

## Install development dependencies and pre-commit hook (env must be already activated)
develop: install-deps activate-pre-commit configure-git
install: install-deps

install-deps:
	@echo "--> Installing dependencies"
	uv venv
	uv sync --inexact
	uv run invoke install

activate-pre-commit:
	@echo "--> Activating pre-commit hook"
	pre-commit install

configure-git:
	@echo "--> Configuring git"
	git config branch.autosetuprebase always


## Update dependencies
update-deps:
	uv sync -U
	pre-commit autoupdate

#
# testing & checking
#
.PHONY: test test-randomly test-with-coverage test-with-typeguard clean-test lint audit

## Run python tests
test:
	@echo "--> Running Python tests"
	pytest -x -p no:randomly
	@echo ""

test-e2e:
	@echo "--> Running e2e tests"
	make clean-and-deploy
	hop-test
	@echo ""

test-randomly:
	@echo "--> Running Python tests in random order"
	pytest
	@echo ""

test-with-coverage:
	@echo "--> Running Python tests"
	pytest --cov=. --cov-report term-missing
	@echo ""

test-with-typeguard:
	@echo "--> Running Python tests with typeguard"
	pytest --typeguard-packages=${PKG}
	@echo ""

## Cleanup tests artifacts
clean-test: ## remove test and coverage artifacts
	rm -fr .tox/
	rm -f .coverage
	rm -fr htmlcov/
	rm -fr .pytest_cache

## Lint / check typing
lint:
	ruff check packages
	pyright packages/hop3-agent/src
	# mypy TODO
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
	ruff format src */src tests */tests
	ruff check --fix src */src tests */tests
	markdown-toc -i README.md

## Format / beautify apps
format-apps:
	bash -c "shopt -s globstar && gofmt -w apps/**/*.go"
	bash -c "shopt -s globstar && prettier -w apps/**/*.js"


## Add copyright mention
add-copyright:
	bash -c 'shopt -s globstar && reuse annotate --copyright "Copyright (c) 2023-2024, Abilian SAS" \
		tests/**/*.py src/**/*.py */src/**/*.py */tests/**/*.py'

#
# Everything else
#
.PHONY: help install doc doc-html doc-pdf clean tidy update-deps publish

help:
	adt help-make

doc: doc-html doc-pdf

doc-html:
	sphinx-build -W -b html docs/ docs/_build/html

doc-pdf:
	sphinx-build -W -b latex docs/ docs/_build/latex
	make -C docs/_build/latex all-pdf


## Cleanup harder
tidy: clean
	rm -rf .nox .tox .venv
	rm -rf */.tox */.nox */.venv
	rm -rf node_modules
