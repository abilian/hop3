.PHONY: all develop test lint clean doc format
.PHONY: clean clean-build clean-pyc clean-test coverage dist docs install lint lint/flake8

PKG:=hop3,hop3_agent,hop3_server,hop3_web,hop3_lib

# For tests
# Either uncomment and set the following variables or set them in the environment
# HOP3_DEV_HOST=XXX

all: lint test

#
# Used by CI
#

## Lint / check typing
lint:
	ruff check packages
	pyright packages/hop3-agent
	mypy packages/hop3-agent
	reuse lint -q
	cd packages/hop3-agent && deptry src
	# vulture --min-confidence 80 packages/hop3-agent/src


## Cleanup repository
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
	uv sync --inexact

activate-pre-commit:
	@echo "--> Activating pre-commit hook"
	pre-commit install

configure-git:
	@echo "--> Configuring git"
	git config branch.autosetuprebase always

## Check development environment
check-dev-env:
	python3 scripts/check-dev-env.py

## Update dependencies
update-deps:
	just update-deps

#
# testing & checking
#
.PHONY: test test-randomly test-with-coverage test-with-typeguard clean-test lint audit

# NB: keep tests in the Makefile for now, because if CI.

## Run python tests
test:
	@echo "--> Running Python tests"
	uv run pytest
	@echo ""

test-randomly:
	@echo "--> Running Python tests in random order"
	uv run pytest --random-order
	@echo ""

test-e2e:
	@echo "--> Running e2e tests"
	make clean-and-deploy
	hop-test
	@echo ""

test-with-coverage:
	@echo "--> Running Python tests"
	pytest --cov=hop3 --cov-report term-missing
	@echo ""

test-with-typeguard:
	@echo "--> Running Python tests with typeguard"
	pytest --typeguard-packages=${PKG}
	@echo ""


## Run a security audit
audit:
	just audit

# Delegate to just

add-copyright:
	just add-copyright

## Clean up
clean:
	just clean

clean-test:
	just clean-test

## Default recipe
default:
	just default

## Documentation
doc:
	duty docs-build

doc-serve:
	duty docs

## Formatting
format:
	just format

format-apps:
	just format-apps

## Cleanup harder
tidy:
	just tidy
