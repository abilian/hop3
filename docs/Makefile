#.PHONY: all run build clean deploy pdf
#
#SRC:=$(wildcard src/**/*.md)
#
#all: run
#
#run:
#	python ./scripts/gen-api.py
#	mkdocs serve
#
#serve: run
#
#build: $(SRC) mkdocs.yml
#	python ./scripts/gen-api.py
#	mkdocs build
#	cp -a src/.well-known site/
#	cp -a assets/root/* site/
#
#clean:
#	rm -rf site
#
#pdf: $(SRC) mkdocs.yml
#	ENABLE_PDF_EXPORT=1 mkdocs build
