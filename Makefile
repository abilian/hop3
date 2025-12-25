.PHONY: all develop test lint clean doc format
.PHONY: clean clean-build clean-pyc clean-test coverage dist docs install lint lint/flake8
.PHONY: deploy deploy-docker deploy-local deploy-clean deploy-status deploy-teardown
.PHONY: test-installer test-installer-ssh test-installer-docker test-installer-vagrant
.PHONY: test-installer-docker-all test-installer-all-methods test-installer-cleanup build-installers

PKG:=hop3,hop3_agent,hop3_server,hop3_web,hop3_lib

# For tests
# Either uncomment and set the following variables or set them in the environment
# HOP3_DEV_HOST=XXX

all: test lint

#
# Help
#
help:
	adt help-make

#
# Used by CI
#

## Lint / check typing
check: lint

## Lint / check typing
lint:
	@echo "--> Linting code"
	uv run ruff format --check packages/*/src packages/*/tests
	uv run ruff check packages/*/src packages/*/tests
	uv run mypy packages/hop3-server/src
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

## Deploy to development server (set HOP3_DEV_HOST env var)
deploy:
	@echo "--> Deploying to" ${HOP3_DEV_HOST}
	uv run hop3-deploy

## Deploy to local Docker container
deploy-docker:
	@echo "--> Deploying to Docker container"
	uv run hop3-deploy --docker

## Deploy with local code changes
deploy-local:
	@echo "--> Deploying with local code"
	uv run hop3-deploy --local

## Deploy with clean install
deploy-clean:
	@echo "--> Clean deploy to" ${HOP3_DEV_HOST}
	uv run hop3-deploy --clean

## Show deployment target status
deploy-status:
	uv run hop3-deploy --status

## Teardown Docker container
deploy-teardown:
	uv run hop3-deploy --teardown

#
# Installer Testing
#

## Test installers via SSH (requires HOP3_TEST_HOST or --host) and docker
test-installer-all: 
	@make test-installer-ssh
	@make test-installer-docker-all

## Test installers on remote server via SSH
test-installer-ssh: build-installers
	@echo "--> Testing installers via SSH (local code)"
	uv run hop3-test-installers ssh --host ${HOP3_TEST_HOST} --type both --method local
	@echo ""

## Test installers in Docker containers
test-installer-docker: build-installers
	@echo "--> Testing installers in Docker (local code)"
	uv run hop3-test-installers docker --distro ubuntu --type both --method local
	@echo ""

## Test installers in Vagrant VMs
test-installer-vagrant: build-installers
	@echo "--> Testing installers in Vagrant VMs (local code)"
	uv run hop3-test-installers vagrant --vm ubuntu --type both --method local
	@echo ""

## Test installers on all Docker distros
test-installer-docker-all: build-installers
	@echo "--> Testing installers on all Docker distros (local code)"
	uv run hop3-test-installers docker --all --type both --method local
	@echo ""

## Test installers with all methods (pypi, git, local) via SSH
test-installer-all-methods: build-installers
	@echo "--> Testing installers with all methods (pypi, git, local)"
	uv run hop3-test-installers ssh --host ${HOP3_TEST_HOST} --type both --method all
	@echo ""

## Cleanup Docker test containers
test-installer-cleanup:
	@echo "--> Cleaning up Docker test containers"
	uv run hop3-test-installers docker --cleanup
	@echo ""

## Build single-file installers
build-installers:
	@echo "--> Building single-file installers"
	@mkdir -p installer
	uv run hop3-installer-bundle --all --output-dir installer/
	@echo ""


#
# Other packages
#

## Build the python packages
build:
	@make clean
	uv build packages/hop3-server
	uv build packages/hop3-cli

## Run full development stack (web server + uWSGI emperor)
serve:
	hop-server setup
	honcho -f Procfile.dev start

## Alias for serve
dev: serve
run: serve

## Run only the web server (without uWSGI)
serve-web:
	litestar --app asgi:create_app run --debug --reload

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
	uv sync --all-groups -U
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
test: test-full

test-quick:
	@echo "--> Running quick Python tests"
	# uv run pytest -m "not slow and not network"
	uv run pytest -n 2 packages/hop3-server/tests/a_unit
	uv run pytest -n 4 packages/hop3-server/tests/b_integration
	@echo ""

test-full:
	@echo "--> Running full Python tests"
	uv run pytest packages/hop3-server/tests/a_unit
	uv run pytest -n 4 packages/hop3-server/tests/b_integration
	# uv run pytest -q --tb=short packages/hop3-server/tests/c_system
	uv run pytest packages/hop3-server/tests/d_e2e
	uv run pytest packages/hop3-cli/tests
	@echo ""

test-server:
	@echo "--> Running e2e tests against a remote server"
	make deploy
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
	@echo "--> Running security audit"
	# We're using 'nox' to run the audit tools because we don't want
	# the dependencies of the audit tools to be installed in the main environment.
	nox -e audit
	@echo ""

## Formatting
format:
	@echo "--> Formatting code"
	uv run ruff format packages/*/src packages/*/tests
	uv run ruff check --fix packages/*/src packages/*/tests
	@make update-tocs
	python scripts/update-copyright.py
	@echo ""

update-tocs:
	uv run markdown-toc --maxdepth 3 -i README.md
	uv run markdown-toc --maxdepth 3 -i notes/todo/TODO-next.md
	uv run markdown-toc --maxdepth 3 -i notes/todo/TODO-NGI.md
	uv run markdown-toc --maxdepth 3 -i notes/roadmap.md
	uv run markdown-toc --maxdepth 3 -i notes/current-status.md
	uv run markdown-toc --maxdepth 3 -i notes/test-status.md

## Format apps
format-apps:
	@echo "--> Formatting apps"
	bash -c "shopt -s globstar && gofmt -w apps/**/*.go"
	bash -c "shopt -s globstar && prettier -w apps/**/*.js"
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
	rm -rf docs/site
	adt clean

clean-test:
	@echo "--> Cleaning test artifacts"
	rm -rf .pytest_cache .coverage htmlcov coverage.xml junit-*.xml
	@echo ""

## Documentation
doc:
	@echo "--> Building documentation"
	cd docs && $(MAKE) build

doc-serve:
	@echo "--> Serving documentation"
	cd docs && $(MAKE) serve

doc-deploy:
	@echo "--> Deploying documentation"
	make doc
	rsync -e ssh -avz docs/site/ root@hop3.cloud:/var/www/hop3.cloud/
