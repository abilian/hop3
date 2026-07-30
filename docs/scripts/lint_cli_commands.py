# Copyright (c) 2023-2026, Abilian SAS

"""
Check that every `hop3 ...` invocation in the docs names a real command.

Documentation rots silently when a command is renamed: `hop3 run` became
`hop3 app run`, `hop3 server add` became `hop3 init`, and nothing failed —
the prose just started lying. This resolves every invocation in `docs/src/`
against the command surface the CLI actually exposes, so a rename breaks the
build instead of the reader's first command.

The surface is assembled offline from three sources, so this runs in CI
without a server:

- the RPC dispatch table (`hop3.server.controllers.rpc.commands`) — core
  commands plus everything plugins contribute through `cli_commands()`. This
  is the table the server dispatches against, reused rather than re-derived so
  the linter cannot drift from the dispatcher;
- the client-side local commands (`context`, `init`, `use`, `tunnel`, …),
  which never reach the server;
- the built-in alias table, without which `hop3 apps` reads as unknown.

Two failure modes are reported. An **unknown command** is an invocation whose
leading tokens match nothing. An **unknown subcommand** is one whose leading
tokens resolve to a namespace (`app`, `addon postgres`) but whose next token
is not one of that namespace's verbs — the case a rename produces, where
`hop3 app logs` would otherwise quietly resolve to the bare `app` group.

Only invocations in *command position* count: at the start of a line, after a
shell prompt, or after a pipe/`&&`/`;`. Otherwise `git push hop3 main` and
`sudo -u hop3 psql` — where `hop3` is a remote or a username — read as
commands.

Two escape hatches, because some docs describe commands that deliberately do
not exist (a removed command named in a migration note, a typo demonstrating
did-you-mean):

    <!-- lint-cli-ignore: reason -->        the next code block or line
    <!-- lint-cli-ignore-file: reason -->   the whole file

ADRs and the changelog are excluded wholesale: both document proposed and
removed commands as a matter of course, so linting them is a category error.

Usage:
    python scripts/lint_cli_commands.py [PATH ...]     # default: src/
"""

from __future__ import annotations

import difflib
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# ADR 036 D3/D12: three levels is the guideline, four the hard ceiling. Mirrors
# `_MAX_COMMAND_DEPTH` in the RPC dispatcher.
MAX_COMMAND_DEPTH = 4

# Paths that document commands which intentionally do not exist: ADRs propose
# and reject command surfaces, and the changelog names commands precisely
# because they were removed.
DEFAULT_EXCLUDES = ("developers/adrs/", "reference/changelog.md")

# A suppression carries its reason: `<!-- lint-cli-ignore: why -->`.
IGNORE_BLOCK_RE = re.compile(r"^<!--\s*lint-cli-ignore\s*(?::[^>]*)?-->$")
IGNORE_FILE_RE = re.compile(r"<!--\s*lint-cli-ignore-file\s*(?::[^>]*)?-->")

# The binary is installed as both `hop3` and `hop`.
INVOCATION_RE = re.compile(r"\bhop3?\s+([a-z][\w:-]*(?:\s+[^\s`|;&>()]+)*)")

# What may precede an invocation for it to be a command and not an argument:
# start of snippet, a shell prompt, or a command separator.
COMMAND_POSITION_RE = re.compile(r"(?:^|[|;&(]|\$\(|`|^\s*[$#>❯❮]\s*)\s*$")

# A bare word that could plausibly be a subcommand. Deliberately narrow: it
# excludes `db.example.com` (a domain), `FOO=bar` (an assignment),
# `<backup-id>` (a placeholder) and `$APP` (a variable), so a positional
# argument is not mistaken for a verb.
SUBCOMMAND_RE = re.compile(r"^[a-z][a-z0-9-]*$")

# Stop collecting tokens at the first one that cannot be part of a command name.
STOP_PREFIXES = ("-", "$", "<", "{", '"', "'")

FENCE_RE = re.compile(r"^\s*(?:```|~~~)(\w*)")
INLINE_CODE_RE = re.compile(r"`([^`]+)`")

# Fenced blocks whose contents are shell. An untagged fence counts: the docs
# use bare ``` for shell often enough that skipping them would lose coverage.
SHELL_LANGS = {"", "bash", "sh", "shell", "console", "shell-session", "zsh"}

