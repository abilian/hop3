# Makefile for Hop3 slide decks
#
# Decks are Markdown files rendered with Prezo or Marp. Each `*.pdf` / `*.html`
# target auto-routes by front matter: a deck with `marp: true` is built with
# Marp, everything else with Prezo.
# Run `make` (or `make help`) to see the available targets.

# --- Configuration -----------------------------------------------------------

PREZO ?= prezo
MARP  ?= marp

# Screen geometry used when exporting Prezo decks (width x height, in cells).
SIZE  ?= 100x30

# Flags passed to every Prezo export.
# Note: some prezo builds also accept --no-emoji; this one (2026.4.2) does not,
# so it is left out. Add it via `make pdf PREZO_FLAGS="--no-emoji --size 100x30"`.
PREZO_FLAGS ?= --size $(SIZE)

# Flags passed to every Marp export (--allow-local-files: read images/ from disk).
MARP_FLAGS ?= --allow-local-files

# Time budget (minutes) shown by the live presenter's pacing indicator.
TIME_BUDGET ?= 10

# Every Markdown file in this directory is a deck, except this README.
SLIDES := $(filter-out README.md, $(wildcard *.md))
PDFS   := $(SLIDES:.md=.pdf)
HTMLS  := $(SLIDES:.md=.html)

# Split decks by renderer (front matter `marp: true` => Marp, else Prezo).
MARP_SLIDES  := $(shell grep -lE '^marp:[[:space:]]*true' $(SLIDES) /dev/null)
PREZO_SLIDES := $(filter-out $(MARP_SLIDES),$(SLIDES))

# Deck targeted by single-deck actions (present, open). Prezo deck by default
# (only Prezo has the live presenter). Override with DECK=file.md.
DECK ?= $(firstword $(PREZO_SLIDES) $(SLIDES))

.DEFAULT_GOAL := help

# --- Build -------------------------------------------------------------------

.PHONY: all pdf html
all: pdf ## Build every deck to PDF (the default build)

pdf: $(PDFS) ## Export all decks to PDF (auto: Prezo or Marp)

html: $(HTMLS) ## Export all decks to HTML (auto: Prezo or Marp)

%.pdf: %.md
	@if grep -qE '^marp:[[:space:]]*true' $<; then \
		echo "marp  -> $@";  $(MARP) --pdf $(MARP_FLAGS) $<; \
	else \
		echo "prezo -> $@"; $(PREZO) --export pdf $(PREZO_FLAGS) $<; \
	fi

%.html: %.md
	@if grep -qE '^marp:[[:space:]]*true' $<; then \
		echo "marp  -> $@";  $(MARP) --html $(MARP_FLAGS) $<; \
	else \
		echo "prezo -> $@"; $(PREZO) --export html $(PREZO_FLAGS) $<; \
	fi

# --- Present -----------------------------------------------------------------

.PHONY: present watch open
present: ## Open DECK in Prezo's live TUI presenter (DECK=file.md to choose)
	$(PREZO) --time-budget $(TIME_BUDGET) $(DECK)

watch: present ## Alias for `present`

open: $(DECK:.md=.pdf) ## Build DECK's PDF and open it (macOS)
	open $<

# --- Housekeeping ------------------------------------------------------------

.PHONY: clean
clean: ## Remove generated PDF/HTML exports
	rm -f $(PDFS) $(HTMLS)

.PHONY: help
help: ## Show this help
	@echo "Hop3 slide decks. Available targets:"
	@echo
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'
	@echo
	@echo "Prezo decks: $(PREZO_SLIDES)"
	@echo "Marp decks:  $(MARP_SLIDES)"
