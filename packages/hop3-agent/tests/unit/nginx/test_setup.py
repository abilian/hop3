# Copyright (c) 2023-2024, Abilian SAS
from __future__ import annotations

import pytest
from hop3.core.app import App
from hop3.core.env import Env
from hop3.proxies.nginx.setup import NginxConfig


def test_get_static_paths_0() -> None:
    env = {"NGINX_SERVER_NAME": "testapp.com"}
    workers = {}
    nginx = NginxConfig(App("testapp"), env, workers)
    assert nginx.get_static_paths() == []


def test_get_static_paths_1() -> None:
    env = {
        "NGINX_SERVER_NAME": "testapp.com",
        "NGINX_STATIC_PATHS": "/prefix1:path1",
    }
    workers = {}
    nginx = NginxConfig(App("testapp"), env, workers)
    result = nginx.get_static_paths()
    assert result[0][0] == "/prefix1"
    assert result[0][1].name == "path1"


def test_get_static_paths_2() -> None:
    env = {"NGINX_SERVER_NAME": "testapp.com"}
    workers = {"static": "public"}
    nginx = NginxConfig(App("testapp"), env, workers)
    result = nginx.get_static_paths()
    assert result[0][0] == "/"
    assert result[0][1].name == "public"


# Copied from hop3-agent/src/hop3/proxies/nginx/setup.py
SAFE_DEFAULTS = {
    "NGINX_IPV4_ADDRESS": "0.0.0.0",
    "NGINX_IPV6_ADDRESS": "[::]",
    "BIND_ADDRESS": "127.0.0.1",
}


@pytest.fixture
def env() -> Env:
    env = Env()
    env.update({
        "PORT": "8000",
        "NGINX_SERVER_NAME": "testapp.com",
    })
    env.update(SAFE_DEFAULTS)
    return env


def test_setup_no_workers(env: Env) -> None:
    workers = {}
    nginx = NginxConfig(App("testapp"), env, workers)
    nginx.setup()


def test_setup_with_workers(env: Env) -> None:
    workers = {"static": "public"}
    nginx = NginxConfig(App("testapp"), env, workers)
    nginx.setup()