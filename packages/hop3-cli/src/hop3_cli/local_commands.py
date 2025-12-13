# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Backward compatibility shim - import from hop3_cli.commands instead."""

from __future__ import annotations

from .commands.local import (
    LOCAL_COMMANDS,
    LOCAL_COMMANDS_INFO,
    BootstrapError,
    create_admin_via_ssh,
    extract_token,
    fetch_and_save_certificate,
    get_token_via_ssh,
    handle_auth,
    handle_init,
    handle_local_command,
    handle_login,
    handle_login_password,
    handle_login_ssh,
    handle_login_token,
    handle_settings,
    handle_version,
    infer_server_url,
    is_local_command,
    print_init_help,
    print_login_help,
    print_settings_help,
    settings_get,
    settings_set,
    settings_show,
)

__all__ = [
    "LOCAL_COMMANDS",
    "LOCAL_COMMANDS_INFO",
    "BootstrapError",
    "create_admin_via_ssh",
    "extract_token",
    "fetch_and_save_certificate",
    "get_token_via_ssh",
    "handle_auth",
    "handle_init",
    "handle_local_command",
    "handle_login",
    "handle_login_password",
    "handle_login_ssh",
    "handle_login_token",
    "handle_settings",
    "handle_version",
    "infer_server_url",
    "is_local_command",
    "print_init_help",
    "print_login_help",
    "print_settings_help",
    "settings_get",
    "settings_set",
    "settings_show",
]
