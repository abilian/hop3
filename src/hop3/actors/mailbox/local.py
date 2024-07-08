from eventlet.queue import LightQueue

from .base import Mailbox


class LocalMailbox(Mailbox):
    __slots__ = ["_queue"]

    _queue: LightQueue

    def __init__(self):
        self._queue = LightQueue()

    def put(self, message):
        self._queue.put(message)

    def get(self):
        return self._queue.get()

    def encode(self):
        raise NotImplementedError

    @staticmethod
    def decode(params):
        raise NotImplementedError
