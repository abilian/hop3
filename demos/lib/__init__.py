# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Shared utilities for Hop3 demos."""

from .app import (
    check_app_status,
    cleanup_app,
    deploy_app,
    list_apps,
    redeploy_app,
    restart_app,
    set_env_vars,
    set_hostname,
    show_app_structure,
    show_config,
    show_file_content,
    test_app_via_curl,
    test_app_via_hop3,
    wait_for_app,
)
from .commands import run_hop3, run_local, run_ssh
from .context import DemoContext
from .output import (
    Colors,
    pause,
    print_command,
    print_error,
    print_header,
    print_info,
    print_step,
    print_success,
)

__all__ = [
    "Colors",
    "DemoContext",
    "check_app_status",
    "cleanup_app",
    "deploy_app",
    "list_apps",
    "pause",
    "print_command",
    "print_error",
    "print_header",
    "print_info",
    "print_step",
    "print_success",
    "redeploy_app",
    "restart_app",
    "run_hop3",
    "run_local",
    "run_ssh",
    "set_env_vars",
    "set_hostname",
    "show_app_structure",
    "show_config",
    "show_file_content",
    "test_app_via_curl",
    "test_app_via_hop3",
    "wait_for_app",
]
