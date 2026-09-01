#!/usr/bin/env python3
# Copyright (c) 2023-2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Analyse a shell history of `hop3` invocations to find real-world CLI usage.

Usage:
    python scripts/analyze-cli-history.py [HISTORY_FILE]
    python scripts/analyze-cli-history.py --self-check

Reports command and flag frequency, syntax drift (synonym groups, positional
target vs `--app`, global-flag placement), likely typos, incomplete
invocations, and history lines that still contain secrets.

Every value that looks like a secret is redacted before printing, so the
report can be pasted where the history itself cannot.
"""

from __future__ import annotations

import difflib
import re
import shlex
import string
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

DEFAULT_HISTORY = "/tmp/hop3-history.txt"

# Command groups that take a sub-command; every other first word is a leaf verb.
GROUPS = frozenset({
    "addon", "addons", "app", "apps", "auth", "backup", "catalog", "cert",
    "config", "context", "domain", "env", "help", "server", "system", "user",
})

# Flags that consume the next token, so its value is not read as a positional.
VALUE_FLAGS = frozenset({
    "--app", "--context", "--covers", "--host", "--port", "--server",
    "--status", "--url", "--username", "--with",
})

# Flags whose value is optional: `login --web` and `login --web root@host`.
OPTIONAL_VALUE_FLAGS = frozenset({"--ssh", "--web"})

SHELL_SPLIT = re.compile(r"&&|\|\||[|>;]")
WORD = re.compile(r"[a-z][a-z0-9-]*\Z")

SECRET_ASSIGN = re.compile(
    r"\b([A-Z0-9_]*(?:SECRET|TOKEN|PASSWORD|PASSWD|KEY|DSN|API)[A-Z0-9_]*)=(\S+)"
)
SECRET_URL = re.compile(r"://[^/\s:@]{12,}@")
PLACEHOLDER = re.compile(r"\A(x+|\$\(.*)\Z", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Call:
    """One `hop3 ...` invocation, split into command path, flags and arguments."""

    path: tuple[str, ...]
    flags: tuple[str, ...]
    args: tuple[str, ...]
    values: tuple[tuple[str, str], ...]
    flags_before_path: tuple[str, ...]
    raw: str

    def value(self, flag: str) -> str | None:
        return dict(self.values).get(flag)


def looks_like_host(token: str) -> bool:
    return not token.startswith("-") and ("@" in token or "." in token)


def redact(text: str) -> str:
    """Replace secret-looking values with a marker."""
    text = SECRET_ASSIGN.sub(r"\1=<redacted>", text)
    return SECRET_URL.sub("://<redacted>@", text)


def has_secret(line: str) -> bool:
    """True when the line carries something that looks like a live credential."""
    if SECRET_URL.search(line):
        return True
    return any(
        len(value) >= 16 and not PLACEHOLDER.match(value)
        for _name, value in SECRET_ASSIGN.findall(line)
    )


def tokenize(line: str) -> list[list[str]]:
    """Split a history line into the token lists of its `hop3` invocations."""
    calls = []
    for part in SHELL_SPLIT.split(line):
        try:
            tokens = shlex.split(part, comments=True)
        except ValueError:
            # Unbalanced quote from a truncated `$(...)` substitution: split naively.
            tokens = part.split()
        if tokens and tokens[0] in {"hop3", "hop"}:
            calls.append(tokens[1:])
    return calls


def parse(tokens: list[str], raw: str) -> Call:
    positionals: list[str] = []
    flags: list[str] = []
    values: list[tuple[str, str]] = []
    before_path: list[str] = []

    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token.startswith("-"):
            name, _, inline = token.partition("=")
            flags.append(name)
            if not positionals:
                before_path.append(name)
            if inline:
                values.append((name, inline))
            elif i + 1 < len(tokens) and (
                name in VALUE_FLAGS
                or (name in OPTIONAL_VALUE_FLAGS and looks_like_host(tokens[i + 1]))
            ):
                values.append((name, tokens[i + 1]))
                i += 1
        else:
            positionals.append(token)
        i += 1

    # ponytail: path depth 2 max. `addon postgres export` reads as `addon postgres`
    # + arg; that costs a few lines of noise, a real grammar costs a CLI import.
    depth = 2 if positionals[:1] and positionals[0] in GROUPS else 1
    if len(positionals) > 1 and not WORD.match(positionals[1]):
        depth = 1
    path = tuple(positionals[:depth])
    return Call(
        path, tuple(flags), tuple(positionals[depth:]), tuple(values),
        tuple(before_path), raw,
    )


def load(path: Path) -> tuple[list[Call], list[tuple[int, str]]]:
    calls: list[Call] = []
    secrets: list[tuple[int, str]] = []
    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        if has_secret(line):
            secrets.append((lineno, redact(line)))
        for tokens in tokenize(line):
            calls.append(parse(tokens, redact(line)))
    return calls, secrets


def command_of(call: Call) -> str:
    return " ".join(call.path) or "(no command)"


def top(title: str, counter: Counter[str], limit: int = 0, prefix: str = "") -> None:
    print(f"\n## {title}")
    for name, count in counter.most_common(limit or None):
        print(f"  {count:4}  {prefix}{name}")


def contexts_of(calls: list[Call]) -> Counter[str]:
    return Counter(c.value("--context") for c in calls if c.value("--context"))


def positional_vocabulary(calls: list[Call]) -> list[Counter[str]]:
    """Word counts per positional index, used to spot typos at that index."""
    by_index: list[Counter[str]] = [Counter(), Counter(), Counter()]
    for call in calls:
        words = call.path + call.args
        for index in range(min(3, len(words))):
            if WORD.match(words[index]):
                by_index[index][words[index]] += 1
    return by_index


def find_typos(calls: list[Call]) -> list[tuple[str, str, str]]:
    """Rare words that closely resemble a frequent word at the same position."""
    vocabulary = positional_vocabulary(calls)
    contexts = contexts_of(calls)
    findings: dict[str, tuple[str, str, str]] = {}

    def check(word: str, pool: Counter[str], where: str) -> None:
        if pool[word] > 1 or word in findings:
            return
        frequent = {token for token, count in pool.items() if count >= 3}
        matches = difflib.get_close_matches(word, frequent, n=1, cutoff=0.8)
        # `foo2` next to a frequent `foo` is a numbered instance, not a typo.
        if matches and word.rstrip(string.digits) != matches[0]:
            findings[word] = (word, matches[0], where)

    for call in calls:
        if call.path[-1:] == ("run",):
            continue  # `run` passes a shell command through; not CLI vocabulary
        words = call.path + call.args
        for index in range(min(3, len(words))):
            if WORD.match(words[index]):
                check(words[index], vocabulary[index], f"positional #{index}")
        context = call.value("--context")
        if context:
            check(context, contexts, "--context value")
    return sorted(findings.values())


def section_synonyms(calls: list[Call], paths: Counter[str]) -> None:
    print("\n## Synonym groups in use (both spellings appear)")
    heads = {call.path[0] for call in calls if call.path}

    def weight(head: str) -> int:
        return sum(
            count for name, count in paths.items()
            if name == head or name.startswith(head + " ")
        )

    for head in sorted(heads):
        if head + "s" in heads:
            print(f"  hop3 {head} ({weight(head)}) vs hop3 {head}s ({weight(head + 's')})")


def section_target_style(calls: list[Call]) -> None:
    print("\n## Same command with --app and with a bare positional target")
    known_apps = {c.value("--app") for c in calls if c.value("--app")}
    with_flag: dict[str, set[str]] = defaultdict(set)
    with_positional: dict[str, set[str]] = defaultdict(set)
    for call in calls:
        name = command_of(call)
        app = call.value("--app")
        if app:
            with_flag[name].add(app)
        elif call.args and call.args[0] in known_apps:
            with_positional[name].add(call.args[0])
    for name in sorted(set(with_flag) & set(with_positional)):
        print(f"  hop3 {name}: --app {min(with_flag[name])} "
              f"| positional {', '.join(sorted(with_positional[name]))}")


def section_context_placement(calls: list[Call]) -> None:
    print("\n## Placement of --context")
    before = sum(1 for c in calls if "--context" in c.flags_before_path)
    after = sum(1 for c in calls if "--context" in c.flags) - before
    print(f"  {before:4}  before the command (hop3 --context prod app status)")
    print(f"  {after:4}  after the command  (hop3 app status --context prod)")


def section_incomplete(calls: list[Call]) -> None:
    print("\n## Incomplete invocations (flag with no value)")
    dangling = {flag.lstrip("-") for flag in VALUE_FLAGS} | {""}
    for call in calls:
        tail = call.raw.split()[-1]
        if tail.startswith("-") and tail.lstrip("-") in dangling:
            print(f"  {call.raw}")


def report(calls: list[Call], secrets: list[tuple[int, str]]) -> None:
    paths = Counter(command_of(call) for call in calls)
    print(f"# hop3 CLI history: {len(calls)} invocations, {len(paths)} distinct commands")

    top("Most used commands", paths, limit=25, prefix="hop3 ")
    top("Most used flags", Counter(f for c in calls for f in c.flags), limit=20)
    top("--context values", contexts_of(calls))
    top("Group typed with no sub-command (exploring the CLI)", Counter(
        c.path[0] for c in calls
        if len(c.path) == 1 and c.path[0] in GROUPS and not c.args
    ), prefix="hop3 ")
    top("Help lookups, by command", Counter(
        command_of(c) for c in calls
        if "--help" in c.flags or c.path[:1] == ("help",)
    ), limit=15)

    section_synonyms(calls, paths)
    section_target_style(calls)
    section_context_placement(calls)

    print("\n## Likely typos")
    for word, suggestion, where in find_typos(calls):
        print(f"  {word!r} -> {suggestion!r} ({where})")

    section_incomplete(calls)

    print(f"\n## Secrets still present in the history: {len(secrets)} line(s)")
    for lineno, line in secrets:
        print(f"  line {lineno}: {line}")


def self_check() -> None:
    call = parse(shlex.split("app status --app situ-docs --context prod"), "")
    assert call.path == ("app", "status"), call.path
    assert call.value("--app") == "situ-docs"
    assert call.args == ()

    call = parse(shlex.split("--context prod app status ospobox-docs"), "")
    assert call.path == ("app", "status")
    assert call.args == ("ospobox-docs",)
    assert call.flags_before_path == ("--context",)

    call = parse(shlex.split("login --ssh root@hop3.dev"), "")
    assert call.path == ("login",), call.path
    assert call.value("--ssh") == "root@hop3.dev"
    assert parse(shlex.split("login --web"), "").value("--web") is None

    assert tokenize("hop3 apps | pbcopy") == [["apps"]]
    assert tokenize("hop3 a -y && hop3 b -y") == [["a", "-y"], ["b", "-y"]]
    assert tokenize("ls -l") == []

    line = "hop3 env set SENTRY_DSN=https://81e271568630473d8dd3ae@o44322.ingest.io/1"
    assert has_secret(line)
    assert "81e2715" not in redact(line), redact(line)
    assert not has_secret("hop3 env set TESTLAB_SECRET_KEY=xxx")

    calls = [parse(shlex.split(c), c) for c in
             ["catalog list", "catalog list", "catalog list", "cataloig list"]]
    assert find_typos(calls) == [("cataloig", "catalog", "positional #0")]
    print("self-check ok")


def main(argv: list[str]) -> int:
    if "--self-check" in argv:
        self_check()
        return 0
    path = Path(argv[1]) if len(argv) > 1 else Path(DEFAULT_HISTORY)
    calls, secrets = load(path)
    report(calls, secrets)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
