# Local checks for the experience reports.
#
# Deliberately NOT wired into the repo's top-level `make lint`: this validates
# prose-adjacent metadata against recipes and against git history, and a report
# going stale should not block an unrelated code change in CI. Run it here, when
# you touch a report or a recipe.
#
#     make          # validate every report
#     make bundle   # one markdown document, for the PDF

HOP3 := $(CURDIR)/../..

.PHONY: all lint bundle help

all: lint

## Validate every report header against the recipes it describes.
##
## Checks the set of reports against the set of catalog applications in BOTH
## directions, each declared nix-gen template against the recipe's actual one,
## the bar a report claims against what its status may assert, and
## `last_verified` against the recipes' last commit — which is what makes
## staleness detectable instead of merely regrettable.
lint:
	@cd $(HOP3) && uv run hop3-tools catalog reports

## Concatenate the reports into a single markdown document.
bundle:
	@cd $(HOP3) && uv run hop3-tools catalog reports --bundle \
		notes/experience-reports/_bundle.md

help:
	@echo "make lint    validate the report headers against the recipes"
	@echo "make bundle  concatenate the reports into _bundle.md"
