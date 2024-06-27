# Copyright (c) 2023-2024, Abilian SAS
from hop3.proxies.nginx.setup import NginxConfig


def test_get_static_paths_0():
    env = {}
    workers = {}
    nginx = NginxConfig("testapp", env, workers)
    assert nginx.get_static_paths() == []


def test_get_static_paths_1():
    env = {"NGINX_STATIC_PATHS": "/prefix1:path1"}
    workers = {}
    nginx = NginxConfig("testapp", env, workers)
    result = nginx.get_static_paths()
    assert result[0][0] == "/prefix1"
    assert result[0][1].name == "path1"


def test_get_static_paths_2():
    env = {}
    workers = {"static": "public"}
    nginx = NginxConfig("testapp", env, workers)
    result = nginx.get_static_paths()
    assert result[0][0] == "/"
    assert result[0][1].name == "public"
