.PHONY: all develop test lint clean doc format
.PHONY: clean clean-build clean-pyc clean-test coverage dist docs install lint lint/flake8

PKG:=hop3,hop3_agent,hop3_server,hop3_web,hop3_lib

# For tests
# Either uncomment and set the following variables or set them in the environment
# HOP3_DEV_HOST=XXX

all: test lint


#
# Used by CI
#

## Lint / check typing
lint:
	@echo "--> Linting code"
	uv run ruff check packages/*/src packages/*/tests
	cd packages/hop3-server && uv run deptry src
	@echo ""

## Clean and deploy the server
clean-and-deploy:
	make clean-server
	make deploy

## Clean development server (warning: this removes everything)
clean-server:
	@echo "--> Cleaning server (warning: this removes everything)"
	-ssh root@${HOP3_DEV_HOST} apt-get purge -y nginx nginx-core nginx-common
	ssh root@${HOP3_DEV_HOST} rm -rf /home/hop3 /etc/nginx

## Deploy to development server
deploy:
	@echo "--> Deploying to" ${HOP3_DEV_HOST}
	uv build packages/hop3-server
	uv run pyinfra -y --user root ${HOP3_DEV_HOST} installer/install-hop.py

## Build the python packages
build:
	@make clean
	uv build packages/hop3-server
	uv build packages/hop3-cli

## Run server (in development mode)
serve:
	hop-server serve
	# granian --interface asgi --factory hop3.server.asgi:create_app

## Alias for serve
run: serve

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

## Generate Software Bill of Materials (SBOM) from venv for CRA compliance
generate-sbom:
	@echo "--> Generating SBOM (assuming syft is installed)"
	make clean
	rm -rf .venv
	uv sync -q --no-dev
	uv pip list --format=freeze > compliance/requirements-prod.txt
	syft .venv \
		-o spdx-json=compliance/sbom-spdx.json \
		-o cyclonedx-json=compliance/sbom-cyclonedx.json \
		-o syft-text=compliance/sbom-syft.txt
	npx prettier -w compliance/sbom-spdx.json
	npx prettier -w compliance/sbom-cyclonedx.json
	uv sync -q


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
	@echo "--> Running e2e tests (legacy)"
	make deploy
	hop-test
	@echo ""

test-system:
	@echo "--> Running system integration tests"
	@echo "This requires a running hop3-server (local or HOP3_DEV_HOST)"
	uv run pytest packages/hop3-server/tests/c_system/ -v
	@echo ""

test-e2e-cli:
	@echo "--> Running full E2E tests (Docker-based)"
	@echo "This requires Docker"
	uv run pytest packages/hop3-server/tests/d_e2e/ -v
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
	@echo "--> Running security audit"
	# We're using 'nox' to run the audit tools because we don't want
	# the dependencies of the audit tools to be installed in the main environment.
	nox -e audit
	@echo ""

## Formatting
format:
	@echo "--> Formatting code"
	uv run ruff format packages/*/src packages/*/tests installer
	uv run ruff check --fix packages/*/src packages/*/tests installer
	uv run markdown-toc --maxdepth 3 -i README.md
	python scripts/update-copyright.py
	@echo ""

## Format apps
format-apps:
	@echo "--> Formatting apps"
	bash -c "shopt -s globstar && gofmt -w apps/**/*.go"
	bash -c "shopt -s globstar && prettier -w apps/**/*.js"
	@echo ""

## Fix using ruff
fix:
	ruff check packages/hop3-agent --fix --unsafe-fixes

add-copyright:
	@echo "--> Adding/updating copyright headers"
	python scripts/update-copyright.py
	@echo ""

## Clean up
clean:
	bash -c "shopt -s globstar && rm -f **/*.pyc"
	find . -type d -empty -delete
	rm -rf *.egg-info *.egg .coverage .eggs .cache .mypy_cache .pyre \
		.pytest_cache .pytest .DS_Store  docs/_build docs/cache docs/tmp \
		dist build pip-wheel-metadata junit-*.xml htmlcov coverage.xml \
		tmp
	rm -rf packages/*/dist packages/*/.pdm-build
	rm -rf .nox
	rm -rf site
	adt clean

clean-test:
	@echo "--> Cleaning test artifacts"
	rm -rf .pytest_cache .coverage htmlcov coverage.xml junit-*.xml
	@echo ""

## Documentation
doc:
	duty docs-build

doc-serve:
	duty docs
