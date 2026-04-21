# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: AGPL-3.0-only

"""Tests for base.py template helpers.

These are the most logic-dense functions in the generator — they handle
Nix escaping, shell heredoc construction, config file formatting, and
wrapper script assembly.
"""

from __future__ import annotations

import pytest

from hop3.plugins.build.nix.gen.spec import (
    AppSpec,
    ConditionalEnvVar,
    ConfigFile,
    Source,
)
from hop3.plugins.build.nix.gen.templates.base import (
    format_config_file,
    format_env_exports,
    format_local_vars,
    format_nix_env_attrs,
    format_nix_runtime_libs,
    format_paths_json,
    format_runtime_env_json,
    format_wrapper_body,
)

# --- format_local_vars ---


def test_local_vars_empty():
    assert format_local_vars({}) == ""


def test_local_vars_simple():
    result = format_local_vars({"PORT": "8080"})
    assert result == 'PORT="8080"'


def test_local_vars_with_shell_default():
    result = format_local_vars({"PORT": "${PORT:-8080}"})
    assert result == "PORT=\"''${PORT:-8080}\""


def test_local_vars_multiple():
    result = format_local_vars({"A": "1", "B": "2"})
    lines = result.split("\n")
    assert len(lines) == 2
    assert 'A="1"' in lines[0]
    assert 'B="2"' in lines[1]


# --- format_env_exports ---


def _make_spec(**kwargs) -> AppSpec:
    """Helper to create a minimal AppSpec with overrides."""
    defaults = {
        "pname": "test",
        "version": "1.0",
        "description": "test",
        "template": "prebuilt-binary",
        "binary_name": "test",
        "source": Source(url="x", sha256="x", executable=True),
    }
    defaults.update(kwargs)
    return AppSpec(**defaults)


def test_env_exports_empty():
    spec = _make_spec(env_exports={})
    assert format_env_exports(spec) == ""


def test_env_exports_simple():
    spec = _make_spec(env_exports={"DEBUG": "false"})
    result = format_env_exports(spec)
    assert result == 'export DEBUG="false"'


def test_env_exports_escapes_shell_vars():
    spec = _make_spec(env_exports={"ADDR": "0.0.0.0:${PORT:-8080}"})
    result = format_env_exports(spec)
    assert "''${PORT:-8080}" in result


def test_env_exports_bare_dollar_not_escaped():
    spec = _make_spec(env_exports={"WORK_DIR": "$PWD"})
    result = format_env_exports(spec)
    assert "$PWD" in result
    assert "''$" not in result


def test_conditional_env_var():
    spec = _make_spec(
        conditional_env_exports=[
            ConditionalEnvVar(
                name="DB_URL",
                condition_var="DB_URL",
                value="postgres://${PGUSER}@localhost",
            )
        ]
    )
    result = format_env_exports(spec)
    assert 'if [ -z "$DB_URL" ]' in result
    assert "''${PGUSER}" in result
    assert "fi" in result


def test_conditional_with_static_exports():
    spec = _make_spec(
        env_exports={"A": "1"},
        conditional_env_exports=[
            ConditionalEnvVar(name="B", condition_var="B", value="2")
        ],
    )
    result = format_env_exports(spec)
    assert 'export A="1"' in result
    assert 'if [ -z "$B" ]' in result


# --- format_config_file ---


def test_config_raw():
    cf = ConfigFile(
        path="config.json",
        format="raw",
        raw_content='{"port": ${PORT}}',
    )
    result = format_config_file(cf)
    assert "cat > config.json << EOF" in result
    assert "''${PORT}" in result
    assert result.endswith("EOF")


def test_config_raw_requires_content():
    cf = ConfigFile(path="x", format="raw")
    with pytest.raises(ValueError, match="raw format requires raw_content"):
        format_config_file(cf)


def test_config_ini():
    cf = ConfigFile(
        path="app.ini",
        format="ini",
        sections={
            "server": {"port": "${PORT}", "host": "0.0.0.0"},
            "log": {"level": "info"},
        },
    )
    result = format_config_file(cf)
    assert "[server]" in result
    assert "port = ''${PORT}" in result
    assert "host = 0.0.0.0" in result
    assert "[log]" in result
    assert "level = info" in result


