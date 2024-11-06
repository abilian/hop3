# Copyright (c) 2023-2024, Abilian SAS
from unittest import skip

from hop3_lib.bus.bus import (
    EventBus,
    HelloWasSaidEvent,
    SayHelloCommand,
    TransactionalCommandBus,
    TransactionalSayHelloHandler,
)


@skip
def test_say_hello_command():
    event_bus = EventBus()
    command_bus = TransactionalCommandBus(event_bus)
    command_bus.register_handler(
        SayHelloCommand,
        TransactionalSayHelloHandler(event_bus, command_bus.event_buffer).handle,
    )

    event_triggered = False

    def listener(event):
        nonlocal event_triggered
        event_triggered = True
        assert event.name == "Alice"

    event_bus.register_listener(HelloWasSaidEvent, listener)
    command_bus.dispatch(SayHelloCommand(name="Alice"))

    assert event_triggered
