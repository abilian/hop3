# Copyright (c) 2025-2026, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

"""Adapter: construct an AppSpec from parsed hop3.toml sections.

Maps the ``[nix]`` section of hop3.toml (a dict parsed from TOML) into
the AppSpec dataclass consumed by the template generator.

The TOML field names use kebab-case (hop3.toml convention); the AppSpec
fields use snake_case (Python convention). This module handles the
translation.
"""

from __future__ import annotations

from typing import Any

from hop3.plugins.build.nix.gen.spec import (
    AppSpec,
    ConditionalEnvVar,
    ConfigFile,
    FileMapping,
    Source,
)


def app_spec_from_config(
    nix_config: dict[str, Any],
    metadata: dict[str, Any],
    app_name: str,
) -> AppSpec:
    """Construct an AppSpec from parsed hop3.toml sections.

    Args:
        nix_config: The ``[nix]`` section from hop3.toml (dict).
        metadata: The ``[metadata]`` section from hop3.toml (dict).
        app_name: The application name (fallback for pname).

    Returns:
        An AppSpec ready to be passed to ``generate()``.

    Raises:
        ValueError: If required fields are missing.
    """
    template = nix_config.get("template")
    if not template:
        msg = "[nix].template is required"
        raise ValueError(msg)

    # Build Source from [nix] fields
    source = Source(
        url=nix_config.get("url", ""),
        sha256=nix_config.get("sha256", ""),
        executable=nix_config.get("executable", False),
        archive=nix_config.get("archive"),
    )

    # Parse nested structures
    config_files = _parse_config_files(nix_config.get("config-files", []))
    file_mappings = _parse_file_mappings(nix_config.get("file-mappings", []))
    conditional_env = _parse_conditional_env(nix_config.get("conditional-env", []))

    return AppSpec(
        # Identity — from [metadata] with fallbacks
        pname=metadata.get("id", app_name),
        version=str(metadata.get("version", nix_config.get("version", ""))),
        description=metadata.get("description", ""),
        template=template,
        source=source,
        # prebuilt-binary fields
        binary_name=nix_config.get("binary-name"),
        # prebuilt-archive fields
        source_root=nix_config.get("source-root"),
        file_mappings=file_mappings,
        # php-app fields
        php_version=nix_config.get("php-version", "php82"),
        php_extensions=nix_config.get("php-extensions", []),
        needs_composer=nix_config.get("needs-composer", False),
        composer_extra_flags=nix_config.get("composer-extra-flags", []),
        strip_components=nix_config.get("strip-components", 1),
        serve_mode=nix_config.get("serve-mode", "builtin"),
        web_root=nix_config.get("web-root", ""),
        post_install_dirs=nix_config.get("post-install-dirs", []),
        single_file=nix_config.get("single-file", False),
        skip_source_copy=nix_config.get("skip-source-copy", False),
        needs_writable_dir=nix_config.get("needs-writable-dir", False),
        extra_native_build_inputs=nix_config.get("extra-native-build-inputs", []),
        # nixpkgs-wrapper fields
        nixpkgs_package=nix_config.get("nixpkgs-package"),
        # node-prebuilt / java-war / python-venv fields
        runtime_package=nix_config.get("runtime-package"),
        unpack_without_top_level=nix_config.get("unpack-without-top-level", False),
        war_file=nix_config.get("war-file"),
        jvm_default_opts=nix_config.get("jvm-default-opts"),
        pip_packages=nix_config.get("pip-packages", []),
        # Wrapper script fields
        exec_target=nix_config.get("exec-target"),
        exec_args=nix_config.get("exec-args", []),
        local_vars=nix_config.get("local-vars", {}),
        env_exports=nix_config.get("env-exports", {}),
        conditional_env_exports=conditional_env,
        pre_exec_commands=nix_config.get("pre-exec", []),
        config_files=config_files,
        # Runtime metadata
        runtime_env=nix_config.get("runtime-env", {}),
        extra_paths=nix_config.get("extra-paths", []),
    )


def _parse_config_files(raw: list[dict[str, Any]]) -> list[ConfigFile]:
    """Parse [[nix.config-files]] array of tables."""
    result = []
    for entry in raw:
        result.append(
            ConfigFile(
                path=entry["path"],
                format=entry.get("format", "raw"),
                sections=entry.get("sections"),
                raw_content=entry.get("raw-content"),
                create_if_missing=entry.get("create-if-missing", False),
            )
        )
    return result


def _parse_file_mappings(raw: list[dict[str, Any]]) -> list[FileMapping]:
    """Parse [[nix.file-mappings]] array of tables."""
    result = []
    for entry in raw:
        result.append(
            FileMapping(
                source=entry["source"],
                destination=entry["destination"],
                recursive=entry.get("recursive", True),
                executable=entry.get("executable", False),
            )
        )
    return result


def _parse_conditional_env(raw: list[dict[str, Any]]) -> list[ConditionalEnvVar]:
    """Parse [[nix.conditional-env]] array of tables."""
    result = []
    for entry in raw:
        result.append(
            ConditionalEnvVar(
                name=entry["name"],
                condition_var=str(entry.get("condition-var", entry["name"])),
                value=entry["value"],
            )
        )
    return result
