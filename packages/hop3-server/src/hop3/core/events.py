# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from dataclasses import dataclass

from hop3.lib import log


class Event:
    """Base class for events."""


@dataclass(frozen=True)
class BuildEvent(Event):
    app_name: str
    msg: str = ""

    def __str__(self) -> str:
        return self.msg


@dataclass(frozen=True)
class CreatingVirtualEnv(BuildEvent):
    app_name: str

    def __str__(self) -> str:
        return f"Creating virtual environment for {self.app_name}"


@dataclass(frozen=True)
class InstallingVirtualEnv(Event):
    app_name: str

    def __str__(self) -> str:
        return f"Installing/updating virtual environment for {self.app_name}"


@dataclass(frozen=True)
class CreatingBuildEnv(Event):
    app_name: str

    def __str__(self) -> str:
        return f"Creating build environment for {self.app_name}"


@dataclass(frozen=True)
class CompilingProject(Event):
    app_name: str

    def __str__(self) -> str:
        return f"Compiling project {self.app_name}"


@dataclass(frozen=True)
class PreparingBuildEnv(Event):
    app_name: str

    def __str__(self) -> str:
        return f"Preparing build environment for {self.app_name}"


@dataclass(frozen=True)
class InstallingDependencies(Event):
    app_name: str

    def __str__(self) -> str:
        return f"Installing dependencies for {self.app_name}"


def emit(event: Event) -> None:
    """Emits the given event.

    Currently, this only logs the event to the console.
    """
    log(str(event), level=3, fg="blue")
