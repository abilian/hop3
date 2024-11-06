.PHONY: all develop test lint clean doc format
.PHONY: clean clean-build clean-pyc clean-test coverage dist docs install lint lint/flake8

# For tests
# Either uncomment and set the following variables or set them in the environment
# HOP3_DEV_HOST=XXX

all: lint test

#
#
#
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
	poetry build
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
.PHONY: format

## Format / beautify code
format:
	# docformatter -i -r src
	adt format
	ruff format src


## Add copyright mention
add-copyright:
	bash -c 'shopt -s globstar && reuse annotate --copyright "Copyright (c) 2023-2024, Abilian SAS" src/**/*.py tests/**/*.py'

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
