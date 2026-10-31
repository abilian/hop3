# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for hop3_installer.bundler module."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
import tomllib
from hop3_installer.bundler import (
    CLI_MODULES,
    SERVER_MODULES,
    _collect_import_statements,
    bundle_installer,
    extract_code_body,
    extract_imports,
    is_stdlib_module,
    validate_bundle,
)
from hop3_installer.cli_installer import checks
from hop3_installer.common import MIN_PYTHON

# =============================================================================
# Import-symbol preservation (regression: `from typing import TypedDict`
# must survive bundling — dropping the symbol shipped a NameError at install
# time. Fast tier so the inner loop catches a bundler-import regression.)
# =============================================================================


class TestImportSymbolPreservation:
    def test_collect_preserves_from_import_symbols(self):
        src = "from typing import TypedDict, overload\nimport os\n"
        stmts = _collect_import_statements(src)
        assert {"from typing import TypedDict", "from typing import overload"} <= stmts
        assert "import os" in stmts

    def test_overlapping_imports_from_two_modules_are_emitted_once(self):
        # Joined statements left `from dataclasses import dataclass` beside
        # `from dataclasses import dataclass, field` (F811 in the bundle).
        stmts = _collect_import_statements("from dataclasses import dataclass\n")
        stmts |= _collect_import_statements(
            "from dataclasses import dataclass, field\n"
        )
        assert stmts == {
            "from dataclasses import dataclass",
            "from dataclasses import field",
        }

    def test_collect_skips_relative_and_future(self):
        src = "from __future__ import annotations\nfrom .common import X\n"
        assert _collect_import_statements(src) == set()

    def test_collect_finds_conditional_imports(self):
        # imports under `if TYPE_CHECKING:` are still collected (ast.walk).
        src = "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from typing import ClassVar\n"
        stmts = _collect_import_statements(src)
        assert "from typing import ClassVar" in stmts

    def test_server_bundle_keeps_typeddict_symbol(self):
        # Not just `import typing` — the bare name must be importable at runtime.
        # Order-independent: the symbol is co-imported (`from typing import
        # TypedDict, overload`), so match the name within a typing from-import
        # rather than a brittle exact string a linter can reorder.
        source = bundle_installer("server")
        assert re.search(r"^from typing import .*\bTypedDict\b", source, re.MULTILINE)

    @pytest.mark.parametrize("installer_type", ["cli", "server"])
    def test_bundle_runs_on_its_minimum_python(self, installer_type):
        # The bundle's floor is MIN_PYTHON (3.10, Ubuntu 22.04's python3), below
        # the package's own requires-python. These 3.11-only names imported
        # cleanly in tests and crashed the curl-piped installer on 3.10.
        source = bundle_installer(installer_type)
        assert "MIN_PYTHON = (3, 10)" in source
        used: set[str] = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import | ast.ImportFrom):
                used.update(alias.name for alias in node.names)
                used.add(getattr(node, "module", None) or "")
            elif isinstance(node, ast.Attribute):
                used.add(node.attr)
        assert not used & {"tomllib", "Self", "UTC", "StrEnum"}


# =============================================================================
# Constants Tests
# =============================================================================


class TestConstants:
    """Tests for module constants."""

    def test_cli_modules_starts_with_common(self):
        """CLI_MODULES should start with common.py."""
        assert CLI_MODULES[0] == "common.py"

    def test_server_modules_starts_with_common(self):
        """SERVER_MODULES should start with common.py."""
        assert SERVER_MODULES[0] == "common.py"

    def test_cli_modules_contains_installer(self):
        """CLI_MODULES should contain the CLI installer."""
        assert "cli_installer/installer.py" in CLI_MODULES

    def test_server_modules_contains_installer(self):
        """SERVER_MODULES should contain the server installer."""
        assert "server_installer/installer.py" in SERVER_MODULES

    def test_is_stdlib_module_detects_common_modules(self):
        """is_stdlib_module should correctly identify stdlib modules."""
        # Common stdlib modules
        assert is_stdlib_module("os") is True
        assert is_stdlib_module("sys") is True
        assert is_stdlib_module("subprocess") is True
        assert is_stdlib_module("pathlib") is True
        assert is_stdlib_module("urllib.request") is True

        # Non-stdlib modules
        assert is_stdlib_module("requests") is False
        assert is_stdlib_module("numpy") is False
        assert is_stdlib_module("hop3_installer") is False