# `hop3 help <command>` takes a command name as its argument, so its "sub"
# tokens are commands rather than verbs of a `help` namespace.
TAKES_COMMAND_ARGUMENT = {("help",)}


DEPRECATED_ALIAS = "deprecated alias"


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    invocation: str
    reason: str
    suggestion: str

    @property
    def is_error(self) -> bool:
        """A deprecated alias still runs, so it is a warning; anything else is
        a command the reader cannot execute."""
        return self.reason != DEPRECATED_ALIAS

    def format(self, root: Path) -> str:
        try:
            where = self.path.relative_to(root)
        except ValueError:
            where = self.path
        if not self.suggestion:
            hint = ""
        elif self.reason == DEPRECATED_ALIAS:
            hint = f"  (use `hop3 {self.suggestion}`)"
        else:
            hint = f"  (did you mean `hop3 {self.suggestion}`?)"
        return f"{where}:{self.line}: `hop3 {self.invocation}` — {self.reason}{hint}"


@dataclass(frozen=True)
class Surface:
    """The command surface the CLI actually exposes."""

    names: frozenset[tuple[str, ...]]
    heads: frozenset[str]
    # Local commands dispatch client-side and their subcommands live in
    # handler bodies, not a registry. Treated as opaque: we check that the head
    # exists and stop there, rather than inventing a second list that drifts.
    opaque_heads: frozenset[str]
    # Legacy spellings the dispatcher still accepts, mapped to their canonical
    # form. These *work*, so they are not errors of fact — but documentation is
    # the teaching surface, and teaching a deprecated spelling is how a rename
    # fails to land. Reported so the docs name the canonical command.
    deprecated: dict[tuple[str, ...], tuple[str, ...]]

    def is_namespace(self, prefix: tuple[str, ...]) -> bool:
        return any(
            name[: len(prefix)] == prefix and len(name) > len(prefix)
            for name in self.names
        )

    def canonical_form(
        self, prefix: tuple[str, ...], rest: list[str]
    ) -> tuple[str, ...]:
        """The canonical spelling of `prefix`, or () if it is already canonical.

        Honours the collision-with-subcommand rule (`aliases.py`): a plural
        alias does not fire when the next token is a real subcommand of the
        namespace it expands to, so `hop3 addons create` means `addon create`,
        not `addon list create`. Reporting the raw expansion there would send
        the reader to the wrong command.
        """
        expansion = self.deprecated.get(prefix)
        if not expansion:
            return ()
        if rest and (expansion[0], rest[0]) in self.names:
            namespace = (expansion[0],)
            return () if namespace == prefix else namespace
        return expansion


def load_surface() -> Surface:
    """Assemble the command surface. Importing the RPC controller builds the
    dispatch table as a side effect, which is what forces plugin loading."""
    from hop3.server.controllers.rpc import commands as rpc_commands
    from hop3_cli.commands.local import LOCAL_COMMANDS
    from hop3_cli.core.aliases import CORE_ALIASES

    names = {name for name in rpc_commands if name}
    names |= {(local,) for local in LOCAL_COMMANDS}
    names |= {(alias.source_token,) for alias in CORE_ALIASES}

    # A table key that is not the command's own name is a legacy alias
    # (`run` → `app run`, `domains` → `domain`, `config` → `env`).
    deprecated = {
        key: command.name
        for key, command in rpc_commands.items()
        if key and command.name and key != command.name
    }
    deprecated |= {
        (alias.source_token,): alias.expansion
        for alias in CORE_ALIASES
        if alias.expansion
    }
    return Surface(
        names=frozenset(names),
        heads=frozenset(name[0] for name in names),
        opaque_heads=frozenset(LOCAL_COMMANDS),
        deprecated=deprecated,
    )


def iter_snippets(text: str):
    """Yield (line number, snippet, offset) for shell code and inline code.

    `offset` locates the snippet within its line so command position can be
    judged against what precedes it.
    """
    fence_lang: str | None = None
    suppress_block = False
    armed = False

    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()

        if IGNORE_BLOCK_RE.match(stripped):
            armed = True
            continue

        fence = FENCE_RE.match(line)
        if fence:
            if fence_lang is None:
                fence_lang = fence.group(1).lower()
                suppress_block, armed = armed, False
            else:
                fence_lang, suppress_block = None, False
            continue

        if fence_lang is not None:
            if fence_lang in SHELL_LANGS and not suppress_block:
                yield lineno, line, 0
            continue

        spans = list(INLINE_CODE_RE.finditer(line))
        if armed and spans:
            armed = False
            continue
        for span in spans:
            yield lineno, span.group(1), span.start(1)


