# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for hop3_installer.bundler module."""

from __future__ import annotations

from hop3_installer.bundler import (
    CLI_MODULES,
    SERVER_MODULES,
    extract_code_body,
    extract_imports,
    is_stdlib_module,
    validate_bundle,
)

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
        imports, remaining = extract_imports(source)
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
        imports, remaining = extract_imports(source)
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