# =============================================================================
# extract_imports Tests
# =============================================================================


class TestExtractImports:
    """Tests for extract_imports function."""

    def test_extracts_simple_import(self):
        """extract_imports should extract simple import statements."""
        source = """
import os
import sys

def main():
    pass
"""
        imports, remaining = extract_imports(source)
        assert "os" in imports
        assert "sys" in imports
        assert "import os" not in remaining

    def test_extracts_from_import(self):
        """extract_imports should extract from...import statements."""
        source = """
from pathlib import Path
from typing import Optional

def main():
    pass
"""
        imports, _remaining = extract_imports(source)
        assert "pathlib" in imports
        assert "typing" in imports

    def test_removes_relative_imports(self):
        """extract_imports should remove relative imports."""
        source = """
from ..common import Colors
from .config import Config

def main():
    pass
"""
        imports, remaining = extract_imports(source)
        # Relative imports should not be in imports
        assert "common" not in imports
        assert "config" not in imports
        # Should not appear in remaining code either
        assert "from ..common" not in remaining
        assert "from .config" not in remaining

    def test_preserves_code_body(self):
        """extract_imports should preserve non-import code."""
        source = """
import os

def hello():
    print("hello")

class MyClass:
    pass
"""
        _imports, remaining = extract_imports(source)
        assert "def hello():" in remaining
        assert 'print("hello")' in remaining
        assert "class MyClass:" in remaining


# =============================================================================
# extract_code_body Tests
# =============================================================================


class TestExtractCodeBody:
    """Tests for extract_code_body function."""

    def test_removes_docstring(self):
        """extract_code_body should remove module docstring."""
        source = '''"""This is a module docstring."""

import os

def main():
    pass
'''
        result = extract_code_body(source)
        assert "This is a module docstring" not in result
        assert "def main():" in result

    def test_removes_multiline_docstring(self):
        """extract_code_body should remove multiline docstrings."""
        source = '''"""
This is a
multiline docstring.
"""

def main():
    pass
'''
        result = extract_code_body(source)
        assert "multiline docstring" not in result
        assert "def main():" in result

    def test_preserves_code_without_docstring(self):
        """extract_code_body should work on files without docstring."""
        source = """
def main():
    pass
"""
        result = extract_code_body(source)
        assert "def main():" in result


# =============================================================================
# validate_bundle Tests
# =============================================================================


class TestValidateBundle:
    """Tests for validate_bundle function."""

    def test_validates_valid_python(self):
        """validate_bundle should return True for valid Python."""
        source = """
import os

def main():
    print("Hello")

if __name__ == "__main__":
    main()
"""
        assert validate_bundle(source) is True

    def test_rejects_syntax_error(self):
        """validate_bundle should return False for syntax errors."""
        source = """
def main(
    # Missing closing parenthesis
    pass
"""
        assert validate_bundle(source) is False

    def test_rejects_invalid_indentation(self):
        """validate_bundle should return False for indentation errors."""
        source = """
def main():
print("bad indent")
"""
        assert validate_bundle(source) is False

    def test_validates_empty_source(self):
        """validate_bundle should return True for empty source."""
        assert validate_bundle("") is True
        assert validate_bundle("   \n\n   ") is True

    def test_validates_complex_code(self):
        """validate_bundle should validate complex valid Python."""
        source = """
from __future__ import annotations

import os
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

@dataclass
class Config:
    name: str
    value: Optional[int] = None

def main() -> int:
    config = Config(name="test")
    return 0

if __name__ == "__main__":
    sys.exit(main())
"""
        assert validate_bundle(source) is True


def test_the_package_supports_the_bundles_minimum_python():
    """
    `pip install hop3-installer` must work where the one-liner does. The floor
    was raised to 3.11 for a dev-time generator, which locked Ubuntu 22.04's
    python3 out of the package while the bundle still supported it.
    """
    pyproject = Path(__file__).parents[2] / "pyproject.toml"
    floor = tomllib.loads(pyproject.read_text())["project"]["requires-python"]
    assert floor == ">={}.{}".format(*MIN_PYTHON)


def test_check_venv_needs_ensurepip_too(monkeypatch):
    """Debian ships venv without ensurepip until python3-venv is installed."""
    monkeypatch.setattr(
        checks.importlib.util,
        "find_spec",
        lambda name: None if name == "ensurepip" else object(),
    )
    assert checks.check_venv() is False