def in_command_position(line: str, offset: int) -> bool:
    return bool(COMMAND_POSITION_RE.search(line[:offset]))


def command_tokens(invocation: str) -> list[str]:
    """Take the leading tokens that could name a command."""
    tokens: list[str] = []
    for token in invocation.split():
        if token.startswith(STOP_PREFIXES) or len(tokens) >= MAX_COMMAND_DEPTH:
            break
        tokens.append(token)
    return tokens


def resolve(tokens: list[str], surface: Surface) -> tuple[str, ...]:
    """Longest matching prefix of `tokens`, or () if nothing matches."""
    for size in range(min(len(tokens), MAX_COMMAND_DEPTH), 0, -1):
        prefix = tuple(tokens[:size])
        if prefix in surface.names:
            return prefix
    return ()


def suggest(tokens: list[str], surface: Surface) -> str:
    target = " ".join(tokens[:2])
    pool = [" ".join(name) for name in surface.names]
    matches = difflib.get_close_matches(target, pool, n=1, cutoff=0.6)
    return matches[0] if matches else ""


def check_invocation(tokens: list[str], surface: Surface) -> tuple[str, str] | None:
    """Return (reason, suggestion) if this invocation is wrong."""
    prefix = resolve(tokens, surface)
    if not prefix:
        return "unknown command", suggest(tokens, surface)

    canonical = surface.canonical_form(prefix, tokens[len(prefix) :])
    if canonical:
        return DEPRECATED_ALIAS, " ".join(canonical)

    rest = tokens[len(prefix) :]
    if not rest or not SUBCOMMAND_RE.match(rest[0]):
        return None
    if prefix[0] in surface.opaque_heads or prefix in TAKES_COMMAND_ARGUMENT:
        return None
    # `prefix` is a namespace only if some real command extends it. Without
    # this guard, `hop3 addon attach myapp-db` reads as a bad subcommand.
    if not surface.is_namespace(prefix) or prefix + (rest[0],) in surface.names:
        return None
    return (
        f"`{' '.join(prefix)}` has no `{rest[0]}` subcommand",
        suggest(tokens, surface),
    )


def check_file(path: Path, surface: Surface) -> list[Finding]:
    text = path.read_text(encoding="utf-8")
    if IGNORE_FILE_RE.search(text):
        return []

    findings: list[Finding] = []
    seen: set[tuple[int, str]] = set()
    for lineno, snippet, offset in iter_snippets(text):
        for match in INVOCATION_RE.finditer(snippet):
            if not in_command_position(snippet, offset + match.start()):
                continue
            tokens = command_tokens(match.group(1))
            if not tokens:
                continue
            key = (lineno, " ".join(tokens))
            if key in seen:
                continue
            seen.add(key)
            problem = check_invocation(tokens, surface)
            if problem:
                findings.append(Finding(path, lineno, " ".join(tokens), *problem))
    return findings


def collect_files(targets: list[Path], root: Path) -> list[Path]:
    files = {f for t in targets for f in ([t] if t.is_file() else t.rglob("*.md"))}
    return sorted(
        f
        for f in files
        if not any(x in f.resolve().as_posix() for x in DEFAULT_EXCLUDES)
    )


def main(argv: list[str]) -> int:
    root = Path(__file__).resolve().parent.parent
    args = argv[1:]
    strict = "--strict" in args
    targets = [Path(a) for a in args if not a.startswith("-")] or [root / "src"]

    surface = load_surface()
    files = collect_files(targets, root)
    findings = [f for path in files for f in check_file(path, surface)]

    errors = [f for f in findings if f.is_error]
    warnings = [f for f in findings if not f.is_error]

    for finding in errors:
        print(f"error: {finding.format(root)}")
    for finding in warnings:
        print(f"warning: {finding.format(root)}")

    print(
        f"\n{len(files)} files checked against {len(surface.names)} commands: "
        f"{len(errors)} error(s), {len(warnings)} warning(s)."
    )
    if warnings and not strict:
        print(
            "Deprecated aliases run but should not be taught; --strict fails on them."
        )
    return 1 if errors or (strict and warnings) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
