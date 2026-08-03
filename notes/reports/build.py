#!/usr/bin/env python3
"""
Build a PDF from a Hop3 technical report written in Markdown.

The markdown is converted to Typst with `md2typst`, then a generated
`build/<name>/report.typ` applies `report-style.typ`. The style owns every
visual decision, so this script only has to hand it a body and the cover
metadata.

    ./build.py                # every TR-*.md in this directory
    ./build.py TR-03.md       # just that one
    ./build.py --keep TR-03.md    # ...and leave build/ in place

Two things are taken out of the markdown on the way through, because the style
supplies them and having both would mean two of each:

  * the front matter — the `# Title` and the `**Key:** value` block under it,
    which become the cover;
  * a hand-written "Contents" section, which becomes `#outline()`.

Everything after that is the body, and its `##` sections arrive in Typst as
level-2 headings.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILD = HERE / "build"
STYLE = "report-style.typ"

#: The reports this builds when given no arguments.
DEFAULT_GLOB = "TR-*.md"

#: A hand-written table of contents, up to (not including) the next `## `.
#: Case-insensitive because the series spells it both "Contents" and "Table of
#: Contents"; a spelling this misses leaves a duplicate TOC in the PDF, which
#: is easy to miss in a 37-page document.
TOC_SECTION = re.compile(
    r"^## (?:table of )?contents\b.*?(?=^## )",
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)

#: A front-matter metadata line: `**Authors:** Abilian SAS`.
META_LINE = re.compile(r"^\*\*(?P<key>[^:*]+):\*\*\s*(?P<value>.*)$")

#: A front-matter line that is bold and nothing else: `**Technical Report TR-01**`.
KICKER_LINE = re.compile(r"^\*\*(?P<text>[^:*][^*]*)\*\*$")

#: A filename that names a report in the series, e.g. `TR-03`.
REPORT_ID = re.compile(r"TR-\d+", re.IGNORECASE)

#: A fenced ```mermaid block, pre-rendered to PDF before md2typst runs.
MERMAID_BLOCK = re.compile(
    r"^```mermaid\s*\n(?P<code>.*?)^```\s*$\n", re.MULTILINE | re.DOTALL
)

#: `#image("…", alt: "…")` followed by an italic line: md2typst emits the two
#: separately, and a real `#figure` gives us numbering and a styled caption.
IMAGE_THEN_CAPTION = re.compile(
    r"#image\((?P<args>[^\n]*?)\)\n\n_(?P<caption>[^\n]+?)_\n",
)

#: A caption that numbers itself fights Typst's own numbering.
MANUAL_FIGURE_NUMBER = re.compile(r"^Figure\s+\d+[.:]\s*")

#: Cover fields drawn from the metadata block, in the order tried. Everything
#: else in the block is rendered as-is under the cover rule (see `report-style`)
#: rather than dropped.
AUTHOR_KEYS = ("Authors", "Author")
DATE_KEYS = ("Date",)
STATUS_KEYS = ("Version",)


def plain(text: str) -> str:
    """Markdown inline formatting to plain text, for cover metadata.

    `[hop3@abilian.com](mailto:…)` on the cover should read as the address,
    not as brackets and a URL.
    """
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    return re.sub(r"\*\*|\*|`", "", text).strip()


def split_front_matter(text: str) -> tuple[str, str, list[tuple[str, str]], str]:
    """Return (title, kicker, metadata, body).

    The head of a report is an `# H1`, optionally a bold-only line naming the
    report, then a run of `**Key:** value` lines. Collection stops at the first
    line that is none of those — a blockquote note, or the first `## ` section
    — and everything from there is body. Anything unexpected therefore stays in
    the document rather than being guessed at or silently eaten.
    """
    lines = text.splitlines()

    title = ""
    kicker = ""
    meta: list[tuple[str, str]] = []
    cut = 0

    for i, line in enumerate(lines):
        stripped = line.strip()

        if not title:
            if stripped.startswith("# "):
                title = stripped[2:].strip()
                cut = i + 1
            continue

        if not stripped:
            cut = i + 1
            continue

        if m := META_LINE.match(stripped):
            meta.append((m.group("key").strip(), m.group("value").strip()))
            cut = i + 1
            continue

        if not meta and (m := KICKER_LINE.match(stripped)):
            kicker = m.group("text").strip()
            cut = i + 1
            continue

        # Not front matter. The body starts here, blank lines and all.
        cut = i
        break

    return title, kicker, meta, "\n".join(lines[cut:])


def take(meta: list[tuple[str, str]], keys: tuple[str, ...]) -> str:
    """Pop the first matching key out of `meta` and return its plain value."""
    for i, (k, v) in enumerate(meta):
        if k in keys:
            meta.pop(i)
            return plain(v)
    return ""


def to_figures(typ: str) -> str:
    """Turn `#image(...)` + a following italic line into a captioned `#figure`."""

    def repl(m: re.Match[str]) -> str:
        caption = MANUAL_FIGURE_NUMBER.sub("", m.group("caption")).strip()
        return f"#figure(image({m.group('args')}), caption: [{caption}])\n"

    return IMAGE_THEN_CAPTION.sub(repl, typ)


def render_mermaid(md_text: str, out_dir: Path) -> str:
    """Pre-render ```mermaid blocks to PDF and reference them as images.

    md2typst's own backends are bypassed deliberately: the default `mmdr`
    layout engine mangles the report's figures (scrambled ranks, ignored
    direction hints, figures split across pages), and its `cli` backend omits
    mmdc's `--pdfFit`, leaving each diagram small on a mostly-empty fixed-size
    page. Rendering here with the reference renderer and a tight page keeps
    the figures exactly as authored.
    """
    count = 0

    def repl(m: re.Match[str]) -> str:
        nonlocal count
        count += 1
        mmd = out_dir / f"mermaid-{count}.mmd"
        pdf = out_dir / f"mermaid-{count}.pdf"
        mmd.write_text(m.group("code"))
        cmd = ["mmdc", "-i", str(mmd), "-o", str(pdf), "--pdfFit"]
        print(f"Running '{' '.join(cmd)}")
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
        )
        mmd.unlink()
        return f"![]({pdf.name})\n"

    return MERMAID_BLOCK.sub(repl, md_text)


def convert(md_text: str, out_dir: Path) -> Path:
    """Markdown body to a Typst fragment, ready to `#include`."""
    src = out_dir / "body.md"
    src.write_text(render_mermaid(md_text, out_dir))

    raw = out_dir / "body.raw.typ"
    subprocess.run(
        ["uvx", "md2typst", "-o", str(raw), str(src)],
        check=True,
        capture_output=True,
        text=True,
    )

    typ = raw.read_text()
    typ = to_figures(typ)
    # The part lives in build/<name>/, two levels below the figures directory
    # it would reference.
    typ = typ.replace('image("figures/', 'image("../../figures/')

    part = out_dir / "body.typ"
    part.write_text(typ)
    raw.unlink()
    src.unlink()
    return part


