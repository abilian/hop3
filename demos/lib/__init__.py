# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Shared utilities for Hop3 demos."""

# App management
from lib.app import (
    check_app_status,
    cleanup_app,
    deploy_app,
    ensure_app_removed,
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

# Commands
from lib.commands import CommandError, run_hop3, run_local, run_ssh

# Context and data classes
from lib.context import DemoContext, DemoInfo, DemoResult, OutputLevel

# Output helpers
from lib.output import (
    Colors,
    format_duration,
    get_output_level,
    pause,
    print_blank,
    print_command,
    print_demo_result,
    print_error,
    print_header,
    print_info,
    print_phase_result,
    print_step,
    print_success,
    print_summary_line,
    print_summary_stats,
    print_warning,
    set_output_level,
)

__all__ = [
    # Context
    "DemoContext",
    "DemoInfo",
    "DemoResult",
    "OutputLevel",
    # App management
    "check_app_status",
    "cleanup_app",
    "deploy_app",
    "ensure_app_removed",
    "list_apps",
    "redeploy_app",
    "restart_app",
    "set_env_vars",
    "set_hostname",
    "show_app_structure",
    "show_config",
    "show_file_content",
    "test_app_via_curl",
    "test_app_via_hop3",
    "wait_for_app",
    # Commands
    "CommandError",
    "run_hop3",
    "run_local",
    "run_ssh",
    # Output
    "Colors",
    "format_duration",
    "get_output_level",
    "pause",
    "print_blank",
    "print_command",
    "print_demo_result",
    "print_error",
    "print_header",
    "print_info",
    "print_phase_result",
    "print_step",
    "print_success",
    "print_summary_line",
    "print_summary_stats",
    "print_warning",
    "set_output_level",
]
