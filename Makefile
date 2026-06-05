.PHONY: all develop test lint clean doc format build serve
.PHONY: deploy deploy-docker clean-server clean-and-deploy
.PHONY: test-all test-ci test-demos test-demos-docker test-demos-ssh
.PHONY: test-tutorials test-tutorials-ssh test-installer build-installers
.PHONY: test-dev test-ci-new test-nightly test-list test-run
.PHONY: test-system test-system-clean test-apps test-app test-nix

# For tests, set HOP3_DEV_HOST in your environment

all: ruff test lint doc

#
# Help
#
help:
	adt help-make

#
# Development
#

## Install dependencies and setup dev environment
develop: install-deps activate-pre-commit configure-git

## Alias for develop
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

## Run full development stack (web server + uWSGI emperor)
serve:
	hop3-server setup
	honcho -f Procfile.dev start

## Aliases for serve
dev: serve
run: serve

## Run only the web server (without uWSGI)
serve-web:
	litestar --app asgi:create_app run --debug --reload

#
# Code Quality
#

## Quick lint
ruff:
	uv run ruff format --check packages/*/src packages/*/tests
	uv run ruff check packages/*/src packages/*/tests

## Lint and type check
lint:
	@echo "--> Linting code"
	@make ruff
	uv run pyrefly check packages/hop3-*/src
	# uv run ty check packages/hop3-*/src
	uv run mypy packages/hop3-*/src
	cd packages/hop3-server && uv run deptry src
	@echo ""

## Alias for lint (used by CI)
check: lint

## Format code
format:
	@echo "--> Formatting code"
	uv run ruff format packages/*/src packages/*/tests
	uv run ruff check --fix packages/*/src packages/*/tests
	@make update-tocs
	# python scripts/update-copyright.py
	@echo ""

update-tocs:
	uv run markdown-toc --maxdepth 3 -i README.md
	# uv run markdown-toc --maxdepth 3 -i notes/todo/TODO-next.md
	# uv run markdown-toc --maxdepth 3 -i notes/todo/TODO-NGI.md
	uv run markdown-toc --maxdepth 3 -i notes/testing/status.md

## Run security audit
audit:
	@echo "--> Running security audit"
	nox -e audit
	@echo ""

#
# Testing
#

## Run all pytest tests (unit, integration, e2e)
test:
	@echo "--> Running Python tests"
	uv run pytest packages/hop3-server/tests
	uv run pytest packages/hop3-cli/tests
	@echo ""

## Run tests with coverage report
test-with-coverage:
	@echo "--> Running Python tests with coverage"
	uv run pytest --cov=hop3 --cov-report term-missing
	@echo ""

## Run tests with runtime type checking
test-with-typeguard:
	@echo "--> Running Python tests with typeguard"
	uv run pytest --typeguard-packages=hop3,hop3_agent,hop3_server,hop3_web,hop3_lib
	@echo ""

## Run full CI test suite (pytest + demos + tutorials)
test-all: test-ci
test-ci:
	@echo "=========================================="
	@echo "Running CI test suite"
	@echo "=========================================="
	@echo ""
	@echo "Phase 1: Run pytest..."
	@make test
	@echo ""
	@echo "Phase 2: Deploy to Docker..."
	uv run hop3-deploy --local --docker
	@echo ""
	@echo "Phase 3: Deploy to SSH target (${HOP3_DEV_HOST})..."
	uv run hop3-deploy --local
	@echo ""
	@echo "Phase 4: Run demos on Docker..."
	python demos/demo.py --backend docker --local --quiet
	@echo ""
	@echo "Phase 5: Run demos on SSH target..."
	python demos/demo.py --host ${HOP3_DEV_HOST} --local --quiet
	@echo ""
	@echo "Phase 6: Run tutorials..."
	python ./scripts/run-all-tutorials.py
	@echo ""
	@echo "=========================================="
	@echo "CI test suite completed!"
	@echo "=========================================="

## Run demos on both backends
test-demos: test-demos-docker test-demos-ssh

## Run demos on Docker backend
test-demos-docker:
	@echo "--> Resetting test server (docker)"
	hop3-deploy --docker --local --with all --clean
	@echo "--> Running demos on Docker backend"
	python demos/demo.py --backend docker --local --quiet
	@echo ""

## Run demos on SSH backend (requires HOP3_DEV_HOST)
test-demos-ssh:
	@echo "--> Resetting test server (${HOP3_DEV_HOST})"
	hop3-deploy --local --with all --clean
	@echo "--> Performing additional system cleanup"
	hop3 system:cleanup
	@echo "--> Running demos on SSH backend (${HOP3_DEV_HOST})"
	python demos/demo.py --host ${HOP3_DEV_HOST} --local --quiet
	@echo ""

## Run tutorials
test-tutorials: test-tutorials-ssh

## Run tutorials on SSH backend
test-tutorials-ssh:
	@echo "--> Running tutorials on SSH backend"
	./scripts/run-all-tutorials.sh
	@echo ""

#
# New unified test runner (hop3-test)
#

