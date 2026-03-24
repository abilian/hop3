#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2024-2026 Abilian SAS <https://abilian.com>
# SPDX-License-Identifier: Apache-2.0
"""Generate blog index.md and update zensical.toml nav section.

This script:
1. Reads all blog posts from docs/src/blog/posts/
2. Parses YAML frontmatter for metadata (date, tags, description)
3. Generates docs/src/blog/index.md
4. Updates the Blog section in docs/zensical.toml

Usage:
    python scripts/generate_blog_index.py
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

# Paths
DOCS_DIR = Path(__file__).parent.parent
POSTS_DIR = DOCS_DIR / "blog" / "posts"  # Source posts (not generated)
INDEX_FILE = DOCS_DIR / "src" / "blog" / "index.md"
ZENSICAL_FILE = DOCS_DIR / "zensical.toml"


@dataclass
class BlogPost:
    """Represents a blog post with its metadata."""

    filename: str
    title: str
    date: date
    description: str
    tags: list[str]
    is_draft: bool

    @property
    def path(self) -> str:
        return f"posts/{self.filename}"

    @property
    def year(self) -> int:
        return self.date.year

    @property
    def month(self) -> int:
        return self.date.month

    @property
    def month_name(self) -> str:
        return self.date.strftime("%B")


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from markdown content.

    Returns (metadata dict, remaining content).
    """
    if not content.startswith("---"):
        return {}, content

    # Find the closing ---
    end_match = re.search(r"\n---\n", content[3:])
    if not end_match:
        return {}, content

    yaml_content = content[3 : end_match.start() + 3]
    remaining = content[end_match.end() + 3 :]

    try:
        metadata = yaml.safe_load(yaml_content) or {}
    except yaml.YAMLError:
        metadata = {}

    return metadata, remaining


def extract_title(content: str) -> str:
    """Extract title from first H1 heading."""
    match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return "Untitled"


def parse_date_from_filename(filename: str) -> date | None:
    """Extract date from filename like 2026-01-slug.md or draft-2026-04-slug.md."""
    # Remove draft- prefix if present
    name = filename.replace("draft-", "")

    match = re.match(r"(\d{4})-(\d{2})-", name)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        # Use first of month as default day
        return date(year, month, 1)
    return None


def load_blog_post(filepath: Path) -> BlogPost | None:
    """Load a blog post and extract its metadata."""
    content = filepath.read_text()
    metadata, body = parse_frontmatter(content)

    # Get date from frontmatter or filename
    post_date = None
    if "date" in metadata:
        if isinstance(metadata["date"], date):
            post_date = metadata["date"]
        elif isinstance(metadata["date"], str):
            try:
                post_date = date.fromisoformat(metadata["date"])
            except ValueError:
                pass

    if post_date is None:
        post_date = parse_date_from_filename(filepath.name)

    if post_date is None:
        print(f"Warning: Could not determine date for {filepath.name}")
        return None

    # Get title from frontmatter or content
    title = metadata.get("title") or extract_title(body)

    # Get description
    description = metadata.get("description", "")

    # Get tags
    tags = metadata.get("tags", [])
    if isinstance(tags, str):
        tags = [tags]

    # Check if draft
    is_draft = filepath.name.startswith("draft-")

    return BlogPost(
        filename=filepath.name,
        title=title,
        date=post_date,
        description=description,
        tags=tags,
        is_draft=is_draft,
    )


def load_all_posts() -> list[BlogPost]:
    """Load all blog posts from the posts directory."""
    posts = []
    for filepath in POSTS_DIR.glob("*.md"):
        post = load_blog_post(filepath)
        if post:
            posts.append(post)

    # Sort by date descending (newest first)
    posts.sort(key=lambda p: p.date, reverse=True)
    return posts


def generate_index_md(posts: list[BlogPost]) -> str:
    """Generate the blog index.md content."""
    lines = [
        "# Blog",
        "",
        "News, announcements, and updates from the Hop3 project.",
        "",
    ]

    # Group posts by year and month
    current_year = None
    current_month = None

    # Only include published posts in the index
    published_posts = [p for p in posts if not p.is_draft]

    for post in published_posts:
        # Year header
        if post.year != current_year:
            if current_year is not None:
                lines.append("")
            lines.append(f"## {post.year}")
            current_year = post.year
            current_month = None

        # Month header
        if post.month != current_month:
            lines.append("")
            lines.append(f"### {post.month_name}")
            lines.append("")
            current_month = post.month

        # Post entry with date
        date_str = post.date.strftime("%B %d")  # e.g., "January 02"
        description = f" - {post.description}" if post.description else ""
        lines.append(f"- **{date_str}**: [{post.title}]({post.path}){description}")

    # Footer
    lines.extend(
        [
            "",
            "---",
            "",
            "Want to stay updated? Follow us on [GitHub](https://github.com/abilian/hop3).",
            "",
            "<!-- or [Mastodon](https://fosstodon.org/@hop3). -->",
        ]
    )

    return "\n".join(lines) + "\n"


def update_zensical_toml(posts: list[BlogPost]) -> None:
    """Update the Blog section in zensical.toml."""
    content = ZENSICAL_FILE.read_text()

    # Find the Blog section and replace just that part
    blog_start = content.find('{ "Blog" = [')
    if blog_start == -1:
        print("Warning: Could not find Blog section in zensical.toml")
        return

    # Find the end of the Blog section (matching closing ]})
    depth = 0
    blog_end = blog_start
    in_blog = False
    for i, char in enumerate(content[blog_start:]):
        if char == "[":
            depth += 1
            in_blog = True
        elif char == "]":
            depth -= 1
            if in_blog and depth == 0:
                blog_end = blog_start + i + 1
                # Include the closing }
                if content[blog_end : blog_end + 1] == "}":
                    blog_end += 1
                break

    # Generate the new Blog section
    new_blog = generate_blog_toml_section(posts)

    # Replace
    new_content = content[:blog_start] + new_blog + content[blog_end:]
    ZENSICAL_FILE.write_text(new_content)


def generate_blog_toml_section(posts: list[BlogPost]) -> str:
    """Generate the Blog section as TOML string."""
    lines = ['{ "Blog" = [']
    lines.append('        { "All Posts" = "blog/index.md" },')

    # Group by year
    years: dict[int, list[BlogPost]] = {}
    for post in posts:
        if post.is_draft:
            continue
        if post.year not in years:
            years[post.year] = []
        years[post.year].append(post)

    # Add year sections (newest first)
    for year in sorted(years.keys(), reverse=True):
        year_posts = years[year]
        lines.append(f'        {{ "{year}" = [')
        for post in year_posts:
            # Use a shortened title for nav
            short_title = post.title
            if len(short_title) > 50:
                short_title = short_title[:47] + "..."
            # Escape quotes in title
            short_title = short_title.replace('"', '\\"')
            lines.append(f'            {{ "{short_title}" = "blog/{post.path}" }},')
        lines.append("        ]},")

    lines.append("    ]}")

    return "\n".join(lines)


def main() -> None:
    """Main entry point."""
    print("Loading blog posts...")
    posts = load_all_posts()
    print(f"Found {len(posts)} posts ({len([p for p in posts if not p.is_draft])} published, {len([p for p in posts if p.is_draft])} drafts)")

    print("\nGenerating index.md...")
    index_content = generate_index_md(posts)
    INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    INDEX_FILE.write_text(index_content)
    print(f"Written to {INDEX_FILE}")

    print("\nUpdating zensical.toml...")
    update_zensical_toml(posts)
    print(f"Updated {ZENSICAL_FILE}")

    print("\nDone!")


if __name__ == "__main__":
    main()
