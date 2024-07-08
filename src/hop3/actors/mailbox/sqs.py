# from msgpack import packb, unpackb
#
# from .base import AckableMailbox, decode, encode
#
#
# class SQSMailbox(AckableMailbox):
#     __slots__ = ["_name", "_queue", "_last_msg", "_last_msgs", "_no_ack"]
#
#     def __init__(self, name, no_ack=True):
#         import boto3
#
#         sqs = boto3.resource("sqs")
#         self._name = name
#         self._queue = sqs.get_queue_by_name(QueueName=name)
#         self._last_msg = None
#         self._last_msgs = None
#         self._no_ack = no_ack
#
#     def get(self, **kwargs):
#         while self._last_msgs is None or len(self._last_msgs) == 0:
#             self._last_msgs = self._queue.receive_messages(**kwargs)
#         self._last_msg = self._last_msgs.pop(0)
#         if self._no_ack:
#             self._last_msg.delete()
#         return decode(
#             unpackb(
#                 base64.decodebytes(bytes(self._last_msg.body, "utf-8")),
#                 encoding="utf-8",
#                 use_list=False,
#             )
#         )
#
#     def put(self, message, **kwargs):
#         return self._queue.send_message(
#             MessageBody=str(
#                 base64.encodebytes(packb(encode(message), use_bin_type=True)),
#                 "utf-8",
#             ),
#             **kwargs
#         )
#
#     def ack(self):
#         if self._no_ack:
#             return
#         if self._last_msg is not None:
#             self._last_msg.delete()
#             self._last_msg = None
#
#     def encode(self):
#         cls = self.__class__
#         return [cls.__module__, cls.__name__, self._name, self._no_ack]
#
#     @staticmethod
#     def decode(params):
#         name, no_ack = params
#         return SQSMailbox(name, no_ack=no_ack)
#
#     def __enter__(self):
#         return self
#
#     def __exit__(self, *exc_details):
#         self.__del__()
#
#     def __del__(self):
#         pass
#
#     def __str__(self):
#         return str(self._queue.url)
#
#     def __eq__(self, other):
#         return self.__class__ is other.__class__ and self._queue.url == other._queue.url
#
#     def __hash__(self):
#         return hash(self._queue.url)
