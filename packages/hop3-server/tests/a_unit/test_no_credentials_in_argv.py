# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Threat-model invariant 2: no credential reaches a subprocess through argv.

A secret on a spawned process's command line is readable by any local user
through `ps` and `/proc/<pid>/cmdline` for as long as the process runs, so
every subprocess that needs one takes it from the environment or stdin
(`MYSQL_PWD`, `PGPASSWORD`, `REDISCLI_AUTH`, `--password-stdin`).

The threat model recorded this as holding by inspection with nothing enforcing
it, and named the failure mode: it drifts sister-site, one call site fixed and
its twin in another package left alone. The May 2026 round found exactly that
-- `MYSQL_PWD` applied in the server's mysql plugin and missed in the
installer's connection-verify helper. This test is the enforcement the model
asked for; it scans every package, so a fix in one no longer leaves its twin
undetected.
"""

from __future__ import annotations

import re
from pathlib import Path

# Argv shapes that put a secret on a command line. Each targets the
# interpolation, not the flag: a literal `-p` is fine, `-p{password}` is not.
ANTI_PATTERNS = {
    "mysql -p<secret> on argv (use MYSQL_PWD)": re.compile(r'["\']-p\{|f["\']-p\{'),
    "--password=<secret> on argv (use env or stdin)": re.compile(
        r'--password=\{|--password=["\']?\s*\+|--password=%s'
    ),
    "redis-cli -a <secret> on argv (use REDISCLI_AUTH)": re.compile(
        r'["\']-a["\']\s*,\s*\w*(?:password|passwd|secret)'
    ),
    "--token=<secret> on argv": re.compile(r"--token=\{"),
}

# This file quotes every pattern it looks for, so it matches itself.
SELF = Path(__file__).resolve()


def _source_files() -> list[Path]:
    root = SELF.parents[4]
    files = sorted(root.glob("packages/*/src/**/*.py"))
    assert files, f"no package sources found under {root}; check the path math"
    return files


def test_no_credential_reaches_a_subprocess_via_argv() -> None:
    """Every package, every anti-pattern, one sweep."""
    offenders: list[str] = []
    for path in _source_files():
        if path.resolve() == SELF:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for label, pattern in ANTI_PATTERNS.items():
            for match in pattern.finditer(text):
                line = text[: match.start()].count("\n") + 1
                offenders.append(f"{path}:{line}: {label}")

    assert not offenders, "Credential on a subprocess command line:\n" + "\n".join(
        offenders
    )


def test_the_scan_would_catch_a_regression() -> None:
    """A scan that matches nothing is indistinguishable from a passing one."""
    planted = 'cmd = ["mysqldump", f"-p{password}", db]'
    assert any(p.search(planted) for p in ANTI_PATTERNS.values())
