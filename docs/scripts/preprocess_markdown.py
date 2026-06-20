#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2024-2026 Abilian SAS <https://abilian.com>
# SPDX-License-Identifier: Apache-2.0
"""Preprocess blog posts for Zensical.

This script:
1. Copies blog posts from blog/posts/ to src/blog/posts/
2. Adds blank lines before lists (CommonMark fix)
3. Extracts title from H1 as metadata
4. Adds formatted metadata (date, tags) after the title as HTML
5. Skips draft posts (no date or filename starts with "draft-")
6. Generates tag index pages with navigation
7. Adds "generated file" comment at the top
8. Wires up multi-part *series* (see below)

Series support
--------------
A post joins a series with two frontmatter keys::

    series: How Hop3 is Tested      # the series name
    series_order: 2                 # 1-based position; falls back to date order

For every post in a series the generated page gets:

* **Title** -- the H1 is prefixed with the series name (``# <Series> -- <Title>``),
  unless the title already leads with the series name (the landing/overview post).
* **Series box** -- directly under the title, a "Part N of the series <Series>"
  heading followed by an ordered list of *all* posts in the series (the current
  one in bold without a link, the others linked).

Membership and ordering are computed across all source posts at build time, so
adding or reordering a post updates every sibling's box automatically. Drafts
are excluded from the series.
"""

from __future__ import annotations

import html
import re
import shutil
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

DOCS_DIR = Path(__file__).parent.parent
BLOG_SRC_DIR = DOCS_DIR / "blog" / "posts"
BLOG_DEST_DIR = DOCS_DIR / "src" / "blog" / "posts"
TAGS_DEST_DIR = DOCS_DIR / "src" / "blog" / "tags"
BLOG_INDEX_PATH = DOCS_DIR / "src" / "blog" / "index.md"

GENERATED_COMMENT = "<!-- Generated file - DO NOT EDIT. Source: /docs/blog/posts/ -->\n\n"


