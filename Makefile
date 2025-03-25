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
	ruff check packages/hop3-server packages/hop3-cli
	pyright packages/hop3-server
	mypy packages/hop3-server
	reuse lint -q
	cd packages/hop3-server && deptry src
	# vulture --min-confidence 80 packages/hop3-agent/src

## Cleanup repository
clean-and-deploy:
	make clean-server
	make deploy-dev

clean-server:
	@echo "--> Cleaning server (warning: this removes everything)"
	-ssh root@${HOP3_DEV_HOST} apt-get purge -y nginx nginx-core nginx-common
	ssh root@${HOP3_DEV_HOST} rm -rf /home/hop3 /etc/nginx

deploy:
	@echo "Use 'make deploy-dev' or 'make deploy-prod'"

deploy-dev:
	@echo "--> Deploying to" ${HOP3_DEV_HOST}
	@make build
	uv run pyinfra -y --user root ${HOP3_DEV_HOST} installer/install-hop.py

deploy-prod:
	@echo "--> Deploying to" ${HOP3_HOST}
	@make build
	uv run pyinfra -y --user root ${HOP3_HOST} installer/install-hop.py

build:
	@make clean
	uv build packages/hop3-agent

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
	@echo "--> Updating dependencies"
	uv sync -U
	uv run pre-commit autoupdate
	uv pip list --outdated
	uv pip list --format=freeze > compliance/requirements-full.txt

## Generate SBOM
generate-sbom:
	@echo "--> Generating SBOM"
	uv sync -q --no-dev
	uv pip list --format=freeze > compliance/requirements-prod.txt
	uv sync -q
	# CycloneDX
	uv run cyclonedx-py requirements \
		--pyproject pyproject.toml -o compliance/sbom-cyclonedx.json \
		compliance/requirements-prod.txt
	# Add license information
	uv run lbom \
		--input_file compliance/sbom-cyclonedx.json \
		> compliance/sbom-lbom.json
	mv compliance/sbom-lbom.json compliance/sbom-cyclonedx.json
	# broken
	#	# SPDX
	#	sbom4python -r compliance/requirements-prod.txt \
	#		--sbom spdx --format json \
	#		-o compliance/sbom-spdx.json

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
	# uvx pip-audit .
	# uvx safety scan
	just audit

## Formatting
format:
	just format

## Format apps
format-apps:
	just format-apps

## Fix using ruff
fix:
	ruff check packages/hop3-agent --fix --unsafe-fixes

add-copyright:
	just add-copyright

## Clean up
clean:
	bash -c "shopt -s globstar && rm -f **/*.pyc"
	find . -type d -empty -delete
	rm -rf *.egg-info *.egg .coverage .eggs .cache .mypy_cache .pyre \
		.pytest_cache .pytest .DS_Store  docs/_build docs/cache docs/tmp \
		dist build pip-wheel-metadata junit-*.xml htmlcov coverage.xml \
		tmp
	rm -rf */dist
	rm -rf .nox
	rm -rf site
	adt clean

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

## Cleanup harder
tidy:
	just tidy
