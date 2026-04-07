#!/usr/bin/env python3
"""Migrate spike Python specs to [nix] sections in hop3.toml files.

Reads each spec from spikes/nix-gen/src/hop3_nix_gen/specs/, generates
the equivalent [nix] TOML section, and appends it to the corresponding
apps/real-apps-nix/<app>/hop3.toml.

Also adds [metadata] if missing, and backs up hop3.nix to hop3.nix.bak.

Usage:
    python scripts/migrate-nix-specs-to-toml.py [--dry-run]
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add spike to path
sys.path.insert(0, str(Path("spikes/nix-gen/src")))

from hop3_nix_gen.spec import AppSpec, ConditionalEnvVar, ConfigFile, FileMapping
from hop3_nix_gen.specs import SPECS


APPS_DIR = Path("apps/real-apps-nix")


def spec_to_toml_section(spec: AppSpec) -> str:
    """Convert an AppSpec to a [nix] TOML section string."""
    lines: list[str] = []

    # [metadata] — only if needed
    metadata_lines = []
    if spec.pname:
        metadata_lines.append(f'id = "{spec.pname}"')
    if spec.version:
        metadata_lines.append(f'version = "{spec.version}"')
    if spec.description:
        metadata_lines.append(f'description = "{spec.description}"')

    if metadata_lines:
        lines.append("[metadata]")
        lines.extend(metadata_lines)
        lines.append("")

    # [nix] main section
    lines.append("[nix]")
    lines.append(f'template = "{spec.template}"')

    # Source fields
    if spec.source.url and spec.source.url != "file:///dev/null":
        lines.append(f'url = "{spec.source.url}"')
        lines.append(f'sha256 = "{spec.source.sha256}"')
    if spec.source.executable:
        lines.append("executable = true")
    if spec.source.archive:
        lines.append(f'archive = "{spec.source.archive}"')

    # Template-specific scalar fields
    _add_str(lines, "binary-name", spec.binary_name)
    _add_str(lines, "exec-target", spec.exec_target)
    _add_str(lines, "source-root", spec.source_root)
    _add_str(lines, "runtime-package", spec.runtime_package)
    _add_str(lines, "war-file", spec.war_file)
    _add_str(lines, "nixpkgs-package", spec.nixpkgs_package)
    _add_str(lines, "php-version", spec.php_version if spec.php_extensions else None)
    _add_str(lines, "serve-mode", spec.serve_mode if spec.serve_mode != "builtin" else None)
    _add_str(lines, "web-root", spec.web_root if spec.web_root else None)

    if spec.exec_args:
        lines.append(f"exec-args = {spec.exec_args}")
    if spec.php_extensions:
        lines.append(f"php-extensions = {spec.php_extensions}")
    if spec.needs_composer:
        lines.append("needs-composer = true")
    if spec.composer_extra_flags:
        lines.append(f"composer-extra-flags = {spec.composer_extra_flags}")
    if spec.strip_components != 1:
        lines.append(f"strip-components = {spec.strip_components}")
    if spec.post_install_dirs:
        lines.append(f"post-install-dirs = {spec.post_install_dirs}")
    if spec.single_file:
        lines.append("single-file = true")
    if spec.extra_native_build_inputs:
        lines.append(f"extra-native-build-inputs = {spec.extra_native_build_inputs}")
    if spec.unpack_without_top_level:
        lines.append("unpack-without-top-level = true")
    if spec.pip_packages:
        lines.append(f"pip-packages = {spec.pip_packages}")
    if spec.extra_paths:
        lines.append(f"extra-paths = {spec.extra_paths}")
    if spec.pre_exec_commands:
        # Multi-line commands need special handling
        if len(spec.pre_exec_commands) == 1 and "\n" not in spec.pre_exec_commands[0]:
            lines.append(f"pre-exec = {spec.pre_exec_commands}")
        else:
            lines.append("pre-exec = [")
            for cmd in spec.pre_exec_commands:
                if "\n" in cmd:
                    lines.append(f'  """{cmd}"""')
                    lines.append(",")
                else:
                    lines.append(f'  "{cmd}",')
            lines.append("]")

    # [nix.local-vars]
    if spec.local_vars:
        lines.append("")
        lines.append("[nix.local-vars]")
        for k, v in spec.local_vars.items():
            lines.append(f'{k} = "{v}"')

    # [nix.env-exports]
    if spec.env_exports:
        lines.append("")
        lines.append("[nix.env-exports]")
        for k, v in spec.env_exports.items():
            lines.append(f'{k} = "{v}"')

    # [[nix.conditional-env]]
    for cev in spec.conditional_env_exports:
        lines.append("")
        lines.append("[[nix.conditional-env]]")
        lines.append(f'name = "{cev.name}"')
        lines.append(f'condition-var = "{cev.condition_var}"')
        lines.append(f'value = "{cev.value}"')

    # [nix.runtime-env]
    if spec.runtime_env:
        lines.append("")
        lines.append("[nix.runtime-env]")
        for k, v in spec.runtime_env.items():
            lines.append(f'{k} = "{v}"')

    # [[nix.config-files]]
    for cf in spec.config_files:
        lines.append("")
        lines.append("[[nix.config-files]]")
        lines.append(f'path = "{cf.path}"')
        lines.append(f'format = "{cf.format}"')
        if cf.create_if_missing:
            lines.append("create-if-missing = true")
        if cf.raw_content:
            lines.append(f'raw-content = """\n{cf.raw_content}"""')
        if cf.sections:
            for section_name, kvs in cf.sections.items():
                lines.append(f"[nix.config-files.sections.{section_name}]")
                for k, v in kvs.items():
                    lines.append(f'{k} = "{v}"')

    # [[nix.file-mappings]]
    for fm in spec.file_mappings:
        lines.append("")
        lines.append("[[nix.file-mappings]]")
        lines.append(f'source = "{fm.source}"')
        lines.append(f'destination = "{fm.destination}"')
        if not fm.recursive:
            lines.append("recursive = false")
        if fm.executable:
            lines.append("executable = true")

    return "\n".join(lines)


def _add_str(lines: list[str], key: str, value: str | None) -> None:
    if value:
        lines.append(f'{key} = "{value}"')


def migrate_app(app_name: str, spec: AppSpec, dry_run: bool) -> bool:
    """Add [nix] section to an app's hop3.toml and back up hop3.nix."""
    app_dir = APPS_DIR / app_name

    if not app_dir.exists():
        print(f"  SKIP {app_name}: directory not found")
        return False

    toml_path = app_dir / "hop3.toml"
    nix_path = app_dir / "hop3.nix"

    # Check if [nix] section already exists
    if toml_path.exists():
        content = toml_path.read_text()
        if "[nix]" in content:
            print(f"  SKIP {app_name}: [nix] section already exists")
            return False
    else:
        content = ""

    # Generate the TOML section
    nix_section = spec_to_toml_section(spec)

    # Build the new hop3.toml content
    # Strip existing [metadata] if we're adding one
    if "[metadata]" in nix_section and "[metadata]" in content:
        # Remove existing [metadata] section
        new_lines = []
        in_metadata = False
        for line in content.split("\n"):
            if line.strip() == "[metadata]":
                in_metadata = True
                continue
            if in_metadata and line.startswith("["):
                in_metadata = False
            if in_metadata:
                continue
            new_lines.append(line)
        content = "\n".join(new_lines)

    new_content = nix_section + "\n\n" + content.strip() + "\n"

    if dry_run:
        print(f"  DRY RUN {app_name}:")
        print(f"    Would write {len(new_content)} chars to {toml_path}")
        if nix_path.exists():
            print(f"    Would move {nix_path} to {nix_path}.bak")
        return True

    # Write the new hop3.toml
    toml_path.write_text(new_content)

    # Back up hop3.nix
    if nix_path.exists():
        nix_path.rename(nix_path.with_suffix(".nix.bak"))

    print(f"  OK {app_name}")
    return True


def main():
    dry_run = "--dry-run" in sys.argv

    print(f"Migrating {len(SPECS)} apps ({'DRY RUN' if dry_run else 'LIVE'}):")
    print()

    # Skip miniflux — already done manually
    migrated = 0
    for app_name, spec in sorted(SPECS.items()):
        if app_name == "miniflux":
            print(f"  SKIP miniflux: already migrated")
            continue
        if migrate_app(app_name, spec, dry_run):
            migrated += 1

    print()
    print(f"Migrated: {migrated} apps")


if __name__ == "__main__":
    main()
