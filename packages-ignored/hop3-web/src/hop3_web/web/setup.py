# Copyright (c) 2023-2025, Abilian SAS

from __future__ import annotations

from importlib import import_module

from flask import Blueprint, Flask
from loguru import logger

MODULES = [
    "hop3_web.web.blueprints.admin",
    "hop3_web.web.blueprints.user",
]


#
# Registration
#
def register_blueprints(app: Flask) -> None:
    blueprints = set()
    for module_name in MODULES:
        module = import_module(module_name)
        blueprint = _find_blueprint(module)
        blueprints.add(blueprint)

    for blueprint in blueprints:
        logger.debug("Registering blueprint {name}", name=blueprint.name)
        app.register_blueprint(blueprint)


def _find_blueprint(module):
    if hasattr(module, "blueprint"):
        blueprint = module.blueprint
        assert isinstance(blueprint, Blueprint)
        return blueprint

    module_name = module.__name__
    if "." not in module_name:
        msg = f"Could not find blueprint for module {module_name}"
        raise ValueError(msg)

    parent_module_name = module_name.rsplit(".", 1)[0]
    parent_module = import_module(parent_module_name)
    return _find_blueprint(parent_module)
