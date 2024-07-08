import sys
import types
from abc import ABCMeta, abstractmethod
from collections.abc import Mapping
from typing import Any

import cloudpickle
from eventlet.queue import LightQueue
from msgpack import ExtType, packb, unpackb
from pyrsistent import PBag, PList, PVector, pbag, plist, pmap, pset, pvector

TYPE_PSET = 1
TYPE_PLIST = 2
TYPE_PBAG = 3
TYPE_MBOX = 4
TYPE_FUNC = 5


def decode(obj):
    match obj:
        case ExtType():
            # ExtType represents ext type in msgpack.
            if obj.code == TYPE_PSET:
                unpacked_data = unpackb(obj.data, use_list=False)
                return pset(decode(item) for item in unpacked_data)
            if obj.code == TYPE_PLIST:
                unpacked_data = unpackb(obj.data, use_list=False)
                return plist(decode(item) for item in unpacked_data)
            if obj.code == TYPE_PBAG:
                unpacked_data = unpackb(obj.data, use_list=False)
                return pbag(decode(item) for item in unpacked_data)
            if obj.code == TYPE_FUNC:
                return decode_func(obj.data)

            module_name, class_name, *data = unpackb(obj.data, use_list=False)
            cls = getattr(sys.modules[module_name], class_name)
            if obj.code == TYPE_MBOX:
                return cls.decode(data)

            return cls(*(decode(item) for item in data))

        case tuple():
            return pvector(decode(item) for item in obj)

        case dict():
            new_dict = dict()
            for key in obj.keys():
                new_dict[decode(key)] = decode(obj[key])
            return pmap(new_dict)

        case _:
            return obj


def encode(obj):
    match obj:
        case int() | float() | str() | bool() | None:
            return obj

        case list() | tuple() | PVector():
            return [encode(item) for item in obj]

        case Mapping():
            encoded_obj = {}
            for key in obj.keys():
                encoded_obj[encode(key)] = encode(obj[key])
            return encoded_obj

        case set():
            return ExtType(
                TYPE_PSET, packb([encode(item) for item in obj], use_bin_type=True)
            )

        case PList():
            return ExtType(
                TYPE_PLIST, packb([encode(item) for item in obj], use_bin_type=True)
            )

        case PBag():
            return ExtType(
                TYPE_PBAG, packb([encode(item) for item in obj], use_bin_type=True)
            )

        case types.FunctionType():
            return ExtType(TYPE_FUNC, encode_func(obj))

        case Receiver():
            return ExtType(TYPE_MBOX, packb(obj.encode(), use_bin_type=True))

        case _:
            # assume record
            cls = obj.__class__
            return ExtType(
                0,
                packb(
                    [cls.__module__, cls.__name__] + [encode(item) for item in obj],
                    use_bin_type=True,
                ),
            )


def decode_func(obj):
    return cloudpickle.loads(obj)


def encode_func(obj):
    return cloudpickle.dumps(obj)


class Receiver(metaclass=ABCMeta):
    @abstractmethod
    def encode(self):
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    def decode(params):
        raise NotImplementedError


class Mailbox(Receiver, metaclass=ABCMeta):
    @abstractmethod
    def put(self, message):
        raise NotImplementedError

    @abstractmethod
    def get(self) -> Any:
        raise NotImplementedError

    def __ne__(self, other):
        return not self.__eq__(other)


class AckableMailbox(Mailbox, metaclass=ABCMeta):
    @abstractmethod
    def ack(self):
        raise NotImplementedError


Mailbox.register(LightQueue)
