from msgpack import packb, unpackb

from .base import AckableMailbox, decode, encode


class KombuMailbox(AckableMailbox):
    __slots__ = ["_address", "_conn", "_queue", "_no_ack", "_last_msg"]

    def __init__(
        self,
        address,
        name,
        transport_options,
        ssl=False,
        no_ack=True,
        queue_opts=None,
        exchange_opts=None,
    ):
        from kombu import Connection

        self._address = address
        self._conn = Connection(address, transport_options=transport_options, ssl=ssl)
        self._queue = self._conn.SimpleQueue(name, no_ack, queue_opts, exchange_opts)
        self._no_ack = no_ack
        self._last_msg = None

    def get(self):
        self._last_msg = self._queue.get()
        return decode(unpackb(self._last_msg.body, use_list=False))

    def put(self, message):
        return self._queue.put(packb(encode(message), use_bin_type=True))

    def ack(self):
        if self._no_ack:
            return
        if self._last_msg is not None:
            self._last_msg.ack()
            self._last_msg = None

    def encode(self):
        raise NotImplementedError

    @staticmethod
    def decode(params):
        raise NotImplementedError

    def __enter__(self):
        return self

    def __exit__(self, *exc_details):
        self.__del__()

    def __del__(self):
        if hasattr(self, "_queue"):
            self._queue.close()
        if hasattr(self, "_conn"):
            self._conn.close()

    def __str__(self):
        return self._address

    def __eq__(self, other):
        return self.__class__ is other.__class__ and self._address == other._address
