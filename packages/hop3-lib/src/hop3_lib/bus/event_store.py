# Copyright (c) 2023-2024, Abilian SAS

from typing import Any

from hop3_lib.bus.bus import Event, EventBus


class EventStore:
    def __init__(self):
        self.store = []

    def save(self, event: Event):
        self.store.append(event)


class EventBusWithStore(EventBus):
    def __init__(self, event_store: EventStore):
        super().__init__()
        self.event_store = event_store

    def dispatch(self, event: Any):
        self.event_store.save(event)
        super().dispatch(event)
