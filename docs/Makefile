# Hop3 Documentation - Zensical Build

ZENSICAL := ../sandbox/zensical/.venv/bin/zensical
PYTHON := python3

.PHONY: help build serve clean convert-tutorials

help:
	@echo "Hop3 Documentation (Zensical)"
	@echo ""
	@echo "Commands:"
	@echo "  make build             - Build the documentation site"
	@echo "  make serve             - Start local development server"
	@echo "  make clean             - Remove generated files"
	@echo "  make convert-tutorials - Convert tutorials from source format"
	@echo ""

convert-tutorials:
	$(PYTHON) scripts/convert_tutorials.py

build: convert-tutorials
	$(ZENSICAL) build

serve: convert-tutorials
	$(ZENSICAL) serve --open

deploy:
	@make build
	hop3 --context prod deploy hop3-docs

clean:
	rm -rf site/ src/tutorials/
