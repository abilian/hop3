from dataclasses import dataclass


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
    func: str
    args: tuple
    kwargs: dict


@dataclass(frozen=True)
class ForkWithMonitor:
    sender: str
    func: str
    args: tuple
    kwargs: dict


@dataclass(frozen=True)
class ForkResponse:
    new_actor: str


@dataclass(frozen=True)
class Down:
    sender: str
    reason: str
