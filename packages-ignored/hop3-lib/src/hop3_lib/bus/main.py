# Copyright (c) 2023-2025, Abilian SAS
from __future__ import annotations

from hop3_lib.bus.bus import (
    EventBus,
    HelloWasSaidEvent,
    SayHelloCommand,
    SayHelloListener,
    TransactionalCommandBus,
)
from hop3_lib.bus.transactions import TransactionalSayHelloHandler


def main():
    event_bus = EventBus()
    command_bus = TransactionalCommandBus(event_bus)

    # Register handlers and listeners
    command_bus.register_handler(
        SayHelloCommand, TransactionalSayHelloHandler(event_bus).handle
    )
    event_bus.register_listener(HelloWasSaidEvent, SayHelloListener().on_hello_was_said)

    # Dispatch a command
    command_bus.dispatch(SayHelloCommand(name="Alice"))


if __name__ == "__main__":
    main()
