# Copyright (c) 2023-2024, Abilian SAS

"""
A Python command and event bus.

### Key Components

1. **Command Bus**: Handles command dispatching and execution.
2. **Event Bus**: Manages event dispatching and listener execution.
3. **Command Handlers**: Specific functions that handle commands.
4. **Event Listeners**: Specific functions that handle events.
5. **Transactions**: Manage the atomic execution of commands and events.

"""

#### 1. Command Bus

from dataclasses import dataclass
from typing import Any, Callable, Dict, Type


class CommandBus:
    """The Command Bus is responsible for dispatching commands to their respective handlers.

    Commands are processed within a transaction.
    """

    def __init__(self):
        self.handlers: Dict[Type, Callable] = {}

    def register_handler(self, command_type: Type, handler: Callable):
        self.handlers[command_type] = handler

    def dispatch(self, command: Any):
        handler = self.handlers.get(type(command))
        if not handler:
            raise ValueError(f"No handler registered for {type(command)}")
        handler(command)


@dataclass
class Command:
    pass


@dataclass
class SayHelloCommand(Command):
    name: str


#### 2. Event Bus


class EventBus:
    """The Event Bus dispatches events to their listeners synchronously."""

    def __init__(self):
        self.listeners: Dict[Type, Callable] = {}

    def register_listener(self, event_type: Type, listener: Callable):
        self.listeners.setdefault(event_type, []).append(listener)

    def dispatch(self, event: Any):
        for listener in self.listeners.get(type(event), []):
            listener(event)


@dataclass
class Event:
    pass


@dataclass
class HelloWasSaidEvent(Event):
    name: str


#### 3. Command Handlers

# Command Handlers execute commands and can emit events.


class SayHelloHandler:
    """Example handler for the SayHelloCommand."""

    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus

    def handle(self, command: SayHelloCommand):
        print(f"Hello, {command.name}")
        self.event_bus.dispatch(HelloWasSaidEvent(command.name))


#### 4. Event Listeners

# Event Listeners react to events emitted by command handlers.


class SayHelloListener:
    """Example listener for the HelloWasSaidEvent."""

    def on_hello_was_said(self, event: HelloWasSaidEvent):
        print(f"Event received: Hello was said to {event.name}")


#### 5. Transactions and Event Buffer


class TransactionalCommandBus(CommandBus):
    """To ensure atomicity, we can implement a simple transaction management system."""

    def __init__(self, event_bus: EventBus):
        super().__init__()
        self.event_bus = event_bus
        self.event_buffer = []

    def dispatch(self, command: Any):
        try:
            super().dispatch(command)
            self.commit()
        except Exception as e:
            self.rollback()
            raise e

    def commit(self):
        for event in self.event_buffer:
            self.event_bus.dispatch(event)
        self.event_buffer = []

    def rollback(self):
        self.event_buffer = []


class TransactionalSayHelloHandler(SayHelloHandler):
    def handle(self, command: SayHelloCommand):
        print(f"Hello, {command.name}")
        self.event_buffer.append(HelloWasSaidEvent(command.name))
