# Copyright (c) 2023-2024, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

import flask_super
from flask import Flask

from hop3.core.plugins import scan_package


def create_app():
    app = Flask(__name__)
    scan_package("hop3.model")
    flask_super.init_app(app)
    return app