# Hop3 Documentation - Zensical Build

ZENSICAL := uv run zensical
PYTHON := uv run python

.PHONY: help build serve clean convert-tutorials convert-adrs generate-blog-index preprocess schema lint-cli

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
	@echo "  make schema              - Publish the hop3.toml JSON Schema into site/"
	@echo "  make lint-cli            - Check every documented \`hop3 ...\` command exists"
	@echo ""

convert-tutorials:
	$(PYTHON) scripts/convert_tutorials.py

convert-adrs:
	$(PYTHON) scripts/convert_adrs.py

generate-blog-index:
	$(PYTHON) scripts/generate_blog_index.py

preprocess: convert-tutorials convert-adrs generate-blog-index
	$(PYTHON) scripts/preprocess_markdown.py

# The hop3.toml JSON Schema editors validate against. Regenerated from the
# server's Pydantic models and dropped at the path its own $$id points to, so a
# recipe's `#:schema` directive resolves. Runs AFTER zensical build, which
# rewrites site/ (same reason the installer bundles are placed here).
schema:
	$(PYTHON) ../scripts/generate-toml-schema.py --site-dir site

# Every `hop3 ...` in the docs must name a real command. Runs after preprocess
# so the generated trees (tutorials, ADRs, blog) are checked as published.
# Deprecated aliases are warnings; add --strict to fail on them too.
lint-cli:
	$(PYTHON) scripts/lint_cli_commands.py

build: preprocess lint-cli
	$(ZENSICAL) build
	uv run hop3-install bundle --all --output-dir site/
	@make schema

serve: preprocess
	$(ZENSICAL) serve --open

deploy:
	@make build
	hop3 --context prod deploy

clean:
	rm -rf site/ src/tutorials/ src/blog/posts/ src/developers/adrs/
