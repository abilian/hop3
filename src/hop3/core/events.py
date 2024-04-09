from dataclasses import dataclass

from hop3.util import log


class Event:
    pass


@dataclass(frozen=True)
class BuildEvent(Event):
    app_name: str
    msg: str = ""

    def __str__(self):
        return self.msg


@dataclass(frozen=True)
class CreatingVirtualEnv(BuildEvent):
    app_name: str

    def __str__(self):
        return f"Creating virtual environment for {self.app_name}"


@dataclass(frozen=True)
class InstallingVirtualEnv(Event):
    app_name: str

    def __str__(self):
        return f"Installing/updateing virtual environment for {self.app_name}"


@dataclass(frozen=True)
class CreatingBuildEnv(Event):
    app_name: str

    def __str__(self):
        return f"Creating build environment for {self.app_name}"


@dataclass(frozen=True)
class CompilingProject(Event):
    app_name: str

    def __str__(self):
        return f"Compiling project {self.app_name}"


@dataclass(frozen=True)
class PreparingBuildEnv(Event):
    app_name: str

    def __str__(self):
        return f"Preparing build environment for {self.app_name}"


@dataclass(frozen=True)
class InstallingDependencies(Event):
    app_name: str

    def __str__(self):
        return f"Installing dependencies for {self.app_name}"


def emit(event: Event):
    log(str(event), level=5, fg="blue")
