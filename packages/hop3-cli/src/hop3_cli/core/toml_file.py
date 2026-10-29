# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Read a TOML file the CLI depends on (a hop3.toml, a pyproject.toml, an overlay)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import tomllib

from hop3_cli.exceptions import ConfigError

if TYPE_CHECKING:
    from pathlib import Path


def read_toml(path: Path) -> dict[str, Any]:
    """
    Parse the TOML file at ``path``; ``{}`` if it is absent.

    Any other failure raises ``ConfigError`` naming the file and the cause.
    A file that exists but cannot be read must not pass for an empty one: a
    malformed hop3.toml read as ``{}`` dropped ``[build].ignore``, so a deploy
    uploaded the files it excluded.
    """
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        return {}
    except tomllib.TOMLDecodeError as e:
        msg = f"{path} is not valid TOML: {e}. Fix the file and retry."
        raise ConfigError(msg) from e
    except OSError as e:
        msg = f"cannot read {path}: {e.strerror or e}."
        raise ConfigError(msg) from e
