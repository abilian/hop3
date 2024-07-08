from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from actors.actor import Actor


@dataclass(frozen=True)
class Monitor:
    sender: str


@dataclass(frozen=True)
class Unmonitor:
    sender: str


@dataclass(frozen=True)
class Cancel:
    sender: str


@dataclass(frozen=True)
class Kill:
    sender: str


@dataclass(frozen=True)
class Fork:
    sender: str
    func: Callable
    args: tuple
    kwargs: dict


@dataclass(frozen=True)
class ForkWithMonitor:
    sender: str
    func: Callable
    args: tuple
    kwargs: dict


@dataclass(frozen=True)
class ForkResponse:
    new_actor: Actor


@dataclass(frozen=True)
class Down:
    sender: str
    reason: Any
