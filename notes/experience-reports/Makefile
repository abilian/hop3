# Local checks and the PDF build for the experience reports.
#
# `lint` is deliberately NOT wired into the repo's top-level `make lint`: it
# validates prose-adjacent metadata against recipes and against git history, and
# a report going stale should not block an unrelated code change in CI. Run it
# here, when you touch a report or a recipe.
#
#     make          # validate every report
#     make pdf      # bundle.pdf, one chapter per report
#     make bundle   # the intermediate single markdown document

HOP3 := $(CURDIR)/../..

.PHONY: all lint pdf pdf-debug bundle clean help

all: lint pdf

## Validate every report header against the recipes it describes.
##
## Checks the set of reports against the set of catalog applications in BOTH
## directions, each declared nix-gen template against the recipe's actual one,
## the bar a report claims against what its status may assert, and
## `last_verified` against the recipes' last commit — which is what makes
## staleness detectable instead of merely regrettable.
lint:
	@cd $(HOP3) && uv run hop3-tools catalog reports

## Build bundle.pdf: every report as its own chapter, starting on a new page.
##
## Not gated on `lint`. The bundle is useful while the reports are being
## revised, and a blocked build teaches nothing a warning does not — run `make
## lint` for the verdict.
pdf:
	@./build.py

## Leave build/ in place so the generated Typst can be inspected.
pdf-debug:
	@./build.py --keep
	@echo "--> Typst sources kept in build/"

## Concatenate the reports into a single markdown document (not the PDF path).
bundle:
	@cd $(HOP3) && uv run hop3-tools catalog reports --bundle \
		notes/experience-reports/_bundle.md

clean:
	@rm -rf build bundle.pdf _bundle.md _bundle.pdf
	@echo "--> Removed build/, bundle.pdf, _bundle.md"

help:
	@echo "make lint       validate the report headers against the recipes"
	@echo "make pdf        build bundle.pdf (one chapter per report)"
	@echo "make pdf-debug  ... and keep the generated Typst in build/"
	@echo "make bundle     concatenate the reports into _bundle.md"
	@echo "make clean      remove generated files"
