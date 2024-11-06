# Copyright (c) 2023-2024, Abilian SAS

"""
For asynchronous command dispatching, we'll need a simple message broker interface.

We're using Python's queue for simplicity.


"""

import queue
import threading
from typing import Any

from hop3_lib.bus.bus import CommandBus


class MessageBroker:
    """The `MessageBroker` class has two queues: one for commands and one for events."""

    def __init__(self):
        self.command_queue = queue.Queue()
        self.event_queue = queue.Queue()

    def send_command(self, command: Any):
        self.command_queue.put(command)

    def receive_command(self):
        return self.command_queue.get()

    def send_event(self, event: Any):
        self.event_queue.put(event)

    def receive_event(self):
        return self.event_queue.get()


class AsynchronousCommandBus(CommandBus):
    """The `AsynchronousCommandBus` class extends the `CommandBus` class and uses the `MessageBroker` to send and receive commands."""

    def __init__(self, message_broker: MessageBroker):
        super().__init__()
        self.message_broker = message_broker

    def dispatch(self, command: Any):
        self.message_broker.send_command(command)

    def start_worker(self):
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        while True:
            command = self.message_broker.receive_command()
            super().dispatch(command)


class MultiMessageBroker:
    def __init__(self):
        self.queues = {}

    def add_queue(self, name: str):
        self.queues[name] = queue.Queue()

    def send_message(self, queue_name: str, message: Any):
        if queue_name in self.queues:
            self.queues[queue_name].put(message)
        else:
            raise ValueError(f"Queue {queue_name} does not exist")

    def receive_message(self, queue_name: str):
        if queue_name in self.queues:
            return self.queues[queue_name].get()
        else:
            raise ValueError(f"Queue {queue_name} does not exist")
