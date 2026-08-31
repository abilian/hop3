# Build the Hop3 technical reports as PDFs.
#
#     make              # every TR-*.pdf that is out of date
#     make TR-03.pdf    # just one
#     make draft        # ... with a DRAFT banner on the cover
#     make debug        # ... and keep the generated Typst in build/
#     make clean
#
# Needs `typst`, `uv` and `mmdc` on PATH (brew install typst uv; npm install
# -g @mermaid-js/mermaid-cli). md2typst is fetched on demand by uvx.

REPORTS := $(wildcard TR-*.md)
PDFS    := $(REPORTS:.md=.pdf)

.PHONY: all draft debug clean help
.DEFAULT_GOAL := all

all: $(PDFS)

## One rule per report, so an untouched TR is not rebuilt and `make -j` works.
## The template is a prerequisite: changing it must re-render everything. It
## lives in the shared library, and `report` is @local/cs's, which is
## @local/lab's document with the CS Lab brand bound to it, so both count.
LIB       := $(HOME)/projects/typst/templates
TEMPLATES := $(wildcard $(LIB)/cs/0.1.0/*.typ) $(wildcard $(LIB)/lab/0.1.0/*.typ)

%.pdf: %.md build.py $(TEMPLATES)
	@./build.py $<

## Same PDFs with a DRAFT banner on the cover. Always rebuilds: the banner is
## not visible to make, so a stale timestamp would silently give you the
## unbannered file back.
draft:
	@./build.py --status draft
	@echo "--> Built with a DRAFT cover banner"

## Leave build/ in place so the generated Typst can be inspected.
debug:
	@./build.py --keep

clean:
	@rm -rf build $(PDFS)
	@echo "--> Removed build/ and $(PDFS)"

help:
	@echo "make            build every TR-*.pdf that is out of date"
	@echo "make TR-03.pdf  build one report"
	@echo "make draft      rebuild all with a DRAFT cover banner"
	@echo "make debug      ... and keep the generated Typst in build/"
	@echo "make clean      remove generated files"