## Run quick tests with new runner (fast, P0 only) - LEGACY
test-dev:
	@echo "--> Running dev tests (fast, P0)"
	uv run hop3-test dev --target docker
	@echo ""

## Run CI tests with new runner (fast+medium, P0)
test-ci-new:
	@echo "--> Running CI tests (fast+medium, P0)"
	uv run hop3-test ci --target docker
	@echo ""

## Run nightly tests with new runner (all tiers, all priorities)
test-nightly:
	@echo "--> Running nightly tests (all)"
	uv run hop3-test nightly --target docker
	@echo ""

## List available tests
test-list:
	@uv run hop3-test list

## Run specific tests by name
test-run:
	@echo "Usage: make test-run APPS='app1 app2'"
	@echo "Example: make test-run APPS='010-flask-pip-wsgi 020-nodejs-express'"

#
# System and App Testing (NEW - uses hop3-deploy)
#

## Test Hop3 system with hop3-deploy (local code)
test-system:
	@echo "--> Testing Hop3 system (via hop3-deploy)"
	uv run hop3-test system --deploy-from local
	@echo ""

## Test Hop3 system with clean install
test-system-clean:
	@echo "--> Testing Hop3 system (clean install)"
	uv run hop3-test system --deploy-from local --clean
	@echo ""

## Test apps against pre-built image (fast, no deployment)
test-apps:
	@echo "--> Testing apps (pre-built image)"
	uv run hop3-test apps
	@echo ""

## Test specific app
test-app:
	@echo "Usage: make test-app APP=010-flask-pip-wsgi"
	@if [ -n "$(APP)" ]; then uv run hop3-test apps $(APP); fi

## Run Nix-focused test suite (test-apps-nix + real-apps-nix-gen, Docker)
test-nix:
	@echo "--> Running Nix test suite (Docker, --with nix)"
	uv run hop3-test system --docker --with nix apps/test-apps-nix apps/real-apps-nix-gen
	@echo ""

#
# Installer Testing
#

## Build single-file installers
build-installers:
	@echo "--> Building single-file installers"
	@mkdir -p installer
	uv run hop3-install bundle --all --output-dir installer/
	@echo ""

## Test installers (Docker by default, use 'hop3-install test --help' for more options)
test-installer: build-installers
	@echo "--> Testing installers in Docker"
	uv run hop3-install test docker --distro ubuntu --type both --method local
	uv run hop3-install test ssh --distro ubuntu --type both --method local
	@echo ""

#
# Deployment
#

## Deploy to development server (set HOP3_DEV_HOST)
deploy:
	@echo "--> Deploying to ${HOP3_DEV_HOST}"
	uv run hop3-deploy --local

## Deploy to local Docker container
deploy-docker:
	@echo "--> Deploying to Docker container"
	uv run hop3-deploy --local --docker

## Clean development server (WARNING: removes everything)
clean-server:
	@echo "--> Cleaning server (WARNING: removes everything)"
	-ssh root@${HOP3_DEV_HOST} apt-get purge -y nginx nginx-core nginx-common
	ssh root@${HOP3_DEV_HOST} rm -rf /home/hop3 /etc/nginx

## Clean server and redeploy
clean-and-deploy:
	make clean-server
	make deploy

#
# Build & Release
#

## Build Python packages
build:
	@make clean
	uv build packages/hop3-server
	uv build packages/hop3-rootd
	uv build packages/hop3-cli
	uv build packages/hop3-installer
	uv build packages/hop3-testing
	uv build packages/hop3-tui

## Publish to PyPI (legacy, use 'make release' instead)
publish: clean build
	twine upload dist/*

## Release all packages to PyPI (checks versions, builds, uploads)
release:
	python scripts/release.py

## Dry-run release (build but don't upload)
release-dry-run:
	python scripts/release.py --dry-run

## Generate SBOM for CRA compliance
generate-sbom:
	@echo "--> Generating SBOM"
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
# Documentation
#

## Build documentation
doc:
	@echo "--> Building documentation"
	cd docs && $(MAKE) build

## Serve documentation locally
doc-serve:
	@echo "--> Serving documentation"
	cd docs && $(MAKE) serve

## Deploy documentation to hop3.cloud
doc-deploy:
	@echo "--> Deploying documentation"
	make doc
	cd docs && hop3 deploy hop3-doc

#
# Cleanup
#

## Clean build artifacts
clean:
	bash -c "shopt -s globstar && rm -f **/*.pyc"
	bash -c "shopt -s globstar && rm -rf **/.ruff_cache"
	bash -c "shopt -s globstar && rm -rf **/.pytest_cache"
	bash -c "shopt -s globstar && rm -rf **/.mypy_cache"
	find . -type d -empty -delete
	rm -rf *.egg-info *.egg .coverage .eggs .cache .mypy_cache .pyre \
		.pytest_cache .pytest .DS_Store  docs/_build docs/cache docs/tmp \
		dist build pip-wheel-metadata junit-*.xml htmlcov coverage.xml \
		tmp htmlcov-hop3-testing
	rm -rf packages/*/dist packages/*/.pdm-build
	rm -rf .nox
	rm -rf docs/site
	rm -rf docs/.cache
	rm -rf test-logs/
	adt clean
