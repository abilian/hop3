"""hop3-nix-gen: template-based hop3.nix generator."""

from hop3_nix_gen.registry import generate
from hop3_nix_gen.spec import (
    AppSpec,
    ConditionalEnvVar,
    ConfigFile,
    FileMapping,
    Source,
)

__all__ = [
    "AppSpec",
    "ConditionalEnvVar",
    "ConfigFile",
    "FileMapping",
    "Source",
    "generate",
]
