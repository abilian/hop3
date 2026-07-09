# Hop3 Documentation - Zensical Build

ZENSICAL := uv run zensical
PYTHON := uv run python

.PHONY: help build serve clean convert-tutorials convert-adrs generate-blog-index preprocess

help:
	@echo "Hop3 Documentation (Zensical)"
	@echo ""
	@echo "Commands:"
	@echo "  make build               - Build the documentation site"
	@echo "  make serve               - Start local development server"
	@echo "  make clean               - Remove generated files"
	@echo "  make convert-tutorials   - Convert tutorials from source format"
	@echo "  make convert-adrs        - Publish ADRs (notes/adrs/) and update nav"
	@echo "  make generate-blog-index - Generate blog index and update nav"
	@echo ""

convert-tutorials:
	$(PYTHON) scripts/convert_tutorials.py

convert-adrs:
	$(PYTHON) scripts/convert_adrs.py

generate-blog-index:
	$(PYTHON) scripts/generate_blog_index.py

preprocess: convert-tutorials convert-adrs generate-blog-index
	$(PYTHON) scripts/preprocess_markdown.py

build: preprocess
	$(ZENSICAL) build

serve: preprocess
	$(ZENSICAL) serve --open

deploy:
	@make build
	hop3 --context prod deploy

clean:
	rm -rf site/ src/tutorials/ src/blog/posts/ src/developers/adrs/
