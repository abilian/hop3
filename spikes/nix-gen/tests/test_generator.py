"""Integration tests: generate each spec and check basic properties."""

import pytest

from hop3_nix_gen.registry import generate, list_templates
from hop3_nix_gen.specs import SPECS


def test_templates_registered():
    names = list_templates()
    assert "prebuilt-binary" in names
    assert "prebuilt-archive" in names


def test_all_specs_have_valid_template():
    registered = set(list_templates())
    for name, spec in SPECS.items():
        assert spec.template in registered, (
            f"Spec {name!r} uses unknown template {spec.template!r}"
        )


@pytest.mark.parametrize("app_name", sorted(SPECS.keys()))
def test_spec_generates_without_error(app_name: str):
    spec = SPECS[app_name]
    result = generate(spec)
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.parametrize("app_name", sorted(SPECS.keys()))
def test_output_contains_required_elements(app_name: str):
    spec = SPECS[app_name]
    output = generate(spec)

    # Every output should declare pkgs input
    assert "{ pkgs ? import <nixpkgs> {} }" in output

    # Should have a `let` block
    assert "\nlet\n" in output

    # Should have a version binding
    assert f'version = "{spec.version}"' in output

    # Should have the pname
    assert f'pname = "{spec.pname}"' in output

    # Should produce a package attribute
    assert "package = app;" in output

    # Should have a runtime.json generation
    assert "$out/hop3/runtime.json" in output


@pytest.mark.parametrize("app_name", sorted(SPECS.keys()))
def test_output_uses_nix_escaped_vars(app_name: str):
    """Verify that shell variables ARE properly escaped where they appear.

    Inside the generated wrapper script, any ${VAR} must be escaped to ''${VAR}
    so Nix does not try to interpolate them at build time.
    """
    spec = SPECS[app_name]
    output = generate(spec)

    # If the spec has any shell variable references, they should be escaped
    # in the final output (inside the multi-line Nix string).
    if spec.local_vars or spec.env_exports:
        # Check that at least one escaped ${...} appears
        # (assuming the spec uses shell variable defaults)
        has_shell_vars = any("${" in v for v in spec.local_vars.values()) or any(
            "${" in v for v in spec.env_exports.values()
        )
        if has_shell_vars:
            assert "''${" in output, f"Expected escaped ${{ in output for {app_name}"
