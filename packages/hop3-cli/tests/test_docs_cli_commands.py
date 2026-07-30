# Copyright (c) 2023-2026, Abilian SAS

"""The docs must only name commands the CLI actually has.

`hop3 run` → `hop3 app run` and `hop3 server add` → `hop3 init` both happened
without a single test failing, and the documentation quietly kept teaching the
old spelling. This is the gate that stops the next rename doing the same:
`docs/scripts/lint_cli_commands.py` resolves every documented invocation
against the real dispatch table, and this pins it in the fast lane.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
LINTER = REPO_ROOT / "docs" / "scripts" / "lint_cli_commands.py"
DOCS_SRC = REPO_ROOT / "docs" / "src"


def _load_linter():
    spec = importlib.util.spec_from_file_location("lint_cli_commands", LINTER)
    if spec is None or spec.loader is None:
        msg = f"cannot load the docs CLI linter from {LINTER}"
        raise RuntimeError(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


lint = _load_linter()


@pytest.fixture(scope="module")
def surface():
    """A small, explicit surface — the resolution rules are what is under test,
    not the real command list (which changes every release)."""
    names = {
        ("app",),
        ("app", "run"),
        ("app", "logs"),
        ("addon",),
        ("addon", "attach"),
        ("addon", "postgres"),
        ("addon", "postgres", "query"),
        ("deploy",),
        ("help",),
        ("context",),
        ("run",),
        ("apps",),
    }
    return lint.Surface(
        names=frozenset(names),
        heads=frozenset(n[0] for n in names),
        opaque_heads=frozenset({"context"}),
        deprecated={("run",): ("app", "run"), ("apps",): ("app", "list")},
    )


def check(text: str, surface) -> list[str]:
    tokens = lint.command_tokens(text)
    problem = lint.check_invocation(tokens, surface)
    return [problem[0]] if problem else []


class TestResolution:
    def test_real_command_passes(self, surface):
        assert check("app run --app myapp", surface) == []

    def test_deepest_match_wins(self, surface):
        assert check("addon postgres query --app x", surface) == []

    def test_unknown_head_is_an_error(self, surface):
        assert check("server add prod", surface) == ["unknown command"]

    def test_unknown_subcommand_of_a_namespace(self, surface):
        # The failure mode a rename produces: without this, `app frobnicate`
        # would resolve to the bare `app` group and pass silently.
        (reason,) = check("app frobnicate", surface)
        assert reason == "`app` has no `frobnicate` subcommand"

    def test_positional_argument_is_not_a_subcommand(self, surface):
        # `addon attach` takes an addon name; it is not a namespace.
        assert check("addon attach myapp-db", surface) == []

    def test_flags_end_the_command_name(self, surface):
        assert lint.command_tokens("app logs --app myapp --lines 50") == [
            "app",
            "logs",
        ]

    def test_local_commands_are_opaque(self, surface):
        # `context use` dispatches client-side; its verbs live in a handler
        # body, not a registry, so we check the head and stop.
        assert check("context use prod", surface) == []


class TestDeprecatedAliases:
    def test_alias_is_reported_with_its_canonical_form(self, surface):
        tokens = lint.command_tokens("run --app myapp")
        reason, suggestion = lint.check_invocation(tokens, surface)
        assert reason == lint.DEPRECATED_ALIAS
        assert suggestion == "app run"

    def test_alias_is_a_warning_not_an_error(self, surface):
        finding = lint.Finding(Path("x.md"), 1, "run", lint.DEPRECATED_ALIAS, "app run")
        assert not finding.is_error

    def test_plural_alias_does_not_fire_before_a_real_subcommand(self, surface):
        # ADR 036 D9 collision rule: `hop3 apps run` means `app run`, not
        # `app list run`. Reporting the raw expansion would misdirect.
        assert surface.canonical_form(("apps",), ["run"]) == ("app",)


class TestCommandPosition:
    @pytest.mark.parametrize(
        "line",
        [
            "git push hop3 main",
            "sudo -u hop3 psql",
            "ssh hop3 deploy",
        ],
    )
    def test_hop3_as_an_argument_is_not_an_invocation(self, line):
        match = lint.INVOCATION_RE.search(line)
        assert match, "regex should still find the text"
        assert not lint.in_command_position(line, match.start())

    @pytest.mark.parametrize(
        "line",
        [
            "hop3 app run",
            "$ hop3 app run",
            "make build && hop3 deploy",
            "hop3 app list | grep web",
        ],
    )
    def test_real_invocations_are_in_command_position(self, line):
        match = lint.INVOCATION_RE.search(line)
        assert match
        assert lint.in_command_position(line, match.start())


class TestSuppression:
    def test_ignore_marker_skips_the_next_block(self, tmp_path):
        doc = tmp_path / "d.md"
        doc.write_text(
            "<!-- lint-cli-ignore: deliberate typo -->\n\n```bash\nhop3 nope\n```\n"
        )
        assert lint.check_file(doc, _real_surface()) == []

    def test_without_the_marker_the_same_block_fails(self, tmp_path):
        doc = tmp_path / "d.md"
        doc.write_text("```bash\nhop3 nope\n```\n")
        assert len(lint.check_file(doc, _real_surface())) == 1

    def test_file_level_marker(self, tmp_path):
        doc = tmp_path / "d.md"
        doc.write_text("<!-- lint-cli-ignore-file: historical -->\n\n`hop3 nope`\n")
        assert lint.check_file(doc, _real_surface()) == []


def _real_surface():
    names = {("deploy",)}
    return lint.Surface(
        names=frozenset(names),
        heads=frozenset({"deploy"}),
        opaque_heads=frozenset(),
        deprecated={},
    )


class TestPublishedDocs:
    """The gate itself, against the real command surface and the real docs."""

    def test_no_documented_command_is_unknown(self):
        surface = lint.load_surface()
        files = lint.collect_files([DOCS_SRC], REPO_ROOT / "docs")
        assert files, "no docs found — the path is wrong, not the docs empty"

        errors = [
            f for path in files for f in lint.check_file(path, surface) if f.is_error
        ]
        assert not errors, "docs name commands that do not exist:\n" + "\n".join(
            f.format(REPO_ROOT / "docs") for f in errors
        )

    def test_the_gate_would_catch_a_removed_command(self, tmp_path):
        # Mutation check: if resolution ever falls open, the test above turns
        # into a tautology. This proves it still rejects something.
        doc = tmp_path / "d.md"
        doc.write_text("```bash\nhop3 server add prod\n```\n")
        findings = lint.check_file(doc, lint.load_surface())
        assert [f.reason for f in findings] == ["unknown command"]
