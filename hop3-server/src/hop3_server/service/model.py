from dataclasses import dataclass


@dataclass(frozen=True)
class App:
    name: str
    is_running: bool = False
