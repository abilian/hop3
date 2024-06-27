# Copyright (c) 2023-2024, Abilian SAS

from .setup import get_static_paths


def test_get_static_paths_0():
    env = {}
    workers = {}
    assert get_static_paths(env, workers) == ""


def test_get_static_paths_1():
    env = {"NGINX_STATIC_PATHS": "/prefix1:path1"}
    workers = {}
    assert get_static_paths(env, workers) == "/prefix1:path1"


def test_get_static_paths_2():
    env = {}
    workers = {"static": "public"}
    assert get_static_paths(env, workers) == "/:public/"
