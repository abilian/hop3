# Copyright (c) 2023-2024, Abilian SAS

from __future__ import annotations

from termcolor import colored

# TODO ?
# "light_grey": 37,
# "dark_grey": 90,
# "light_red": 91,
# "light_green": 92,
# "light_yellow": 93,
# "light_blue": 94,
# "light_magenta": 95,
# "light_cyan": 96,
# "white": 97,


# Color helpers
def black(text):
    return colored(text, "black")


def red(text):
    return colored(text, "red")


def green(text):
    return colored(text, "green")


def yellow(text):
    return colored(text, "yellow")


def blue(text):
    return colored(text, "blue")


def magenta(text):
    return colored(text, "magenta")


def cyan(text):
    return colored(text, "cyan")


# Variants
def bold(text):
    return colored(text, attrs=["bold"])


def dim(text):
    return colored(text, attrs=["dark"])


success = green
error = red
warning = yellow
info = blue
debug = dim
