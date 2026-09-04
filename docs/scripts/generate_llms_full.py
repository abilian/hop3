# SPDX-FileCopyrightText: 2026 Abilian SAS <https://abilian.com>
# SPDX-License-Identifier: Apache-2.0
"""Generate site/llms-full.txt: the curated documentation in one file.

The companion to the hand-written ``src/llms.txt`` index (llmstxt.org): that
one lists where things are, this one inlines them so a model needs no further
fetches.

The page set IS the index: every page ``llms.txt`` links outside its
``## Optional`` section, in index order. Inlining the whole ``src/`` tree gave
2.8 MB (~700k tokens, a third of it ADRs), more than any context window holds;
the index's own curation is the one list to keep, and ``Optional`` is the
spec's mechanism for "skip when short on context". To change what is inlined,
edit ``llms.txt``. A link there that matches no source page fails the build.

Output goes straight to ``site/`` rather than ``src/``: it is a build artifact,
and ``zensical build`` rewrites ``site/``, so this runs after it — the same
reason the installer bundles and the JSON schema are placed there.

Usage:
    python scripts/generate_llms_full.py [--site-dir site]
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import tomllib

DOCS_DIR = Path(__file__).parent.parent
SRC_DIR = DOCS_DIR / "src"
INDEX_FILE = SRC_DIR / "llms.txt"
ZENSICAL_FILE = DOCS_DIR / "zensical.toml"

#: The llms.txt section whose links are NOT inlined (llmstxt.org: "skip if a
#: shorter context is needed").
OPTIONAL_SECTION = "## Optional"

RULE = "=" * 78


#: Filenames the site publishes as their directory's index page.
INDEX_STEMS = ("index", "README")


def site_url(base: str, rel: Path) -> str:
    """Canonical URL for a source page, matching the site's clean URLs."""
    parts = rel.with_suffix("").parts
    if parts[-1] in INDEX_STEMS:
        parts = parts[:-1]
    path = "/".join(parts)
    return f"{base}{path}/" if path else base


def index_urls(index_text: str, base: str) -> list[str]:
    """Site URLs linked from the index, in order, stopping at the Optional section."""
    urls: list[str] = []
    for line in index_text.splitlines():
        if line.startswith(OPTIONAL_SECTION):
            break
        for url in re.findall(r"\]\((https?://[^)\s]+)\)", line):
            if url.startswith(base) and url not in urls:
                urls.append(url)
    return urls


def source_page(url: str, base: str) -> Path:
    """The ``src/``-relative page a site URL is built from, or a loud error."""
    path = url[len(base) :].strip("/")
    candidates = ([Path(f"{path}.md")] if path else []) + [
        Path(path) / f"{stem}.md" for stem in INDEX_STEMS
    ]
    for rel in candidates:
        if (SRC_DIR / rel).is_file():
            return rel
    msg = f"llms.txt links {url}, but no source page builds it (tried {candidates})"
    raise FileNotFoundError(msg)


def strip_front_matter(text: str) -> str:
    """Drop a leading YAML front-matter block (icons, tags, dates)."""
    if not text.startswith("---\n"):
        return text
    end = text.find("\n---\n", 4)
    return text[end + 5 :] if end != -1 else text


def absolutise_links(text: str, page: Path, base: str) -> str:
    """
    Rewrite relative ``.md`` links to canonical site URLs.

    A reader of this file has no directory to resolve `../guides/faq.md`
    against, so every in-repo link is turned into the URL it will have on the
    site. Absolute URLs, anchors and mail links are left alone.
    """

    def replace(match: re.Match[str]) -> str:
        target, rest = match.group(1), match.group(2)
        if target.startswith(("http://", "https://", "#", "mailto:", "/")):
            return match.group(0)
        path_part, _, anchor = target.partition("#")
        if not path_part.endswith(".md"):
            return match.group(0)
        # Lexical, NOT realpath: a URL is resolved lexically by the browser,
        # and `reference/changelog.md` is a symlink to the repo-root
        # CHANGES.md — resolving it would land outside src/ and the link
        # would be left un-rewritten. (This is link rewriting, not a
        # containment check; the security rule about realpath does not apply.)
        joined = os.path.normpath(os.path.join(page.parent, path_part))
        try:
            rel = Path(joined).relative_to(SRC_DIR)
        except ValueError:
            return match.group(0)
        url = site_url(base, rel)
        return f"]({url}#{anchor}{rest})" if anchor else f"]({url}{rest})"

    # Only the target is matched, never the label: labels legitimately contain
    # brackets (``[hop3.toml `[nix]` section](config.md)``), and a
    # label-spanning pattern silently skipped every such link.
    return re.sub(r"\]\(\s*([^)\s]+)([^)]*)\)", replace, text)


def build(site_dir: Path) -> Path:
    with ZENSICAL_FILE.open("rb") as fp:
        base = tomllib.load(fp)["project"]["site_url"]

    index_text = INDEX_FILE.read_text(encoding="utf-8")
    pages = [source_page(url, base) for url in index_urls(index_text, base)]
    index_url = f"{base}llms.txt"
    preamble = (
        "> The Hop3 documentation in a single file, for language models that\n"
        "> would rather not fetch each page: every page the index at\n"
        f"> {index_url} lists, except its Optional section.\n"
    )
    note = (
        f"Every document below is preceded by its canonical URL on {base}\n"
        "Relative links have been rewritten to absolute URLs so they still\n"
        "resolve out of context.\n"
    )
    chunks = ["# Hop3 — Full Documentation\n", "\n", preamble, "\n", note, "\n"]

    for rel in pages:
        text = (SRC_DIR / rel).read_text(encoding="utf-8")
        text = absolutise_links(strip_front_matter(text), SRC_DIR / rel, base)
        chunks += [
            f"\n{RULE}\n",
            f"Source: {site_url(base, rel)}\n",
            f"{RULE}\n\n",
            text.strip(),
            "\n",
        ]

    out = site_dir / "llms-full.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(chunks), encoding="utf-8")
    size_kb = out.stat().st_size // 1024
    print(f"Wrote {out} ({len(pages)} pages, {size_kb} KB, ~{size_kb // 4}k tokens)")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--site-dir",
        default="site",
        help="Built site directory to write into (default: site)",
    )
    args = parser.parse_args()

    site_dir = Path(args.site_dir)
    if not site_dir.is_absolute():
        site_dir = DOCS_DIR / site_dir
    if not site_dir.exists():
        print(
            f"error: {site_dir} does not exist — run `zensical build` first; "
            "this writes into the built site, which that step rewrites.",
            file=sys.stderr,
        )
        return 1
    build(site_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
