import uuid
from abc import ABCMeta, abstractmethod
from collections.abc import Callable

import eventlet
from devtools import debug
from snoop import snoop

from .mailbox import AckableMailbox, LocalMailbox, Mailbox, Receiver
from .message import (
    Cancel,
    Down,
    Fork,
    ForkResponse,
    ForkWithMonitor,
    Kill,
    Monitor,
    Unmonitor,
)

_actor_map = {}

_actor_pool = eventlet.GreenPool(size=1000000)


class ActorBase(Receiver, metaclass=ABCMeta):
    @abstractmethod
    def encode(self):
        pass

    @staticmethod
    @abstractmethod
    def decode(params):
        pass


class Actor(ActorBase):
    __slots__ = ["_ack", "_inbox", "_outbox", "_callback", "_greenlet", "_observers"]

    mailbox: Mailbox
    _ack: bool
    _inbox: Mailbox
    _outbox: Mailbox
    _callback: Callable
    _greenlet: eventlet.greenthread.GreenThread | None
    _observers: dict

    def __init__(self, callback, mailbox=None):
        if mailbox is None:
            mailbox = LocalMailbox()
        assert isinstance(mailbox, Mailbox)
        self._ack = isinstance(mailbox, AckableMailbox)
        self._inbox = mailbox
        self._outbox = mailbox
        self._callback = callback
        self._greenlet = None
        self._observers = {}

    @snoop
    def run(self, *args, **kwargs):
        greenlet_id = id(eventlet.getcurrent())
        _actor_map[greenlet_id] = self
        try:
            self._callback(*args, **kwargs)
        finally:
            if greenlet_id in _actor_map.keys():
                del _actor_map[greenlet_id]

    def spawn(self, *args, **kwargs):
        self._greenlet = _actor_pool.spawn(self.run, *args, **kwargs)

    def _link(self, func, *args, **kwargs):
        if self._greenlet is None:
            return
        return self._greenlet.link(func, *args, **kwargs)

    def _unlink(self, func, *args, **kwargs):
        if self._greenlet is None:
            return
        return self._greenlet.unlink(func, *args, **kwargs)

    def _cancel(self, *throw_args):
        if self._greenlet is None:
            return
        return self._greenlet.cancel(*throw_args)

    def _kill(self, *throw_args):
        if self._greenlet is None:
            return
        return self._greenlet.kill(*throw_args)

    def wait(self):
        if self._greenlet is None:
            return
        return self._greenlet.wait()

    def send(self, message):
        if self._outbox is not None:
            debug(self._outbox, message)
            self._outbox.put(message)

    def receive(self):
        while True:
            self.receive_message()

    def receive_message(self):
        message = self._inbox.get()
        match message:
            case Monitor(sender):
                try:
                    self._observers[sender] = spawn(observe, self, sender)
                finally:
                    self.ack_last_msg()

            case Unmonitor(sender):
                try:
                    self._observers[sender]._kill()
                    del self._observers[sender]
                finally:
                    self.ack_last_msg()

            case Cancel():
                try:
                    self._cancel()
                finally:
                    self.ack_last_msg()

            case Kill():
                try:
                    self._kill()
                finally:
                    self.ack_last_msg()

            case Fork(sender, func, args, kwargs):
                try:
                    new_actor = spawn_with_mailbox(func, self._inbox, *args, **kwargs)
                    send(ForkResponse(new_actor), sender)
                    self._kill()
                finally:
                    self.ack_last_msg()

            case ForkWithMonitor(sender, func, args, kwargs):
                try:
                    new_actor = spawn_with_mailbox(func, self._inbox, *args, **kwargs)
                    self._observers[sender] = spawn(observe, new_actor, sender)
                    send(ForkResponse(new_actor), sender)
                    self._kill()
                finally:
                    self.ack_last_msg()

            case _:
                return message  # ???
        # return message

    def ack_last_msg(self):
        if isinstance(self._inbox, AckableMailbox):
            self._inbox.ack()

    def encode(self):
        return self._inbox.encode()

    @staticmethod
    def decode(params):
        raise NotImplementedError

    def __del__(self):
        del self._observers

    def __str__(self):
        return str(id(self._greenlet)) + "@" + str(self._inbox)

    def __eq__(self, other):
        return self.__class__ is other.__class__ and self._inbox == other._inbox

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash(str(self))


def observe(target, observer):
    try:
        exit_value = target.wait()
        send(Down(target, exit_value), observer)
    except Exception as e:
        send(
            Down(target, {"exception name:": e.__class__.__name__, "args": e.args}),
            observer,
        )


def make_ref():
    return uuid.uuid4()


default_mailbox = LocalMailbox()


def send(message, target=None):
    match target:
        case Actor():
            target.send(message)
        case Mailbox():
            target.put(message)
        case None:
            default_mailbox.put(message)
        case _:
            raise ValueError("Invalid target type")


def recv(target=None):
    match target:
        case Actor():
            return target.receive()
        case Mailbox():
            return target.get()
        case None:
            return default_mailbox.get()
        case _:
            raise ValueError("Invalid target type")


def ack_last_msg(target=None):
    if isinstance(target, Actor):
        target.ack_last_msg()
    elif isinstance(target, AckableMailbox):
        target.ack()


def ack():
    self().ack_last_msg()


def link(receiver: Receiver):
    send(Monitor(self()), receiver)


monitor = link


def unlink(receiver: Receiver):
    send(Unmonitor(self()), receiver)


unmonitor = unlink


def cancel(receiver: Receiver):
    send(Cancel(self()), receiver)


def kill(receiver: Receiver):
    send(Kill(self()), receiver)


def fork(receiver: Receiver, func, *args, **kwargs):
    current_actor = self()
    send(Fork(current_actor, func, args, kwargs), receiver)
    while True:
        message = recv(current_actor)
        match message:
            case ForkResponse(new_actor):
                return new_actor
            case _:
                send(message, current_actor)


def fork_with_monitor(receiver: Receiver, func, *args, **kwargs):
    current_actor = self()
    send(ForkWithMonitor(current_actor, func, args, kwargs), receiver)
    while True:
        message = recv(current_actor)
        match message:
            case ForkResponse(new_actor):
                return new_actor
            case _:
                send(message, current_actor)


def self():
    cur_green = eventlet.getcurrent()
    return _actor_map.get(id(cur_green))


def spawn(func, *args, **kwargs):
    actor = Actor(func)
    actor.spawn(*args, **kwargs)
    return actor


def spawn_with_mailbox(func, mailbox, *args, **kwargs):
    actor = Actor(func, mailbox)
    actor.spawn(*args, **kwargs)
    return actor


def sleep(seconds):
    eventlet.sleep(seconds)


def wait_all():
    _actor_pool.waitall()


def wait(actor):
    return actor.wait()
