# Copyright (c) 2023-2024, Abilian SAS
from hop3.core.app import App
from hop3.proxies.nginx.setup import NginxConfig


def test_get_static_paths_0():
    env = {"NGINX_SERVER_NAME": "testapp.com"}
    workers = {}
    nginx = NginxConfig(App("testapp"), env, workers)
    assert nginx.get_static_paths() == []


def test_get_static_paths_1():
    env = {
        "NGINX_SERVER_NAME": "testapp.com",
        "NGINX_STATIC_PATHS": "/prefix1:path1",
    }
    workers = {}
    nginx = NginxConfig(App("testapp"), env, workers)
    result = nginx.get_static_paths()
    assert result[0][0] == "/prefix1"
    assert result[0][1].name == "path1"


def test_get_static_paths_2():
    env = {"NGINX_SERVER_NAME": "testapp.com"}
    workers = {"static": "public"}
    nginx = NginxConfig(App("testapp"), env, workers)
    result = nginx.get_static_paths()
    assert result[0][0] == "/"
    assert result[0][1].name == "public"


# def test_setup_no_workers():
#     env = {"NGINX_SERVER_NAME": "testapp.com"}
#     workers = {}
#     nginx = NginxConfig(App("testapp"), env, workers)
#     nginx.setup()
#
#
# def test_setup_with_workers():
#     env = {"NGINX_SERVER_NAME": "testapp.com"}
#     workers = {"static": "public"}
#     nginx = NginxConfig(App("testapp"), env, workers)
#     nginx.setup()