def q(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def report_typ(
    title: str,
    kicker: str,
    author: str,
    date: str,
    status: str,
    meta: list[tuple[str, str]],
    running: str,
) -> str:
    pairs = ", ".join(f'("{q(k)}", "{q(plain(v))}")' for k, v in meta)
    return (
        "\n".join([
            "// GENERATED by build.py — edit report-style.typ or the markdown, not this.",
            f'#import "../../{STYLE}": report',
            "",
            "#show: report.with(",
            f'  title: "{q(title)}",',
            f'  kicker: "{q(kicker)}",',
            f'  author: "{q(author)}",',
            f'  date: "{q(date)}",',
            f'  status: "{q(status)}",',
            f'  running: "{q(running)}",',
            f"  meta: ({pairs}{',' if len(meta) == 1 else ''}),",
            ")",
            "",
            '#include "body.typ"',
        ])
        + "\n"
    )


def page_count(pdf: Path) -> str:
    """A ` (N pages)` suffix for the build line, empty if pdfinfo is missing.

    Counting `/Type /Page` in the raw bytes is wrong for the compressed object
    streams Typst emits, so ask pdfinfo when it is there and say nothing rather
    than something false when it is not.
    """
    if not shutil.which("pdfinfo"):
        return ""
    out = subprocess.run(
        ["pdfinfo", str(pdf)], capture_output=True, text=True, check=False
    )
    m = re.search(r"^Pages:\s+(\d+)", out.stdout, re.MULTILINE)
    return f" ({m.group(1)} pages)" if m else ""


def build_one(
    source: Path, output: Path | None, status_override: str, keep: bool
) -> None:
    if not source.exists():
        msg = f"{source} not found"
        raise SystemExit(msg)

    title, kicker, meta, body = split_front_matter(source.read_text())
    if not title:
        # Without a title the cover is blank and the PDF still builds, which is
        # the kind of quietly wrong output that gets attached to a grant report.
        msg = f"{source.name}: no '# Title' heading found"
        raise SystemExit(msg)

    body = TOC_SECTION.sub("", body, count=1)

    author = take(meta, AUTHOR_KEYS)
    date = take(meta, DATE_KEYS)
    status = status_override or take(meta, STATUS_KEYS)
    # TR-03 carries no `**Technical Report TR-03**` line, so the filename
    # supplies it — but only when the filename is actually a report id, or a
    # stray `notes.md` would be captioned "TECHNICAL REPORT NOTES".
    running = source.stem
    if not kicker and REPORT_ID.fullmatch(running):
        kicker = f"Technical Report {running}"

    out_dir = BUILD / source.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    convert(body, out_dir)

    master = out_dir / "report.typ"
    master.write_text(report_typ(title, kicker, author, date, status, meta, running))

    pdf = output or source.with_suffix(".pdf")
    subprocess.run(
        ["typst", "compile", "--root", str(HERE), str(master), str(pdf)],
        check=True,
    )

    shown = pdf.relative_to(Path.cwd()) if pdf.is_relative_to(Path.cwd()) else pdf
    print(f"--> Wrote {shown}{page_count(pdf)}")

    if not keep:
        shutil.rmtree(out_dir)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "sources",
        nargs="*",
        type=Path,
        help=f"reports to build (default: every {DEFAULT_GLOB} here)",
    )
    parser.add_argument(
        "--keep", action="store_true", help="leave build/ in place afterwards"
    )
    parser.add_argument(
        "--status",
        default="",
        help='banner on the cover, e.g. "draft" (default: the report\'s Version)',
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="output path (only valid with a single source)",
    )
    args = parser.parse_args()

    tools = {
        "uvx": "install uv",
        "typst": "brew install typst",
        "mmdc": "npm install -g @mermaid-js/mermaid-cli (renders the figures)",
    }
    for tool, hint in tools.items():
        if not shutil.which(tool):
            msg = f"{tool} is not on PATH; cannot build the reports — {hint}"
            raise SystemExit(msg)

    sources = args.sources or sorted(HERE.glob(DEFAULT_GLOB))
    if not sources:
        msg = f"no {DEFAULT_GLOB} found in {HERE}"
        raise SystemExit(msg)
    if args.output and len(sources) > 1:
        msg = "--output takes a single source"
        raise SystemExit(msg)

    for source in sources:
        build_one(source, args.output, args.status, args.keep)

    if args.keep:
        print(f"--> Typst sources kept in {BUILD.relative_to(Path.cwd())}/")
    elif BUILD.exists() and not any(BUILD.iterdir()):
        BUILD.rmdir()
    return 0


if __name__ == "__main__":
    sys.exit(main())
