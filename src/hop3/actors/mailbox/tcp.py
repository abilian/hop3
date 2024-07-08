import socket

from eventlet.green import zmq
from msgpack import packb, unpackb

from .base import Mailbox, decode, encode


def get_hostname():
    return socket.getfqdn()


class TcpInbox(Mailbox):
    __slots__ = ["_port", "_url", "_context", "_recv_sock"]

    def __init__(self, port=9999, **kwargs):
        self._port = port
        self._url = "tcp://*:" + str(port)
        self._context = zmq.Context(**kwargs)
        self._recv_sock = self._context.socket(zmq.PULL)
        self._recv_sock.bind(self._url)

    def get(self):
        return decode(unpackb(self._recv_sock.recv(), use_list=False))

    def put(self, message):
        raise NotImplementedError()

    def encode(self):
        cls = self.__class__
        return [cls.__module__, cls.__name__, get_hostname(), self._port]

    @staticmethod
    def decode(params):
        address, port = params
        return TcpOutbox(address, port)

    def __enter__(self):
        return self

    def __exit__(self, *exc_details):
        self.__del__()

    def __del__(self):
        self._recv_sock.close()
        self._context.term()

    def __str__(self):
        return self._url

    def __eq__(self, other):
        return self.__class__ is other.__class__ and self._url == other._url

    def __hash__(self):
        return hash(self._url)


class TcpOutbox(Mailbox):
    __slots__ = ["_url", "_context", "_send_sock"]

    def __init__(self, address, port, **kwargs):
        self._url = "tcp://" + address + ":" + str(port)
        self._context = zmq.Context(**kwargs)
        self._send_sock = self._context.socket(zmq.PUSH)
        self._send_sock.connect(self._url)

    def get(self):
        raise NotImplementedError()

    def put(self, msg):
        self._send_sock.send(packb(encode(msg), use_bin_type=True))

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
        self._context.term()

    def __str__(self):
        return self._url

    def __eq__(self, other):
        return self.__class__ is other.__class__ and self._url == other._url

    def __hash__(self):
        return hash(self._url)
