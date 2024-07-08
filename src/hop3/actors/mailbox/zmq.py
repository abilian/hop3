from eventlet.green import zmq
from msgpack import packb, unpackb
from zmq import PULL, PUSH

from .base import Mailbox, decode, encode


class ZmqInbox(Mailbox):
    __slots__ = ["_url", "_context", "_recv_sock"]

    def __init__(self, url="tcp://*:9999", **kwargs):
        self._url = url
        self._context = zmq.Context(**kwargs)
        self._recv_sock = self._context.socket(PULL)
        self._recv_sock.bind(url)

    def get(self):
        return decode(unpackb(self._recv_sock.recv(), use_list=False))

    def put(self, message):
        raise NotImplementedError

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
        self._recv_sock.close()

    def __str__(self):
        return self._url

    def __eq__(self, other):
        return self.__class__ is other.__class__ and self._url == other._url

    def __hash__(self):
        return hash(self._url)


class ZmqOutbox(Mailbox):
    __slots__ = ["_url", "_context", "_send_sock"]

    def __init__(self, url, **kwargs):
        self._url = url
        self._context = zmq.Context(**kwargs)
        self._send_sock = self._context.socket(PUSH)
        self._send_sock.connect(self._url)

    def get(self):
        raise NotImplementedError()

    def put(self, message):
        self._send_sock.send(packb(encode(message), use_bin_type=True))

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
        self._send_sock.close()

    def __str__(self):
        return self._url

    def __eq__(self, other):
        return self.__class__ is other.__class__ and self._url == other._url

    def __hash__(self):
        return hash(self._url)
