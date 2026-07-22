# Copyright (c) 2025-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Adapter: construct an AppSpec from parsed hop3.toml sections.

Maps the ``[nix]`` section of hop3.toml (a dict parsed from TOML) into the
AppSpec dataclass consumed by the template generator. TOML keys are kebab-case
(hop3.toml convention), spec fields are snake_case (Python convention); this
module handles the translation, and the key tables below are the single place
that records it.

Every key is claimed by exactly one table: the shared core, or one template's
payload. A key that is not claimed at all, or that is claimed by a template
other than the one selected, is an error. Silently ignoring it is what the
tables exist to prevent — a mistyped ``go-vendor-hsah`` or a ``pip-packages``
left behind by an earlier design used to vanish without a word, and the app
built with a default the author never intended.
"""

from __future__ import annotations

import re
from typing import Any

from hop3.plugins.build.nix.gen.spec import (
    AppSpec,
    ConditionalEnvVar,
    ConfigFile,
    FileMapping,
    GoSourcePayload,
    JavaGradlePayload,
    JavaWarPayload,
    NixpkgsWrapperPayload,
    NodePnpmInstallPayload,
    NodePrebuiltPayload,
    PhpAppPayload,
    PrebuiltArchivePayload,
    PrebuiltBinaryPayload,
    PythonVenvPayload,
    RubyBundlerPayload,
    Source,
    TemplatePayload,
)

_NIXPKGS_REV_RE = re.compile(r"\A[0-9a-f]{40}\Z")
# Nix's own base32 alphabet (no e/o/u/t), 52 chars — or an SRI `sha256-<base64>`.
_NIXPKGS_SHA256_RE = re.compile(
    r"\A(?:[0-9abcdfghijklmnpqrsvwxyz]{52}|sha256-[A-Za-z0-9+/]{43}=)\Z"
)

# TOML keys consumed by this module directly rather than mapped to a field:
# the template selector, the Source parts, and the two array-of-tables that any
# template may carry. Template-specific nested keys are NOT here — they are
# claimed by their payload like any other key, so they are rejected elsewhere.
_CORE_KEYS = {
    "template",
    "url",
    "sha256",
    "executable",
    "archive",
    "version",
    "config-files",
    "conditional-env",
}

# Shared AppSpec fields: TOML key -> field name. No defaults here: an absent key
# is simply not passed, so the dataclass supplies its own. Restating the
# defaults would be a second source of truth, and a mutable one (a `[]` here is
# a single list object every spec would share).
_SHARED_FIELDS: dict[str, str] = {
    "source-root": "source_root",
    "strip-components": "strip_components",
    "runtime-package": "runtime_package",
    "nixpkgs-rev": "nixpkgs_rev",
    "nixpkgs-sha256": "nixpkgs_sha256",
    "exec-target": "exec_target",
    "exec-args": "exec_args",
    "local-vars": "local_vars",
    "env-exports": "env_exports",
    "pre-exec": "pre_exec_commands",
    "writable-home-at-runtime": "writable_home_at_runtime",
    "writable-home-env-var": "writable_home_env_var",
    "runtime-env": "runtime_env",
    "extra-paths": "extra_paths",
    "nix-runtime-libs": "nix_runtime_libs",
}

# Per-template payload fields: template -> (payload class, {TOML key -> field}).
_PAYLOAD_FIELDS: dict[str, tuple[type[TemplatePayload], dict[str, str]]] = {
    "prebuilt-binary": (PrebuiltBinaryPayload, {"binary-name": "binary_name"}),
    "prebuilt-archive": (PrebuiltArchivePayload, {"file-mappings": "file_mappings"}),
    "node-prebuilt": (
        NodePrebuiltPayload,
        {"unpack-without-top-level": "unpack_without_top_level"},
    ),
    "java-war": (
        JavaWarPayload,
        {"war-file": "war_file", "jvm-default-opts": "jvm_default_opts"},
    ),
    "ruby-bundler": (RubyBundlerPayload, {}),
    "python-venv": (
        PythonVenvPayload,
        {"pip-requirements": "requirements", "pip-deps-hash": "deps_hash"},
    ),
    "node-pnpm-install": (
        NodePnpmInstallPayload,
        {
            "npm-package": "npm_package",
            "node-manifest": "manifest",
            "node-lockfile": "lockfile",
            "node-deps-hash": "deps_hash",
            "node-pnpm-package": "pnpm_package",
            "node-native-packages": "native_packages",
        },
    ),
    "java-gradle": (
        JavaGradlePayload,
        {
            "gradle-deps-json": "deps_json",
            "gradle-patches": "patches",
            "gradle-flags": "flags",
            "gradle-jar-glob": "jar_glob",
            "gradle-jar-name": "jar_name",
        },
    ),
    "nixpkgs-wrapper": (
        NixpkgsWrapperPayload,
        {
            "nixpkgs-package": "package",
            "install-extra": "install_extra",
            "exec-prefix": "exec_prefix",
            "nixpkgs-overrides": "overrides",
            "let-extra": "let_extra",
            "env-exports-raw": "env_exports_raw",
        },
    ),
    "php-app": (
        PhpAppPayload,
        {
            "php-version": "php_version",
            "php-extensions": "php_extensions",
            "needs-composer": "needs_composer",
            "composer-deps-hash": "composer_deps_hash",
            "composer-strict-validation": "composer_strict_validation",
            "composer-extra-flags": "composer_extra_flags",
            "serve-mode": "serve_mode",
            "web-root": "web_root",
            "post-install-dirs": "post_install_dirs",
            "single-file": "single_file",
            "skip-source-copy": "skip_source_copy",
            "needs-writable-dir": "needs_writable_dir",
            "extra-native-build-inputs": "extra_native_build_inputs",
        },
    ),
    "go-source": (
        GoSourcePayload,
        {
            "go-vendor-hash": "vendor_hash",
            "go-sub-packages": "sub_packages",
            "go-ldflags": "ldflags",
            "go-proxy-vendor": "proxy_vendor",
            "go-version": "go_version",
            "go-static-dirs": "static_dirs",
            "go-frontend-build": "frontend_build",
            "go-npm-deps-hash": "npm_deps_hash",
            "go-frontend-output": "frontend_output",
            "go-frontend-source-root": "frontend_source_root",
            "go-frontend-pnpm": "frontend_pnpm",
            "go-pnpm-deps-hash": "pnpm_deps_hash",
            "go-pnpm-package": "pnpm_package",
            "go-frontend-node-package": "frontend_node_package",
            "go-frontend-embed-path": "frontend_embed_path",
        },
    ),
}

# Keys retired by a design change. Naming them lets the error say what to do,
# instead of the generic "unknown key" that leaves the author guessing.
_RETIRED_KEYS = {
    "pip-packages": (
        "bare package names are unpinned and unhashed, so the build can be "
        "neither reproduced nor run offline. Ship a hash-pinned lockfile and "
        "set `pip-requirements` instead (python-venv), or list the package in "
        "the committed manifest (node-pnpm-install)."
    ),
}


def _validate_nixpkgs_pin(rev: str, sha256: str) -> None:
    """Reject a malformed per-app nixpkgs pin at parse time.

    A placeholder or typo'd pin used to be interpolated verbatim into the
    generated hop3.nix and shipped: the operator only found out at deploy, via an
    opaque Nix eval error ("hash '…' has wrong length for hash algorithm
    'sha256'"). Refuse to emit a build we already know is broken.
    """
    if not _NIXPKGS_REV_RE.match(rev):
        msg = (
            f"[nix].nixpkgs-rev must be a 40-character git commit SHA, got {rev!r}. "
            "Pick a nixpkgs commit (e.g. from the nixos-25.05 branch)."
        )
        raise ValueError(msg)
    if not _NIXPKGS_SHA256_RE.match(sha256):
        msg = (
            f"[nix].nixpkgs-sha256 must be a nix sha256 hash, got {sha256!r}. "
            "Get it with: nix-prefetch-url --unpack "
            f"https://github.com/NixOS/nixpkgs/archive/{rev}.tar.gz"
        )
        raise ValueError(msg)


def _check_nixpkgs_pin(nix_config: dict[str, Any]) -> None:
    """Validate the optional per-app nixpkgs pin, or accept its absence.

    The two keys are meaningful only as a pair. Expressing that here — with an
    early return for "no pin" — states the both-or-neither rule once, and
    leaves both values narrowed to ``str`` for the format check below.

    Every template honours the pin, so there is no template to refuse it for.
    """
    rev = nix_config.get("nixpkgs-rev")
    sha256 = nix_config.get("nixpkgs-sha256")
    if rev is None and sha256 is None:
        return
    if rev is None or sha256 is None:
        msg = (
            "[nix].nixpkgs-rev and [nix].nixpkgs-sha256 must be set together "
            "(a rev needs its fetchTarball sha256, and vice versa)"
        )
        raise ValueError(msg)
    _validate_nixpkgs_pin(rev, sha256)


def _reject_unclaimed_keys(nix_config: dict[str, Any], template: str) -> None:
    """Fail on any ``[nix]`` key the selected template will never read.

    Three cases, each with its own message: a key retired by a design change, a
    key that belongs to a different template, and a key nothing claims (almost
    always a typo). All three used to be dropped in silence.
    """
    _, payload_keys = _PAYLOAD_FIELDS[template]
    known = _CORE_KEYS | set(_SHARED_FIELDS) | set(payload_keys)

    for key in sorted(nix_config):
        if key in known:
            continue
        if key in _RETIRED_KEYS:
            msg = f"[nix].{key} is no longer supported: {_RETIRED_KEYS[key]}"
            raise ValueError(msg)
        owners = sorted(t for t, (_, keys) in _PAYLOAD_FIELDS.items() if key in keys)
        if owners:
            msg = (
                f"[nix].{key} belongs to the {' / '.join(owners)} template(s), "
                f"not to {template!r}. It would have no effect here."
            )
            raise ValueError(msg)
        msg = (
            f"[nix].{key} is not a known key for the {template!r} template. "
            f"Valid keys: {', '.join(sorted(known))}."
        )
        raise ValueError(msg)


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
        ValueError: If a required field is missing, or a key is unknown,
            retired, or owned by another template.
    """
    template = nix_config.get("template")
    if not template:
        msg = "[nix].template is required"
        raise ValueError(msg)
    if template not in _PAYLOAD_FIELDS:
        available = ", ".join(sorted(_PAYLOAD_FIELDS))
        msg = f"Unknown template: {template!r}. Available: {available}"
        raise ValueError(msg)

    _reject_unclaimed_keys(nix_config, template)
    _check_nixpkgs_pin(nix_config)

    source = Source(
        url=nix_config.get("url", ""),
        sha256=nix_config.get("sha256", ""),
        executable=nix_config.get("executable", False),
        archive=nix_config.get("archive"),
    )

    payload_cls, payload_keys = _PAYLOAD_FIELDS[template]
    payload = payload_cls(**{
        field: _NESTED_PARSERS[key](nix_config[key])
        if key in _NESTED_PARSERS
        else nix_config[key]
        for key, field in payload_keys.items()
        if key in nix_config
    })

    shared = {
        field: nix_config[key]
        for key, field in _SHARED_FIELDS.items()
        if key in nix_config
    }

    return AppSpec(
        pname=metadata.get("id", app_name),
        version=str(metadata.get("version", nix_config.get("version", ""))),
        description=metadata.get("description", ""),
        source=source,
        payload=payload,
        conditional_env_exports=_parse_conditional_env(
            nix_config.get("conditional-env", [])
        ),
        config_files=_parse_config_files(nix_config.get("config-files", [])),
        **shared,
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


# Payload keys arriving as an array of tables, parsed rather than passed
# through. Keyed by TOML name, so ownership works exactly as for scalar keys.
_NESTED_PARSERS = {"file-mappings": _parse_file_mappings}
