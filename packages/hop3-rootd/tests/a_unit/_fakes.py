# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
Shared test doubles for hop3-rootd unit tests.

``FakeExec`` is a recording ``hop3_rootd.exec.Exec``: every ``run`` argv is
stored in ``.calls`` and routed to a canned ``CommandResult`` by the first
matching predicate (default: success with empty output). Tests inject it via
``OpContext.exec`` (or the ``exec=`` kwarg on the domain functions) and assert
on final state plus the recorded call set, instead of monkeypatching module
globals and pinning a fragile ``side_effect`` call order.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3_rootd.exec import CommandResult

if TYPE_CHECKING:
    from collections.abc import Callable


class SaveSpy:
    """
    Callable that counts how many times it was invoked.

    Stands in for ``OpContext.save_state`` (a ``Callable[[], None]``) so a test
    can assert the op persisted state, without monkeypatching a private attr
    onto ``OpContext``. Use via a pair of fixtures::

        @pytest.fixture
        def save_spy() -> SaveSpy:
            return SaveSpy()

        @pytest.fixture
        def ctx(save_spy: SaveSpy) -> OpContext:
            return OpContext(..., save_state=save_spy)

        def test_op_persisted(ctx, save_spy):
            ...
            assert save_spy.count == 1
    """

    def __init__(self) -> None:
        self.count = 0

    def __call__(self) -> None:
        self.count += 1


def ok(stdout: str = "") -> CommandResult:
    """A successful CommandResult (rc 0)."""
    return CommandResult(argv=[], returncode=0, stdout=stdout, stderr="")


def fail(stderr: str, *, returncode: int = 1) -> CommandResult:
    """A failed CommandResult (rc 1 by default)."""
    return CommandResult(argv=[], returncode=returncode, stdout="", stderr=stderr)


class FakeExec:
    """
    Recording test double for ``hop3_rootd.exec.Exec``.

    Each ``run(argv)`` is appended to ``.calls`` and routed to the first
    registered predicate whose ``predicate(argv)`` is truthy; unmatched calls
    return ``ok()``. ``resolve`` returns a stable fake path
    (``/usr/sbin/<name>``) so argv construction works without the real binary
    on PATH — override per name with :meth:`set_path` (pass ``None`` to
    simulate "binary not on host").
    """

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self._routes: list[tuple[Callable[[list[str]], bool], CommandResult]] = []
        self._paths: dict[str, str | None] = {}

    def resolve(self, name: str) -> str | None:
        if name not in self._paths:
            self._paths[name] = f"/usr/sbin/{name}"
        return self._paths[name]

    def set_path(self, name: str, path: str | None) -> None:
        """Pin the resolved path for a binary (``None`` = not on host)."""
        self._paths[name] = path

    def run(self, argv: list[str], **_kwargs: object) -> CommandResult:
        argv = list(argv)
        self.calls.append(argv)
        for predicate, result in self._routes:
            if predicate(argv):
                return result
        return ok()

    def on(
        self, predicate: Callable[[list[str]], bool], result: CommandResult
    ) -> FakeExec:
        """Route argv matching ``predicate`` → ``result``. First match wins."""
        self._routes.append((predicate, result))
        return self

    def calls_with(self, token: str) -> list[list[str]]:
        """Recorded argvs containing ``token``."""
        return [c for c in self.calls if token in c]
