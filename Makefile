.PHONY: all develop test lint clean doc format
.PHONY: clean clean-build clean-pyc clean-test coverage dist docs install lint lint/flake8

# For tests
TARGET_HOST=ssh.hop-dev.abilian.com

all: lint test

#
#
#
clean-and-deploy:
	make clean-server
	make deploy

clean-server:
	echo "--> Cleaning server (warning: this removes everything)"
	-ssh root@${TARGET_HOST} apt purge -y nginx nginx-core nginx-common
	ssh root@${TARGET_HOST} rm -rf /home/hop3 /etc/nginx

deploy:
	echo "--> Deploying"
	@make clean
	poetry build
	poetry run pyinfra --user root ${TARGET_HOST} installer/install-hop.py

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
	pytest -x -p no:randomly
	@echo ""

test-e2e:
	@echo "--> Running e2e tests"
	make clean-and-deploy
	python scripts/run-tests-alt.py
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
	adt format
	@echo "You need the Fish shell to run the following commands:"
	fish -c "gofmt -w apps/**/*.go"
	fish -c "prettier -w apps/**/*.js"


#
# Everything else
#
.PHONY: help install doc doc-html doc-pdf clean tidy update-deps publish

help:
	@inv help-make

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

## Publish to PyPI
publish: clean
	git push
	git push --tags
	poetry build
	twine upload dist/*
