# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
Static WCAG checks on the dashboard templates.

Each check pins a class of defect the 2026-10 audit found by reading the
templates, so a new template cannot reintroduce it:

- a ``<label for>`` that names no control: five search and filter fields had
  no accessible name (WCAG 1.3.1, 4.1.2);
- a button with no text and no ``aria-label``: the env-var copy button was
  announced as just "button" (4.1.2);
- an ``<svg>`` or ``<img>`` that says nothing about whether it is decorative
  (1.1.1);
- a ``<select>`` that navigates on change (3.2.2);
- a breadcrumb naming a section differently from the main navigation, as
  "Dashboard" and "Services" did (3.2.4);
- streamed log text inserted as HTML, which let an app's log line run script
  in the operator's session.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from hop3.server.catalog.models import FALLBACK_COLORS

TEMPLATE_DIR = Path(__file__).parents[3] / "src/hop3/server/templates"
TEMPLATES = sorted(TEMPLATE_DIR.rglob("*.html"))

#: Void elements never get an end tag, so they never enter the open-tag stack.
_VOID = {"img", "input", "br", "hr", "meta", "link", "path", "circle", "source"}


class _Scan(HTMLParser):
    """Collect what the checks need in one pass over a template."""

    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.label_targets: list[tuple[str, int]] = []
        self.unnamed_buttons: list[int] = []
        self.unlabelled_svgs: list[int] = []
        self.images_without_alt: list[int] = []
        self._buttons: list[dict] = []  # open buttons: line, named so far
        self._stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        line = self.getpos()[0]
        if attr.get("id"):
            self.ids.add(attr["id"])
        if tag == "label" and attr.get("for"):
            self.label_targets.append((attr["for"], line))
        if tag == "svg" and not _has_name(attr) and attr.get("aria-hidden") != "true":
            self.unlabelled_svgs.append(line)
        if tag == "img" and "alt" not in attr and ":alt" not in attr:
            self.images_without_alt.append(line)
        if tag == "button":
            self._buttons.append({"line": line, "named": _has_name(attr)})
        elif self._buttons and ("x-text" in attr or _has_name(attr)):
            self._buttons[-1]["named"] = True
        if tag not in _VOID:
            self._stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag == "button" and self._buttons:
            button = self._buttons.pop()
            if not button["named"]:
                self.unnamed_buttons.append(button["line"])
        if tag in self._stack:
            while self._stack.pop() != tag:
                pass

    def handle_data(self, data: str) -> None:
        if self._buttons and data.strip() and "svg" not in self._stack:
            self._buttons[-1]["named"] = True


def _has_name(attr: dict[str, str | None]) -> bool:
    return any(key in attr for key in ("aria-label", ":aria-label", "aria-labelledby"))


def _scan(template: Path) -> _Scan:
    scan = _Scan()
    scan.feed(template.read_text())
    return scan


def _ids(template: Path) -> str:
    return str(template.relative_to(TEMPLATE_DIR))


@pytest.mark.parametrize("template", TEMPLATES, ids=_ids)
def test_every_label_names_a_control(template):
    scan = _scan(template)
    dangling = [
        (target, line) for target, line in scan.label_targets if target not in scan.ids
    ]
    assert not dangling, f"<label for> with no matching id: {dangling}"


@pytest.mark.parametrize("template", TEMPLATES, ids=_ids)
def test_every_button_has_a_name(template):
    assert not _scan(template).unnamed_buttons, "button with no text and no aria-label"


@pytest.mark.parametrize("template", TEMPLATES, ids=_ids)
def test_images_say_whether_they_are_decorative(template):
    scan = _scan(template)
    assert not scan.unlabelled_svgs, "<svg> without aria-hidden or a name"
    assert not scan.images_without_alt, "<img> without alt"


@pytest.mark.parametrize("template", TEMPLATES, ids=_ids)
def test_no_select_navigates_on_change(template):
    assert "onchange=" not in template.read_text()


def test_breadcrumbs_use_the_navigation_labels():
    base = (TEMPLATE_DIR / "base.html").read_text()
    nav = dict(re.findall(r'\("(/dashboard[^"]*)", "([^"]+)"\)', base))
    assert nav, "main navigation items not found in base.html"

    wrong = []
    for template in TEMPLATES:
        for call in re.findall(r"breadcrumb\(\[(.*?)\]\)", template.read_text()):
            for label, href in re.findall(r'\("([^"]+)", "(/dashboard[^"]*)"\)', call):
                if href in nav and nav[href] != label:
                    wrong.append((_ids(template), label, nav[href]))
    assert not wrong, f"breadcrumb label differs from the navigation: {wrong}"


def test_log_viewer_never_inserts_streamed_text_as_html():
    logs = (TEMPLATE_DIR / "dashboard/logs.html").read_text()
    for html_sink in ("hx-swap", "sse-swap", "innerHTML", "x-html"):
        assert html_sink not in logs


@pytest.mark.parametrize("color", FALLBACK_COLORS)
def test_fallback_icon_colors_reach_aa_against_white(color):
    assert _contrast(color, "#ffffff") >= 4.5


def _contrast(a: str, b: str) -> float:
    light, dark = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def _luminance(color: str) -> float:
    def channel(hex_pair: str) -> float:
        c = int(hex_pair, 16) / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(color[i : i + 2]) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b
