# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

.PHONY: serve build deploy clean

# Detect Material Insiders and export env var if available
MATERIAL_INSIDERS := $(shell python3 -c "from importlib.metadata import version; v=version('mkdocs-material'); exit(0 if '+insiders' in v else 1)" 2>/dev/null && echo "true" || echo "false")

export MATERIAL_INSIDERS

## Serve documentation (localhost:8000)
serve:
	@echo "--> Serving documentation on http://127.0.0.1:8000"
ifeq ($(MATERIAL_INSIDERS),true)
	@echo "Using Material for MkDocs Insiders"
endif
	mkdocs serve -f mkdocs.yml

## Build documentation
build:
	@echo "--> Building documentation"
ifeq ($(MATERIAL_INSIDERS),true)
	@echo "Using Material for MkDocs Insiders"
endif
	mkdocs build -f mkdocs.yml

## Deploy documentation to GitHub Pages
deploy:
	@echo "--> Deploying documentation to GitHub Pages"
ifeq ($(MATERIAL_INSIDERS),true)
	@echo "Using Material for MkDocs Insiders"
	DEPLOY=true mkdocs gh-deploy -f mkdocs.yml
else
	@echo "ERROR: Not deploying docs without Material for MkDocs Insiders!"
	@exit 1
endif

## Clean built documentation
clean:
	@echo "--> Cleaning built documentation"
	rm -rf site
