# Copyright (c) 2025-2026, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

"""Nix string escaping helpers.

Inside Nix multi-line strings (``'' ... ''``), ``${VAR}`` is interpolated
by Nix. To prevent this and pass the literal text through to the shell,
we escape ``${`` as ``''${``. Bare ``$VAR``, ``$(cmd)``, and ``$PWD`` are
not interpolation in Nix — they pass through literally.
"""

from __future__ import annotations


def nix_escape(s: str) -> str:
    r"""Escape a string for embedding in a Nix ``'' ... ''`` multi-line string.

    Inside such a string Nix gives exactly two sequences meaning: ``''`` (which
    starts an escape, or ends the string) and ``${`` (interpolation). Everything
    else — bare ``$VAR``, ``$(cmd)``, ``$PWD`` — passes through untouched.

    So three things must be rewritten:

    * ``${``  ->  ``''${``   (emit a literal ``${`` for the shell to expand)
    * ``''``  ->  ``'''``    (emit a literal ``''`` — e.g. PHP's empty string)
    * a lone ``'`` that would touch a neighbouring ``''``  ->  ``''\'``

    The last rule is not academic. A lone quote is only safe if nothing starting
    with ``''`` follows it, and two things can: the ``''${`` we are about to emit,
    and the string's own closing ``''`` delimiter. So ``'${MYSQL_HOST}'`` — an
    ordinary single-quoted PHP/shell string — used to escape to ``'''${...}``,
    which Nix lexes as the literal-``''`` escape followed by a *real*
    interpolation ("undefined variable 'MYSQL_HOST'"); and a trailing quote used
    to swallow the closing delimiter. Likewise an unescaped ``''``
    (``const GOOGLE_CLIENT_ID = '';``) simply terminates the string. All of these
    emitted un-parseable Nix with no warning at generation time.

    >>> nix_escape("port: ${PORT}")
    "port: ''${PORT}"
    >>> nix_escape("$(date)")
    '$(date)'
    >>> nix_escape("$PWD")
    '$PWD'
    >>> nix_escape("const X = '';")            # PHP empty string
    "const X = ''';"
    >>> nix_escape("const H = '${MYSQL_HOST}';")  # quote adjacent to ${
    "const H = ''\\'''${MYSQL_HOST}';"
    >>> nix_escape("echo '${A}'")              # trailing quote vs closing ''
    "echo ''\\'''${A}''\\'"
    """
    out: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        if s.startswith("${", i):
            out.append("''${")
            i += 2
        elif s.startswith("''", i):
            # A literal pair of quotes; `'''` is Nix's escape for it.
            out.append("'''")
            i += 2
        elif s[i] == "'" and (s.startswith("${", i + 1) or i == n - 1):
            # A lone quote that would touch the `''${` we are about to emit, or
            # (at the very end) the closing `''` of the enclosing Nix string.
            out.append("''\\'")
            i += 1
        else:
            out.append(s[i])
            i += 1
    return "".join(out)
