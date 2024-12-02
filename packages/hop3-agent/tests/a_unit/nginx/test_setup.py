# Copyright (c) 2023-2024, Abilian SAS
from __future__ import annotations

from pathlib import Path

import pytest
from hop3.config import config
from hop3.core.app import App
from hop3.core.env import Env
from hop3.plugins.nginx import Nginx


@pytest.fixture(autouse=True)
def created_directory():
    Path("/tmp/hop3/nginx/").mkdir(exist_ok=True, parents=True)


def test_get_static_paths_0() -> None:
    env = Env({"NGINX_SERVER_NAME": "testapp.com"})
    workers: dict[str, str] = {}
    nginx = Nginx(App("testapp"), env, workers)
    assert nginx.get_static_paths() == []


def test_get_static_paths_1() -> None:
    env = Env({
        "NGINX_SERVER_NAME": "testapp.com",
        "NGINX_STATIC_PATHS": "/prefix1:path1",
    })
    workers: dict[str, str] = {}
    nginx = Nginx(App("testapp"), env, workers)
    result = nginx.get_static_paths()
    assert result[0][0] == "/prefix1"
    assert result[0][1].name == "path1"


def test_get_static_paths_2() -> None:
    env = Env({"NGINX_SERVER_NAME": "testapp.com"})
    workers: dict[str, str] = {"static": "public"}
    nginx = Nginx(App("testapp"), env, workers)
    result = nginx.get_static_paths()
    assert result[0][0] == "/"
    assert result[0][1].name == "public"


# Copied from hop3-agent/src/hop3/proxies/nginx/setup.py
SAFE_DEFAULTS = Env({
    "NGINX_IPV4_ADDRESS": "0.0.0.0",
    "NGINX_IPV6_ADDRESS": "[::]",
    "BIND_ADDRESS": "127.0.0.1",
})


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
    config.set_home("/tmp/hop3")
    workers: dict[str, str] = {}
    nginx = Nginx(App("testapp"), env, workers)
    nginx.setup()


def test_setup_with_workers(env: Env) -> None:
    config.set_home("/tmp/hop3")
    workers = {"static": "public"}
    nginx = Nginx(App("testapp"), env, workers)
    nginx.setup()
