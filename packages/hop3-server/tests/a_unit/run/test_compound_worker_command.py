# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
A worker command must be one program, and the platform has to say so.

Every worker is wrapped as ``sh -c "cd … ; exec <command>"``. `exec` applies
to the first word, so in ``a && b`` the shell is replaced by ``a`` and ``b``
never runs — the app comes up running half of what it was told to run, or not
at all, and nothing reports it.

This is not hypothetical. The php-fpm runtime shipped with
``sed … > … && exec php-fpm …`` as its web worker and never started a pool on
any app; the docstring on the wrapper asserted that ``&&`` chains were fine.
"""

from __future__ import annotations

import pytest

from hop3.lib import Abort
from hop3.run.uwsgi.worker import _refuse_compound_command


def _refuse(command: str) -> str:
    with pytest.raises(Abort) as excinfo:
        _refuse_compound_command(command, "myapp", "web")
    return str(excinfo.value)


class TestACompoundCommandIsRefused:
    @pytest.mark.parametrize(
        "command",
        [
            "bash scripts/setup.sh && node index.js",
            "php artisan migrate; php -S 0.0.0.0:$PORT",
            "./configure || exit 1",
            "generate-config | tee conf && serve",
            "sed 's/__PORT__/'\"$PORT\"'/' in > out && exec php-fpm",
        ],
    )
    def test_each_chaining_form_is_named(self, command) -> None:
        message = _refuse(command)
        assert "single program" in message

    def test_the_message_says_where_the_setup_half_belongs(self) -> None:
        """A refusal that does not name the alternative just blocks the user."""
        message = _refuse("bash setup.sh && node index.js")
        assert "before-run" in message

    def test_the_offending_command_is_quoted_back(self) -> None:
        assert "bash setup.sh" in _refuse("bash setup.sh && node index.js")


class TestAnOrdinaryCommandIsLeftAlone:
    @pytest.mark.parametrize(
        "command",
        [
            "gunicorn app:application -b 0.0.0.0:$PORT",
            "node index.js",
            "/usr/sbin/php-fpm8.3 --nodaemonize --fpm-config /home/hop3/x.conf",
            "python -m http.server $PORT",
            # xwiki's shape: one program whose *argument* happens to be a
            # script. The `&&` is inside the quoted argument, not between two
            # programs, so `exec` lands on bash and bash runs the whole thing.
            "bash -c 'export JETTY_PORT=$PORT && ./start_xwiki.sh'",
            # A flag that merely looks like an operator.
            "myserver --filter 'a|b' --port $PORT",
        ],
    )
    def test_it_is_not_refused(self, command) -> None:
        _refuse_compound_command(command, "myapp", "web")  # does not raise


class TestWhatCannotBeParsed:
    def test_an_unbalanced_quote_is_not_guessed_at(self) -> None:
        """
        We block on proof, not suspicion: an unparseable command is not
        evidence of chaining, and the shell reports its own parse error.
        """
        _refuse_compound_command("echo 'unterminated", "myapp", "web")
