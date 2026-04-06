"""Template registry and top-level generate() function."""

from __future__ import annotations

from hop3_nix_gen.spec import AppSpec
from hop3_nix_gen.templates.base import Template
from hop3_nix_gen.templates.java_war import JavaWarTemplate
from hop3_nix_gen.templates.nixpkgs_wrapper import NixpkgsWrapperTemplate
from hop3_nix_gen.templates.node_prebuilt import NodePrebuiltTemplate
from hop3_nix_gen.templates.php_app import PhpAppTemplate
from hop3_nix_gen.templates.prebuilt_archive import PrebuiltArchiveTemplate
from hop3_nix_gen.templates.prebuilt_binary import PrebuiltBinaryTemplate
from hop3_nix_gen.templates.python_venv import PythonVenvTemplate

_TEMPLATES: dict[str, Template] = {
    "prebuilt-binary": PrebuiltBinaryTemplate(),
    "prebuilt-archive": PrebuiltArchiveTemplate(),
    "php-app": PhpAppTemplate(),
    "node-prebuilt": NodePrebuiltTemplate(),
    "java-war": JavaWarTemplate(),
    "python-venv": PythonVenvTemplate(),
    "nixpkgs-wrapper": NixpkgsWrapperTemplate(),
}


def register_template(template: Template) -> None:
    """Register a new template. Used by plugins in the real implementation."""
    _TEMPLATES[template.name] = template


def get_template(name: str) -> Template:
    """Look up a template by name."""
    if name not in _TEMPLATES:
        available = ", ".join(sorted(_TEMPLATES))
        raise ValueError(f"Unknown template: {name!r}. Available: {available}")
    return _TEMPLATES[name]


def generate(spec: AppSpec) -> str:
    """Generate a hop3.nix expression from a spec using the named template."""
    template = get_template(spec.template)
    return template.generate(spec)


def list_templates() -> list[str]:
    """Return the names of all registered templates."""
    return sorted(_TEMPLATES)
