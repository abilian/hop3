#!/usr/bin/env python3
"""Convert tutorial markdown files from test syntax to standard markdown.

The source tutorials use custom code block syntax for automated testing:
- ```bash exec id=... dir=... timeout=...  -> executable bash commands
- ```bash skip                              -> skipped commands
- ```output contains                        -> expected output (keep as example)
- ```output regex                           -> regex assertion (remove - not user-friendly)
- ```assert file-exists path=...            -> file assertions (remove)
- ```file path=foo.py                       -> file content to write

This script converts them to clean markdown for Zensical rendering.
"""

import re
import shutil
from pathlib import Path

# Language detection from file extensions
EXTENSION_TO_LANG = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".rb": "ruby",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".php": "php",
    ".cs": "csharp",
    ".fs": "fsharp",
    ".ex": "elixir",
    ".exs": "elixir",
    ".erl": "erlang",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "zsh",
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".xml": "xml",
    ".html": "html",
    ".css": "css",
    ".sql": "sql",
    ".md": "markdown",
    ".dockerfile": "dockerfile",
    ".env": "bash",
    ".gitignore": "text",
}

# Special filenames
FILENAME_TO_LANG = {
    "Procfile": "procfile",
    "Dockerfile": "dockerfile",
    "Makefile": "makefile",
    ".env": "bash",
    ".env.example": "bash",
}


def get_lang_from_path(path: str) -> str:
    """Determine language from file path."""
    filename = Path(path).name
    if filename in FILENAME_TO_LANG:
        return FILENAME_TO_LANG[filename]

    ext = Path(path).suffix.lower()
    return EXTENSION_TO_LANG.get(ext, "text")


def strip_tutorial_frontmatter(content: str) -> str:
    """Remove the tutorial: block from YAML frontmatter.

    Tutorial files have frontmatter like:
    ---
    tutorial:
      name: ...
      env: ...
      teardown: ...
    ---

    This removes the entire frontmatter if it only contains tutorial metadata.
    """
    # Match frontmatter
    frontmatter_match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
    if not frontmatter_match:
        return content

    frontmatter = frontmatter_match.group(1).strip()

    # If frontmatter starts with 'tutorial:', remove it entirely
    # (tutorial metadata is only for testing, not documentation)
    if frontmatter.startswith("tutorial:"):
        return content[frontmatter_match.end() :]

    # Otherwise, try to remove just the tutorial: block
    # Parse line by line to handle nested YAML properly
    lines = frontmatter.split("\n")
    result_lines = []
    skip_until_unindent = False

    for line in lines:
        if line.startswith("tutorial:"):
            skip_until_unindent = True
            continue
        if skip_until_unindent:
            # Check if this line is indented (part of tutorial block)
            if line and (line[0] == " " or line[0] == "\t"):
                continue
            else:
                skip_until_unindent = False

        if not skip_until_unindent:
            result_lines.append(line)

    cleaned_frontmatter = "\n".join(result_lines).strip()

    # If frontmatter is now empty, remove it entirely
    if not cleaned_frontmatter:
        return content[frontmatter_match.end() :]

    return f"---\n{cleaned_frontmatter}\n---\n{content[frontmatter_match.end():]}"


def convert_code_blocks(content: str) -> str:
    """Convert custom code block syntax to standard markdown."""

    # Remove ```assert ... ``` blocks entirely (they're test-only)
    content = re.sub(r"```assert[^\n]*\n```\n*", "", content)

    # Remove ```output regex ... ``` blocks entirely
    # (regex patterns are not user-friendly documentation)
    content = re.sub(r"```output regex[^\n]*\n.*?\n```\n*", "", content, flags=re.DOTALL)

    # ```bash exec id=... dir=... timeout=... -> ```bash
    content = re.sub(r"```bash exec[^\n]*", "```bash", content)

    # ```bash skip -> ```bash
    content = re.sub(r"```bash skip[^\n]*", "```bash", content)

    # ```output contains -> ```console (keep the content as example output)
    content = re.sub(r"```output contains[^\n]*", "```console", content)

    # ```output (plain) -> ```console
    content = re.sub(r"```output\s*$", "```console", content, flags=re.MULTILINE)

    # ```file path=foo.py -> ```python (infer from extension)
    def replace_file_block(match):
        path = match.group(1)
        lang = get_lang_from_path(path)
        return f"```{lang}"

    content = re.sub(r"```file path=([^\n]+)", replace_file_block, content)

    return content


def convert_tutorial(source_path: Path, dest_path: Path) -> None:
    """Convert a single tutorial file."""
    content = source_path.read_text()

    # Apply conversions
    content = strip_tutorial_frontmatter(content)
    content = convert_code_blocks(content)

    # Clean up multiple blank lines
    content = re.sub(r"\n{3,}", "\n\n", content)

    # Remove leading whitespace/newlines
    content = content.lstrip()

    # Ensure destination directory exists
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    # Write converted content
    dest_path.write_text(content)


def main():
    """Convert all tutorials from source to destination."""
    script_dir = Path(__file__).parent
    zdocs_dir = script_dir.parent

    source_dir = zdocs_dir / "tutorials"
    dest_dir = zdocs_dir / "src" / "tutorials"

    if not source_dir.exists():
        print(f"Error: Source directory not found: {source_dir}")
        return 1

    # Remove existing tutorials in destination
    if dest_dir.exists():
        shutil.rmtree(dest_dir)

    # Convert all markdown files
    count = 0
    for source_file in source_dir.rglob("*.md"):
        relative_path = source_file.relative_to(source_dir)
        dest_file = dest_dir / relative_path

        convert_tutorial(source_file, dest_file)
        print(f"Converted: {relative_path}")
        count += 1

    print(f"\nConverted {count} tutorial files")
    return 0


if __name__ == "__main__":
    exit(main())