def test_config_ini_empty_sections():
    cf = ConfigFile(path="app.ini", format="ini", sections={})
    result = format_config_file(cf)
    assert "cat > app.ini << EOF" in result


def test_config_unsupported_format():
    cf = ConfigFile(path="x", format="xml")
    with pytest.raises(NotImplementedError, match="not yet supported"):
        format_config_file(cf)


def test_config_parent_dir_creation():
    cf = ConfigFile(
        path="custom/conf/app.ini",
        format="ini",
        sections={"s": {"k": "v"}},
    )
    result = format_config_file(cf)
    assert "mkdir -p custom/conf" in result


def test_config_no_parent_dir():
    cf = ConfigFile(path="config", format="raw", raw_content="x")
    result = format_config_file(cf)
    assert "mkdir -p" not in result


def test_config_create_if_missing():
    cf = ConfigFile(
        path="config.yml",
        format="raw",
        raw_content="port: 8080\n",
        create_if_missing=True,
    )
    result = format_config_file(cf)
    assert result.startswith("if [ ! -f config.yml ]; then")
    assert "cat > config.yml << EOF" in result
    assert result.endswith("fi")


def test_config_create_if_missing_no_indentation():
    """Heredoc body must NOT be indented — that would add spaces to the config."""
    cf = ConfigFile(
        path="c",
        format="raw",
        raw_content="key = value\n",
        create_if_missing=True,
    )
    result = format_config_file(cf)
    # The heredoc content line should start at column 0, not indented
    lines = result.split("\n")
    content_line = next(line for line in lines if "key = value" in line)
    assert not content_line.startswith(" ")


# --- format_wrapper_body ---


def test_wrapper_minimal():
    spec = _make_spec()
    result = format_wrapper_body(spec, "BINDIR/test")
    assert result.startswith("#!/bin/sh")
    assert "exec BINDIR/test" in result


def test_wrapper_with_local_vars():
    spec = _make_spec(local_vars={"PORT": "${PORT:-8080}"})
    result = format_wrapper_body(spec, "BINDIR/test")
    assert "PORT=\"''${PORT:-8080}\"" in result
    # local vars come before exec
    assert result.index("PORT=") < result.index("exec")


def test_wrapper_with_pre_exec():
    spec = _make_spec(pre_exec_commands=["mkdir -p data", "chmod 700 data"])
    result = format_wrapper_body(spec, "BINDIR/test")
    assert "mkdir -p data" in result
    assert "chmod 700 data" in result
    assert result.index("mkdir") < result.index("exec")


def test_wrapper_exec_line_escapes_shell_vars():
    spec = _make_spec()
    result = format_wrapper_body(spec, "PHPBIN/php -S 0.0.0.0:${PORT:-8080}")
    assert "''${PORT:-8080}" in result


def test_wrapper_exec_line_preserves_dollar_commands():
    spec = _make_spec()
    result = format_wrapper_body(spec, "java $JAVA_OPTS -jar app.war")
    assert "$JAVA_OPTS" in result
    assert "''$" not in result  # bare $ is not escaped


def test_wrapper_section_order():
    """Verify the order: shebang, local vars, exports, config, pre-exec, exec.

    Config files come before pre-exec because pre-exec commands may depend
    on generated config files (e.g., LimeSurvey's install needs config.php).
    """
    spec = _make_spec(
        local_vars={"X": "1"},
        env_exports={"Y": "2"},
        pre_exec_commands=["mkdir -p data"],
        config_files=[ConfigFile(path="c", format="raw", raw_content="content\n")],
    )
    result = format_wrapper_body(spec, "BINDIR/test")
    shebang_pos = result.index("#!/bin/sh")
    local_pos = result.index('X="1"')
    export_pos = result.index('export Y="2"')
    config_pos = result.index("cat > c")
    mkdir_pos = result.index("mkdir -p data")
    exec_pos = result.index("exec BINDIR/test")
    assert shebang_pos < local_pos < export_pos < config_pos < mkdir_pos < exec_pos


# --- format_runtime_env_json ---


def test_runtime_env_json_empty():
    assert format_runtime_env_json({}) == ""


