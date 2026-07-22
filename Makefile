.PHONY: all develop test test-fast lint clean doc format build serve
.PHONY: testlab-serve testlab-prune testlab-schedule testlab-run
.PHONY: deploy deploy-docker clean-server clean-and-deploy
.PHONY: test-e2e test-cov test-demos test-tutorials
.PHONY: test-installer build-installers test-apps test-app test-nix

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
	# uv sync --all-groups -U
	uv sync --all-packages --all-extras --all-groups -U
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

## Run the Test Lab web UI in dev mode (auto-reload, auth bypassed)
testlab-serve:
	TESTLAB_UNSAFE=true uv run hop3-testlab serve --reload

## Prune old Test Lab build logs per the retention policy
testlab-prune:
	uv run hop3-testlab prune

## Run the Test Lab nightly scheduler in the foreground
testlab-schedule:
	uv run hop3-testlab schedule

## Trigger a run now (full: MODE=ci|dev|nightly, or per-app: APP=<path>; TARGET=hetzner)
testlab-run:
	uv run hop3-testlab run --target $(or $(TARGET),hetzner) --trigger manual \
		$(if $(APP),--apps $(APP),--mode $(or $(MODE),ci))

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

## Fast lane — unit tests, all packages, no Docker (< 1 min). The inner loop.
test-fast:
	@echo "--> Fast tests (unit, all packages, no Docker)"
	uv run pytest \
	  packages/hop3-server/tests/a_unit \
	  packages/hop3-cli/tests \
	  packages/hop3-rootd/tests/a_unit \
	  packages/hop3-installer/tests/a_unit \
	  packages/hop3-tui/tests \
	  packages/hop3-testing/tests \
	  packages/hop3-testlab/tests/a_unit
	@echo ""

## Check tier — full in-process suite, all packages, no Docker. The pre-push gate.
test:
	@echo "--> Check tier (unit + integration, all packages, no Docker)"
	uv run pytest \
	  packages/hop3-server/tests/a_unit \
	  packages/hop3-server/tests/b_integration \
	  packages/hop3-cli/tests \
	  packages/hop3-rootd/tests \
	  packages/hop3-installer/tests/a_unit \
	  packages/hop3-installer/tests/b_integration \
	  packages/hop3-tui/tests \
	  packages/hop3-testing/tests \
	  packages/hop3-testlab/tests/a_unit
	@echo ""

## Docker e2e — backups, git-push, real deploys (needs Docker). Part of the check gate.
## Always Docker-only: the root conftest makes HOP3_DEV_HOST/HOP3_TEST_HOST taboo
## for pytest, so no `unset` dance is needed. Remote is opt-in via `--ssh-host`.
test-e2e:
	@echo "--> Docker e2e tests (c_e2e) — server + installer"
	uv run pytest packages/hop3-server/tests/c_e2e
	uv run pytest packages/hop3-installer/tests/c_e2e --docker
	@echo ""

## Coverage — the in-process layers (what coverage.py can actually see)
test-cov:
	@echo "--> Coverage (unit + integration)"
	uv run pytest --cov=hop3 --cov-report term-missing \
	  packages/hop3-server/tests/a_unit \
	  packages/hop3-server/tests/b_integration
	@echo ""

## Run demos on Docker (SSH backend: python demos/demo.py run --host $$HOP3_DEV_HOST --local)
test-demos:
	@echo "--> Resetting test server (docker)"
	hop3-deploy-server --docker --from local --with all --clean
	@echo "--> Running demos on Docker backend"
	python demos/demo.py run --backend docker --local --quiet
	@echo ""

## Run tutorials (validoc doc-as-tests)
test-tutorials:
	@echo "--> Running tutorials (validoc)"
	python ./scripts/run-all-tutorials.py
	@echo ""

#
# App / deploy testing (hop3-test) — deploys real apps to a target.
# `hop3-test` is the interface; the targets below are just front doors. For
# other variants, call the CLI directly:
#   list available tests    uv run hop3-test list
#   deploy from local code   uv run hop3-test run --from local [--clean]
#   nightly matrix + report  uv run hop3-test run --docker --mode nightly --report html
#

## Deploy Hop3 + run the app catalog on Docker (the apps tier)
test-apps:
	@echo "--> Testing apps on Docker (hop3-test run)"
	uv run hop3-test run --docker
	@echo ""

## Test one app or path: make test-app APP=apps/real-apps-native/edrix
test-app:
	@if [ -z "$(APP)" ]; then echo "Usage: make test-app APP=<app-path-or-name>"; exit 1; fi
	uv run hop3-test run --docker $(APP)

## Deploy Hop3 + run the Nix suite (the M2.2 nix-runtime gate).
## Docker by default; pass HOST=<box> to run it against a real server.
## Deliberately NOT taken from an env var: an ambient value silently
## redirecting a deploy at someone's server is the ADR 043 taboo.
NIX_SUITE = apps/test-apps-nix apps/test-apps-nix-gen apps/real-apps-nix-gen
test-nix:
	@echo "--> Testing Nix apps (hop3-test run --with nix)$(if $(HOST), on $(HOST), on Docker)"
	uv run hop3-test run $(if $(HOST),--host $(HOST),--docker) --with nix $(NIX_SUITE)

## Reproducibility gate: rebuild every nix-gen app and fail if any output drifts
.PHONY: check-reproducible
check-reproducible:
	@echo "--> Checking nix-gen reproducibility (nix build --rebuild)"
	uv run hop3-tools nix check-reproducible $${HOP3_NIX_SSH:+--ssh $$HOP3_NIX_SSH} \
	  apps/test-apps-nix-gen apps/real-apps-nix-gen
	@echo ""

## Advertised gate (nix-gen tier): reproducible build AND clean deploy.
## An app can rebuild bit-identically yet fail to start — directus rebuilt
## deterministically while isolated-vm was uncompiled (blocker #17). Build
## determinism alone never proves the app runs, so an app is advertise-ready
## only when BOTH halves pass. check-reproducible runs first (fail-fast); the
## deploy check (test-nix) runs only if it passes.
.PHONY: gate-nix
## Both halves take the same target: HOP3_NIX_SSH picks the build host,
## HOST the deploy host. Passing neither runs the build locally and the deploy
## on Docker, which is a weaker gate than it looks.
gate-nix:
	@echo "--> Advertised gate (nix-gen): reproducible build AND clean deploy"
	$(MAKE) check-reproducible
	$(MAKE) test-nix HOST=$(HOST)
	@echo "==> gate-nix PASSED: nix-gen tier is reproducible AND deploys."

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
	uv run hop3-deploy-server --from local

## Deploy to local Docker container
deploy-docker:
	@echo "--> Deploying to Docker container"
	uv run hop3-deploy-server --from local --docker

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
	twine upload --skip-existing dist/*

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
	cd docs && make deploy

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
	# adt clean
