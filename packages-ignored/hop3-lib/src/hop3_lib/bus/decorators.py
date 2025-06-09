# Copyright (c) 2023-2025, Abilian SAS
from __future__ import annotations

from hop3_lib.bus.bus import CommandBus, EventBus, HelloWasSaidEvent, SayHelloCommand


def command_handler(command_type: type):
    def decorator(func):
        func._is_command_handler = True
        func._command_type = command_type
        return func

    return decorator


def event_listener(event_type: type):
    def decorator(func):
        func._is_event_listener = True
        func._event_type = event_type
        return func

    return decorator


class CommandBusWithAttributes(CommandBus):
    def register(self, obj):
        for attr in dir(obj):
            method = getattr(obj, attr)
            if hasattr(method, "_is_command_handler"):
                self.register_handler(method._command_type, method)


class EventBusWithAttributes(EventBus):
    def register(self, obj):
        for attr in dir(obj):
            method = getattr(obj, attr)
            if hasattr(method, "_is_event_listener"):
                self.register_listener(method._event_type, method)


# Examples
class SayHelloHandler:
    @command_handler(SayHelloCommand)
    def handle(self, command: SayHelloCommand):
        print(f"Hello, {command.name}")
        self.event_bus.dispatch(HelloWasSaidEvent(command.name))


class SayHelloListener:
    @event_listener(HelloWasSaidEvent)
    def on_hello_was_said(self, event: HelloWasSaidEvent):
        print(f"Event received: Hello was said to {event.name}")