def test_runtime_env_json_single():
    result = format_runtime_env_json({"KEY": "value"})
    assert '"KEY": "value"' in result
    assert "," not in result  # no trailing comma for single item


def test_runtime_env_json_multiple():
    result = format_runtime_env_json({"A": "1", "B": "2"})
    assert '"A": "1",' in result
    assert '"B": "2"' in result
    # Last item has no comma
    lines = result.strip().split("\n")
    assert not lines[-1].rstrip().endswith(",")


# --- format_nix_env_attrs ---


def test_nix_env_attrs_empty():
    assert format_nix_env_attrs({}) == ""


def test_nix_env_attrs_single():
    result = format_nix_env_attrs({"KEY": "value"})
    assert 'KEY = "value";' in result


# --- format_paths_json ---


def test_paths_json_no_extra():
    result = format_paths_json([])
    assert result == '"$out/bin"'


def test_paths_json_with_extras():
    result = format_paths_json(["${php}/bin", "${nodejs}/bin"])
    assert '"$out/bin"' in result
    assert '"${php}/bin"' in result
    assert '"${nodejs}/bin"' in result


# --- format_nix_runtime_libs (DEFERRED-APPS blocker #2) ---


def test_nix_runtime_libs_empty():
    assert format_nix_runtime_libs([]) == ""


def test_nix_runtime_libs_single_attr():
    result = format_nix_runtime_libs(["postgresql.lib"])
    # Nix interpolation reference — must NOT be escaped.
    assert "${pkgs.postgresql.lib}/lib" in result
    # Shell fallback for unset LD_LIBRARY_PATH — MUST be Nix-escaped
    # so the shell, not Nix, expands it at runtime.
    assert "''${LD_LIBRARY_PATH:-}" in result


def test_nix_runtime_libs_multiple_attrs_joined_by_colon():
    result = format_nix_runtime_libs(["postgresql.lib", "krb5.lib"])
    # Each entry appears in order, separated by `:`
    assert (
        "${pkgs.postgresql.lib}/lib:${pkgs.krb5.lib}/lib:''${LD_LIBRARY_PATH:-}"
        in result
    )


def test_nix_runtime_libs_supports_dotted_attribute_paths():
    # stdenv.cc.cc.lib is the canonical way to reference libstdc++.so.6
    # in nixpkgs; the helper must pass the dotted path through verbatim.
    result = format_nix_runtime_libs(["stdenv.cc.cc.lib"])
    assert "${pkgs.stdenv.cc.cc.lib}/lib" in result


def test_nix_runtime_libs_full_line_shape():
    # Full canonical form — what ends up in the generated wrapper. This
    # must match the hand-crafted variant's working pattern exactly.
    result = format_nix_runtime_libs(["postgresql.lib", "krb5.lib", "stdenv.cc.cc.lib"])
    expected = (
        'export LD_LIBRARY_PATH="'
        "${pkgs.postgresql.lib}/lib:"
        "${pkgs.krb5.lib}/lib:"
        "${pkgs.stdenv.cc.cc.lib}/lib:"
        "''${LD_LIBRARY_PATH:-}"
        '"'
    )
    assert result == expected


def test_wrapper_body_injects_runtime_libs_between_exports_and_pre_exec():
    spec = _make_spec(
        nix_runtime_libs=["postgresql.lib"],
        env_exports={"FOO": "bar"},
        pre_exec_commands=["some-setup"],
    )
    body = format_wrapper_body(spec, "app")

    # Positional invariant: env exports BEFORE runtime libs BEFORE
    # pre-exec BEFORE the final exec. The order matters because pre-exec
    # may invoke the app's pip-installed Python, which needs LD_LIBRARY_PATH
    # set beforehand.
    export_idx = body.index('export FOO="bar"')
    libs_idx = body.index("LD_LIBRARY_PATH")
    preexec_idx = body.index("some-setup")
    exec_idx = body.index("exec")
    assert export_idx < libs_idx < preexec_idx < exec_idx


def test_wrapper_body_omits_runtime_libs_when_unset():
    spec = _make_spec(nix_runtime_libs=[])
    body = format_wrapper_body(spec, "app")
    assert "LD_LIBRARY_PATH" not in body
