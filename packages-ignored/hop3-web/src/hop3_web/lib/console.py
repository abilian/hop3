# Copyright (c) 2023-2025, Abilian SAS

from __future__ import annotations

from termcolor import colored


class Panic(Exception):
    def __init__(self, msg):
        self.msg = msg
        super().__init__(self.msg)
        print(red(self.msg))


def panic(msg):
    """Prints a message and exits the program."""
    print(red(msg))
    raise SystemExit(1)


# Color helpers
def blue(text):
    return colored(text, "blue")


def green(text):
    return colored(text, "green")


def red(text):
    return colored(text, "red")


def yellow(text):
    return colored(text, "yellow")


def bold(text):
    return colored(text, attrs=["bold"])


def dim(text):
    return colored(text, attrs=["dark"])
