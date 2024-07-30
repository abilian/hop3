# Copyright (c) 2023-2024, Abilian SAS

from hop3_lib.bus.bus import (
    CommandBus,
    EventBus,
    HelloWasSaidEvent,
    SayHelloCommand,
    SayHelloHandler,
)


class TransactionalCommandBus(CommandBus):
    def __init__(self, event_bus: EventBus):
        super().__init__()
        self.event_bus = event_bus
        self.event_buffer = []

    def dispatch(self, command: Any):
        self.event_buffer.clear()
        try:
            super().dispatch(command)
            self.commit()
        except Exception as e:
            self.rollback()
            raise e

    def commit(self):
        for event in self.event_buffer:
            self.event_bus.dispatch(event)
        self.event_buffer.clear()

    def rollback(self):
        self.event_buffer.clear()


# Example
class TransactionalSayHelloHandler(SayHelloHandler):
    def __init__(self, event_bus: EventBus, event_buffer: list):
        super().__init__(event_bus)
        self.event_buffer = event_buffer

    def handle(self, command: SayHelloCommand):
        print(f"Hello, {command.name}")
        self.event_buffer.append(HelloWasSaidEvent(command.name))