@dataclass
class BlogMeta:
    """Blog post metadata."""

    title: str = ""
    date: date | None = None
    tags: list[str] = field(default_factory=list)
    description: str = ""
    filename: str = ""
    series: str = ""
    series_order: int | None = None

    @property
    def slug(self) -> str:
        """URL slug = filename without the .md extension."""
        return self.filename.removesuffix(".md")

    @property
    def is_draft(self) -> bool:
        """Check if post is a draft (no date or filename starts with draft-)."""
        if self.filename.startswith("draft-"):
            return True
        if self.date is None:
            return True
        # Future dates are also drafts
        if self.date > date.today():
            return True
        return False


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from markdown content."""
    if not content.startswith("---"):
        return {}, content

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
    """Extract title from the first H1 heading."""
    match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return ""


def extract_meta(metadata: dict, body: str, filename: str) -> BlogMeta:
    """Extract blog metadata from frontmatter and content."""
    post_date = None
    if "date" in metadata:
        if isinstance(metadata["date"], date):
            post_date = metadata["date"]
        elif isinstance(metadata["date"], str):
            try:
                post_date = date.fromisoformat(metadata["date"])
            except ValueError:
                pass

    tags = metadata.get("tags", [])
    if isinstance(tags, str):
        tags = [tags]

    title = extract_title(body)

    series = (metadata.get("series") or "").strip()
    series_order = metadata.get("series_order")
    if isinstance(series_order, str):
        try:
            series_order = int(series_order)
        except ValueError:
            series_order = None

    return BlogMeta(
        title=title,
        date=post_date,
        tags=tags,
        description=metadata.get("description", ""),
        filename=filename,
        series=series,
        series_order=series_order,
    )


def add_blank_lines_before_lists(content: str) -> str:
    """Add blank line before lists that follow non-blank lines."""
    lines = content.split("\n")
    result = []

    for i, line in enumerate(lines):
        is_list_item = bool(re.match(r"^(\s*[-*+]|\s*\d+\.)\s", line))

        if is_list_item and i > 0:
            prev_line = lines[i - 1]
            prev_is_blank = prev_line.strip() == ""
            prev_is_list = bool(re.match(r"^(\s*[-*+]|\s*\d+\.)\s", prev_line))
            prev_is_code_fence = prev_line.strip().startswith("```")
            prev_is_header = prev_line.strip().startswith("#")

            if (
                not prev_is_blank
                and not prev_is_list
                and not prev_is_code_fence
                and not prev_is_header
            ):
                result.append("")

        result.append(line)

    return "\n".join(result)


def format_metadata_html(meta: BlogMeta) -> str:
    """Format metadata as HTML to insert after title.

    Creates a clean, blog-style metadata block with date and tags. Tag links are
    root-relative (``/blog/tags/<slug>/``): zensical rewrites *relative* hrefs in
    raw HTML (adding a ``../`` for the directory-URL transform), which would
    break a hand-computed relative path. Absolute site paths are left as-is.
    """
    if not meta.date and not meta.tags:
        return ""

    lines = ['<div class="post-meta">']

    # Date with calendar icon (using text, not emoji)
    if meta.date:
        date_str = meta.date.strftime("%B %d, %Y")  # e.g., "January 02, 2026"
        lines.append(f'  <span class="post-date">{date_str}</span>')

    # Tags as pill badges
    if meta.tags:
        tag_links = []
        for tag in meta.tags:
            tag_slug = tag.lower().replace(" ", "-")
            tag_links.append(
                f'<a href="/blog/tags/{tag_slug}/" class="post-tag">{tag}</a>'
            )
        lines.append(f'  <span class="post-tags">{" ".join(tag_links)}</span>')

    lines.append('</div>')

    return '\n\n' + '\n'.join(lines) + '\n'


def add_metadata_after_title(content: str, meta: BlogMeta, series_nav: str = "") -> str:
    """Add formatted metadata HTML (and an optional series box) after the H1."""
    insert = format_metadata_html(meta) + series_nav
    if not insert:
        return content

    # Find the first H1 and add the header blocks after it
    lines = content.split("\n")
    result = []
    added = False

    for line in lines:
        result.append(line)
        if not added and line.startswith("# "):
            result.append(insert)
            added = True

    return "\n".join(result)


def _title_to_inline_html(title: str) -> str:
    """Escape a title for inline HTML, rendering `code` spans as <code>."""
    escaped = html.escape(title, quote=False)
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)


def prefix_series_title(body: str, meta: BlogMeta) -> str:
    """Prefix the H1 with the series name, unless it already leads with it.

    ``# The Demos`` -> ``# How Hop3 is Tested -- The Demos``. The landing post,
    whose title *is* the series name, is left untouched.
    """

    def repl(match: re.Match) -> str:
        title = match.group(1).strip()
        if title.lower().startswith(meta.series.lower()):
            return match.group(0)
        return f"# {meta.series} — {title}"

    return re.sub(r"^#\s+(.+)$", repl, body, count=1, flags=re.MULTILINE)


def render_series_nav(meta: BlogMeta, series_posts: list[BlogMeta]) -> str:
    """Render the 'Part N of the series …' box listing every post in order."""
    items = []
    current_index = 0
    for i, post in enumerate(series_posts, start=1):
        label = _title_to_inline_html(post.title)
        if post.filename == meta.filename:
            current_index = i
            items.append(f'    <li class="current" aria-current="true">{label}</li>')
        else:
            # Root-relative href: zensical rewrites RELATIVE hrefs in raw HTML
            # (adding a "../" for the directory-URL transform), which would break
            # a hand-computed relative path. Absolute site paths are left as-is.
            items.append(f'    <li><a href="/blog/posts/{post.slug}/">{label}</a></li>')

    series_name = html.escape(meta.series, quote=False)
    return (
        '\n<nav class="series-nav" aria-label="Series navigation">\n'
        f'  <p class="series-nav-title">Part {current_index} of the series '
        f"<strong>{series_name}</strong></p>\n"
        '  <ol class="series-nav-list">\n'
        + "\n".join(items)
        + "\n  </ol>\n</nav>\n"
    )


def preprocess_blog_post(
    src_path: Path,
    dest_path: Path,
    series_map: dict[str, list[BlogMeta]] | None = None,
) -> BlogMeta | None:
    """Preprocess a single blog post.

    Returns BlogMeta if the post was processed, None if it was skipped (draft).
    """
    series_map = series_map or {}
    content = src_path.read_text()

    # Parse frontmatter
    metadata, body = parse_frontmatter(content)
    meta = extract_meta(metadata, body, src_path.name)

    # Skip drafts
    if meta.is_draft:
        print(f"  Skipping draft: {src_path.name}")
        return None

    # Add blank lines before lists
    body = add_blank_lines_before_lists(body)

    # Series: prefix the title and build the "Part N of the series …" box.
    series_nav = ""
    series_posts = series_map.get(meta.series) if meta.series else None
    if series_posts and len(series_posts) > 1:
        body = prefix_series_title(body, meta)
        series_nav = render_series_nav(meta, series_posts)

    # Add metadata (and the series box) after title
    body = add_metadata_after_title(body, meta, series_nav)

    # Reconstruct with frontmatter
    # Note: Generated comment goes AFTER frontmatter since --- must be first line
    if metadata:
        yaml_str = yaml.dump(metadata, default_flow_style=False, allow_unicode=True)
        processed = f"---\n{yaml_str}---\n\n{GENERATED_COMMENT}{body}"
    else:
        processed = GENERATED_COMMENT + body

    # Write to destination
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(processed)

    return meta


def generate_tag_page(tag: str, posts: list[BlogMeta], dest_dir: Path) -> None:
    """Generate a tag index page."""
    tag_slug = tag.lower().replace(" ", "-")
    dest_path = dest_dir / f"{tag_slug}.md"

    # Sort posts by date (newest first)
    sorted_posts = sorted(
        [p for p in posts if p.date],
        key=lambda p: p.date,  # type: ignore
        reverse=True,
    )

    lines = [
        GENERATED_COMMENT.strip(),
        "",
        f"# Posts tagged: {tag}",
        "",
    ]

    if sorted_posts:
        for post in sorted_posts:
            date_str = post.date.strftime("%Y-%m-%d") if post.date else ""
            # Link to the post
            lines.append(f"- **{date_str}**: [{post.title}](../posts/{post.filename})")
    else:
        lines.append("*No posts with this tag.*")

    lines.extend([
        "",
        "---",
        "",
        "[&larr; Back to Blog](../index.md)",
    ])

    dest_path.write_text("\n".join(lines))


def generate_tags_index(all_tags: dict[str, list[BlogMeta]], dest_dir: Path) -> None:
    """Generate the main tags index page."""
    dest_path = dest_dir / "index.md"

    # Sort tags alphabetically
    sorted_tags = sorted(all_tags.keys())

    lines = [
        GENERATED_COMMENT.strip(),
        "",
        "# Blog Tags",
        "",
        "Browse posts by topic:",
        "",
    ]

    for tag in sorted_tags:
        tag_slug = tag.lower().replace(" ", "-")
        count = len(all_tags[tag])
        lines.append(f"- [{tag}]({tag_slug}.md) ({count} post{'s' if count != 1 else ''})")

    lines.extend([
        "",
        "---",
        "",
        "[&larr; Back to Blog](../index.md)",
    ])

    dest_path.write_text("\n".join(lines))


def generate_blog_index(
    posts: list[BlogMeta],
    dest_path: Path,
    series_map: dict[str, list[BlogMeta]] | None = None,
) -> None:
    """Generate the main blog index page grouped by year and month.

    Posts are listed newest-first. Within the same date, a series is shown in
    *reverse* order (the latest part on top, down to part 1), so a freshly
    published series reads top-down as 5, 4, 3, 2, 1. Non-series posts (no
    ``series_order``) keep their existing relative order. Each series entry is
    annotated with its "Part N of M".
    """
    # filename -> "Part N of M" label, for series with more than one part.
    part_label: dict[str, str] = {}
    for series_posts in (series_map or {}).values():
        total = len(series_posts)
        if total < 2:
            continue
        for i, post in enumerate(series_posts, start=1):
            part_label[post.filename] = f" *(Part {i} of {total})*"

    sorted_posts = sorted(
        [p for p in posts if p.date],
        key=lambda p: (p.date, p.series_order if p.series_order is not None else -1),
        reverse=True,
    )

    lines = [
        GENERATED_COMMENT.strip(),
        "",
        "# Blog",
        "",
        "News, announcements, and updates from the Hop3 project.",
        "",
    ]

    # Group by year and month
    current_year = None
    current_month = None

    for post in sorted_posts:
        if not post.date:
            continue

        year = post.date.year
        month = post.date.strftime("%B")  # Full month name

        if year != current_year:
            if current_year is not None:
                lines.append("")  # Blank line before new year (except first)
            lines.append(f"## {year}")
            lines.append("")
            current_year = year
            current_month = None

        if month != current_month:
            if current_month is not None:
                lines.append("")  # Blank line before new month (except first)
            lines.append(f"### {month}")
            lines.append("")
            current_month = month

        # Format: - **March 20**: [Title](posts/filename.md) - Description *(Part N of M)*
        date_str = post.date.strftime("%B %d")
        desc = f" - {post.description}" if post.description else ""
        part = part_label.get(post.filename, "")
        lines.append(
            f"- **{date_str}**: [{post.title}](posts/{post.filename}){desc}{part}"
        )

    lines.extend([
        "",
        "---",
        "",
        "Want to stay updated? Follow us on [GitHub](https://github.com/abilian/hop3).",
        "",
    ])

    dest_path.write_text("\n".join(lines))


def build_series_map(src_dir: Path) -> dict[str, list[BlogMeta]]:
    """Map each series name to its published posts, ordered for display.

    Order key: ``series_order`` (ascending) when given, then date, then filename.
    Drafts are excluded so they never appear in a sibling's box.
    """
    series_map: dict[str, list[BlogMeta]] = {}
    for src_path in sorted(src_dir.glob("*.md")):
        metadata, body = parse_frontmatter(src_path.read_text())
        meta = extract_meta(metadata, body, src_path.name)
        if meta.is_draft or not meta.series:
            continue
        series_map.setdefault(meta.series, []).append(meta)

    for posts in series_map.values():
        posts.sort(
            key=lambda p: (
                p.series_order if p.series_order is not None else 10**9,
                p.date or date.max,
                p.filename,
            )
        )
    return series_map


def preprocess_all() -> None:
    """Preprocess all blog posts and generate tag pages and blog index."""
    if not BLOG_SRC_DIR.exists():
        print(f"Warning: {BLOG_SRC_DIR} does not exist")
        return

    # Clean destinations
    if BLOG_DEST_DIR.exists():
        shutil.rmtree(BLOG_DEST_DIR)
    BLOG_DEST_DIR.mkdir(parents=True)

    if TAGS_DEST_DIR.exists():
        shutil.rmtree(TAGS_DEST_DIR)
    TAGS_DEST_DIR.mkdir(parents=True)

    # First pass: discover series membership across all (published) posts, so
    # each post's box can list its siblings in order.
    series_map = build_series_map(BLOG_SRC_DIR)
    for name, posts in series_map.items():
        print(f"  Series '{name}': {len(posts)} parts")

    # Process each post and collect tags
    all_tags: dict[str, list[BlogMeta]] = {}
    all_posts: list[BlogMeta] = []
    published_count = 0
    draft_count = 0

    for src_path in sorted(BLOG_SRC_DIR.glob("*.md")):
        dest_path = BLOG_DEST_DIR / src_path.name
        meta = preprocess_blog_post(src_path, dest_path, series_map)

        if meta is None:
            draft_count += 1
            continue

        published_count += 1
        all_posts.append(meta)

        # Collect tags
        for tag in meta.tags:
            if tag not in all_tags:
                all_tags[tag] = []
            all_tags[tag].append(meta)

    # Generate tag pages
    for tag, posts in all_tags.items():
        generate_tag_page(tag, posts, TAGS_DEST_DIR)

    # Generate tags index
    if all_tags:
        generate_tags_index(all_tags, TAGS_DEST_DIR)

    # Generate blog index
    generate_blog_index(all_posts, BLOG_INDEX_PATH, series_map)

    print(f"Preprocessed {published_count} blog posts, skipped {draft_count} drafts")
    print(f"Generated {len(all_tags)} tag pages in {TAGS_DEST_DIR}")
    print(f"Generated blog index at {BLOG_INDEX_PATH}")


if __name__ == "__main__":
    preprocess_all()
