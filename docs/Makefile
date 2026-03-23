# Hop3 Documentation - Zensical Build

ZENSICAL := uv run zensical
PYTHON := uv run python

.PHONY: help build serve clean convert-tutorials generate-blog-index preprocess

help:
	@echo "Hop3 Documentation (Zensical)"
	@echo ""
	@echo "Commands:"
	@echo "  make build               - Build the documentation site"
	@echo "  make serve               - Start local development server"
	@echo "  make clean               - Remove generated files"
	@echo "  make convert-tutorials   - Convert tutorials from source format"
	@echo "  make generate-blog-index - Generate blog index and update nav"
	@echo ""

convert-tutorials:
	$(PYTHON) scripts/convert_tutorials.py

generate-blog-index:
	$(PYTHON) scripts/generate_blog_index.py

preprocess: convert-tutorials generate-blog-index
	$(PYTHON) scripts/preprocess_markdown.py

build: preprocess
	$(ZENSICAL) build

serve: preprocess
	$(ZENSICAL) serve --open

deploy:
	@make build
	hop3 --context prod deploy hop3-docs

clean:
	rm -rf site/ src/tutorials/ src/blog/posts/
