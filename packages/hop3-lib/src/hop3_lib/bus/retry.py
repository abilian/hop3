# Copyright (c) 2023-2024, Abilian SAS

from typing import Any

from hop3_lib.bus.broker import AsynchronousCommandBus, MessageBroker

# class RetryStrategy:
#     def __init__(self, retries: int = 3):
#         self.retries = retries
#
#     def execute(self, func, *args, **kwargs):
#         attempt = 0
#         while attempt < self.retries:
#             try:
#                 return func(*args, **kwargs)
#             except Exception as e:
#                 attempt += 1
#                 if attempt >= self.retries:
#                     raise e


class RetryStrategy:
    def __init__(self, retries: int = 3, exceptions: tuple = (Exception,)):
        self.retries = retries
        self.exceptions = exceptions

    def execute(self, func, *args, **kwargs):
        attempt = 0
        while attempt < self.retries:
            try:
                return func(*args, **kwargs)
            except self.exceptions as e:
                attempt += 1
                if attempt >= self.retries:
                    raise e


class ConfigurableRetryStrategy:
    def __init__(self, retry_map: dict):
        self.retry_map = retry_map

    def execute(self, func, *args, **kwargs):
        attempt = 0
        while True:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                exception_type = type(e)
                if exception_type in self.retry_map:
                    retries = self.retry_map[exception_type]
                    if attempt < retries:
                        attempt += 1
                        continue
                raise e


class RetryChain:
    def __init__(self):
        self.strategies = []

    def add_strategy(self, strategy: RetryStrategy):
        self.strategies.append(strategy)

    def execute(self, func, *args, **kwargs):
        for strategy in self.strategies:
            try:
                return strategy.execute(func, *args, **kwargs)
            except Exception as e:
                continue
        raise Exception("All retry strategies failed")


class DeadLetterQueue:
    def __init__(self):
        self.queue = []

    def add(self, message: Any):
        self.queue.append(message)

    def get_all(self):
        return self.queue


class AsynchronousCommandBusWithRetry(AsynchronousCommandBus):
    def __init__(
        self,
        message_broker: MessageBroker,
        retry_strategy: RetryStrategy,
        dead_letter_queue: DeadLetterQueue,
    ):
        super().__init__(message_broker)
        self.retry_strategy = retry_strategy
        self.dead_letter_queue = dead_letter_queue

    def dispatch(self, command: Any):
        try:
            self.retry_strategy.execute(super().dispatch, command)
        except Exception as e:
            self.dead_letter_queue.add(command)
