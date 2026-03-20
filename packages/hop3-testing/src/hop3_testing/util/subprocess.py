# Copyright (c) 2024-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Subprocess utilities for test execution."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hop3_testing.targets import TargetInfo


def build_test_env(target_info: TargetInfo) -> dict[str, str]:
    """Build environment variables for test subprocess execution.

    Args:
        target_info: Target information with SSH connection details.

    Returns:
        Environment dict with HOP3_TEST_* variables added.
    """
    return {
        **os.environ,
        "HOP3_TEST_HOST": target_info.ssh_host,
        "HOP3_TEST_PORT": str(target_info.ssh_port),
        "HOP3_TEST_SSH_KEY": target_info.ssh_key or "",
    }
