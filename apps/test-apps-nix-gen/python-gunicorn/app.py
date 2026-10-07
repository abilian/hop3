"""A WSGI app with no framework: gunicorn is its only dependency."""

import sys


def application(environ, start_response):
    body = f"Hello World, from gunicorn on Python {sys.version_info[0]}.{sys.version_info[1]}\n"
    start_response("200 OK", [("Content-Type", "text/plain; charset=utf-8")])
    return [body.encode()]
