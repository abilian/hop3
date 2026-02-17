# Hop3 Documentation (Zensical)

This directory contains the Hop3 documentation built with [Zensical](https://github.com/anthropics/zensical), a modern static site generator.

## Directory Structure

```
zdocs/
├── docs/              # Documentation source files (markdown)
│   └── tutorials/     # Generated from tutorials/ (do not edit directly)
├── tutorials/         # Tutorial source files (with test syntax)
├── scripts/           # Build scripts
│   └── convert_tutorials.py
├── site/              # Generated output (do not commit)
├── zensical.toml      # Site configuration
├── Makefile           # Build commands
└── README.md          # This file
```

## Building

```bash
make build    # Build the site
make serve    # Start local dev server
make clean    # Remove generated files
```

## Tutorial Conversion

The tutorials in `tutorials/` use a custom markdown syntax for automated testing:

```markdown
```bash exec id=create-project dir=myapp timeout=60
mkdir myapp && cd myapp
\```

```output contains
Success
\```

```file path=myapp/main.py
print("Hello")
\```

```assert file-exists path=myapp/main.py
\```
```

This syntax allows the tutorial testing framework to:
- Execute commands and verify output
- Create files with specific content
- Assert conditions (file existence, output patterns)

However, Zensical (and standard markdown renderers) don't understand this syntax. The `scripts/convert_tutorials.py` script converts these to standard markdown:

| Source syntax | Converted to |
|---------------|--------------|
| ` ```bash exec id=... dir=... ` | ` ```bash ` |
| ` ```bash skip ` | ` ```bash ` |
| ` ```output contains/regex ` | ` ```text ` |
| ` ```assert ... ` | (removed) |
| ` ```file path=foo.py ` | ` ```python ` (language inferred from extension) |

The `tutorial:` YAML frontmatter (containing test metadata like environment variables and teardown commands) is also stripped.

### Why This Matters

Without conversion, code blocks containing CSS or HTML (like the FastAPI tutorial's inline styles) could be misinterpreted by the markdown parser, causing CSS to leak into the page styling instead of being displayed as code.

### Workflow

1. Edit tutorials in `tutorials/` (with test syntax)
2. Run `make build` or `make serve`
3. The Makefile automatically runs `convert_tutorials.py` before building
4. Converted files are written to `docs/tutorials/`
5. Zensical builds the site from `docs/`

**Important**: Never edit files in `docs/tutorials/` directly - they are overwritten on each build.
