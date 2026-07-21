# Copyright (c) 2025-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Template registry and top-level generate() function."""

from __future__ import annotations

from hop3.plugins.build.nix.gen.spec import AppSpec  # noqa: TC001
from hop3.plugins.build.nix.gen.templates.base import Template  # noqa: TC001
from hop3.plugins.build.nix.gen.templates.go_source import GoSourceTemplate
from hop3.plugins.build.nix.gen.templates.java_gradle import JavaGradleTemplate
from hop3.plugins.build.nix.gen.templates.java_war import JavaWarTemplate
from hop3.plugins.build.nix.gen.templates.nixpkgs_wrapper import NixpkgsWrapperTemplate
from hop3.plugins.build.nix.gen.templates.node_pnpm_install import (
    NodePnpmInstallTemplate,
)
from hop3.plugins.build.nix.gen.templates.node_prebuilt import NodePrebuiltTemplate
from hop3.plugins.build.nix.gen.templates.php_app import PhpAppTemplate
from hop3.plugins.build.nix.gen.templates.prebuilt_archive import (
    PrebuiltArchiveTemplate,
)
from hop3.plugins.build.nix.gen.templates.prebuilt_binary import PrebuiltBinaryTemplate
from hop3.plugins.build.nix.gen.templates.python_venv import PythonVenvTemplate
from hop3.plugins.build.nix.gen.templates.ruby_bundler import RubyBundlerTemplate

_TEMPLATES: dict[str, Template] = {
    "prebuilt-binary": PrebuiltBinaryTemplate(),
    "prebuilt-archive": PrebuiltArchiveTemplate(),
    "php-app": PhpAppTemplate(),
    "node-prebuilt": NodePrebuiltTemplate(),
    "node-pnpm-install": NodePnpmInstallTemplate(),
    "java-war": JavaWarTemplate(),
    "java-gradle": JavaGradleTemplate(),
    "go-source": GoSourceTemplate(),
    "python-venv": PythonVenvTemplate(),
    "nixpkgs-wrapper": NixpkgsWrapperTemplate(),
    "ruby-bundler": RubyBundlerTemplate(),
}


def get_template(name: str) -> Template:
    """Look up a template by name."""
    if name not in _TEMPLATES:
        available = ", ".join(sorted(_TEMPLATES))
        msg = f"Unknown template: {name!r}. Available: {available}"
        raise ValueError(msg)
    return _TEMPLATES[name]


def generate(spec: AppSpec) -> str:
    """Generate a hop3.nix expression from a spec using the named template."""
    template = get_template(spec.template)
    return template.generate(spec)


def list_templates() -> list[str]:
    """Return the names of all registered templates."""
    return sorted(_TEMPLATES)
