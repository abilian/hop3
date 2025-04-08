# Copyright (c) 2025, Abilian SAS
from __future__ import annotations

import argparse

import pytest
from hop3_cli.parser import create_parser  # Adjust import if your structure differs

# --- Fixtures ---


@pytest.fixture(scope="module")
def parser():
    """Provides a pre-built parser instance for tests."""
    return create_parser()


# --- Test Cases ---


def test_parser_creation(parser):
    """Test if the parser object is created successfully."""
    assert isinstance(parser, argparse.ArgumentParser)


def test_version_option(parser):
    """Test the --version global option."""
    with pytest.raises(SystemExit) as e:
        parser.parse_args(["--version"])
    assert e.value.code == 0


def test_help_option_top_level(parser):
    """Test the -h/--help global option at the top level."""
    with pytest.raises(SystemExit) as e:
        parser.parse_args(["--help"])
    assert e.value.code == 0


def test_help_option_subcommand(parser):
    """Test the -h/--help option for a specific command."""
    with pytest.raises(SystemExit) as e:
        parser.parse_args(["apps", "--help"])
    assert e.value.code == 0


def test_help_option_nested_subcommand(parser):
    """Test the -h/--help option for a nested command."""
    with pytest.raises(SystemExit) as e:
        parser.parse_args(["pg", "backup", "--help"])
    assert e.value.code == 0


def test_unknown_command(parser):
    """Test parsing an unknown command."""
    with pytest.raises(SystemExit) as e:
        parser.parse_args(["nonexistentcommand"])
    assert e.value.code != 0  # Should exit with an error code


def test_missing_command(parser):
    """Test parsing with no command provided."""
    with pytest.raises(SystemExit) as e:
        parser.parse_args([])
    assert e.value.code != 0  # Command is required


def test_global_verbose_option(parser):
    """Test the -v/--verbose global option."""
    args = parser.parse_args(["apps", "list", "-v"])
    assert args.verbose == 1

    args = parser.parse_args(["-vv", "apps", "list"])
    assert args.verbose == 2


def test_global_json_option(parser):
    """Test the --json global option."""
    args = parser.parse_args(["apps", "list", "--json"])
    assert args.json is True

    args = parser.parse_args(["apps", "list"])
    assert args.json is False


def test_global_non_interactive_option(parser):
    """Test the -y/--non-interactive global option."""
    args = parser.parse_args(["apps", "delete", "myapp", "-y"])
    assert args.non_interactive is True

    args = parser.parse_args(["apps", "delete", "myapp"])
    assert args.non_interactive is False


def test_global_api_url_option(parser):
    """Test the --api-url global option."""
    test_url = "http://localhost:8080"
    args = parser.parse_args(["--api-url", test_url, "auth", "status"])
    assert args.api_url == test_url

    args = parser.parse_args(["auth", "status"])
    assert args.api_url is None


# --- Specific Command Parsing Tests ---


# Using parametrize for similar structures
@pytest.mark.parametrize(
    ("cmd_str", "expected_attrs"),
    [
        # Auth
        (
            "auth login",
            {"command": "auth", "subcommand": "login", "token": None, "sso": None},
        ),
        (
            "auth login --token abc",
            {"command": "auth", "subcommand": "login", "token": "abc"},
        ),
        (
            "auth logout",
            {"command": "auth", "subcommand": "logout"},
        ),
        (
            "auth status",
            {"command": "auth", "subcommand": "status"},
        ),
        (
            "auth whoami",
            {"command": "auth", "subcommand": "whoami"},
        ),
        # Link/Unlink/Init
        (
            "link my-app --org testorg",
            {"command": "link", "app_name": "my-app", "org": "testorg"},
        ),
        (
            "unlink",
            {"command": "unlink"},
        ),
        (
            "init --name newapp --template node",
            {"command": "init", "name": "newapp", "template": "node", "from_git": None},
        ),
        # Apps
        (
            "apps list --org myorg",
            {"command": "apps", "subcommand": "list", "org": "myorg"},
        ),
        (
            "apps create new-app --region eu-west-1",
            {
                "command": "apps",
                "subcommand": "create",
                "app_name": "new-app",
                "region": "eu-west-1",
            },
        ),
        (
            "apps info",
            {"command": "apps", "subcommand": "info", "app_name": None},
        ),  # Optional arg not provided
        (
            "apps info specific-app",
            {"command": "apps", "subcommand": "info", "app_name": "specific-app"},
        ),
        (
            "apps delete doomed-app",
            {"command": "apps", "subcommand": "delete", "app_name": "doomed-app"},
        ),
        (
            "apps open my-dashboard-app",
            {"command": "apps", "subcommand": "open", "app_name": "my-dashboard-app"},
        ),
        # Instances (Basic)
        (
            "instances list --app myapp --env prod",
            {
                "command": "instances",
                "subcommand": "list",
                "app": "myapp",
                "env": "prod",
            },
        ),
        (
            "instances info i-12345",
            {"command": "instances", "subcommand": "info", "instance_id": "i-12345"},
        ),
        (
            "instances restart i-abc --type web",
            {
                "command": "instances",
                "subcommand": "restart",
                "target": "i-abc",
                "type": "web",
                "app": None,
            },
        ),
        (
            "instances stop --app myapp --env stage",
            {
                "command": "instances",
                "subcommand": "stop",
                "target": None,
                "app": "myapp",
                "env": "stage",
            },
        ),
        # Scale
        (
            "scale set web=3 worker=1 --app myapp",
            {
                "command": "scale",
                "subcommand": "set",
                "scale_args": ["web=3", "worker=1"],
                "app": "myapp",
                "target": None,
            },
        ),
        (
            "scale show --app otherapp --env dev",
            {
                "command": "scale",
                "subcommand": "show",
                "app": "otherapp",
                "env": "dev",
                "target": None,
            },
        ),
        # Build/Dev
        (
            "build --push --tag latest",
            {"command": "build", "push": True, "tag": "latest", "builder": None},
        ),
        (
            "dev run worker",
            {"command": "dev", "subcommand": "run", "process_type": "worker"},
        ),
        # Deploy
        (
            "deploy --app myapp --env prod -m 'Release v1'",
            {
                "command": "deploy",
                "source": None,
                "app": "myapp",
                "env": "prod",
                "message": "Release v1",
                "image": None,
            },
        ),
        (
            "deploy mybranch --app myapp",
            {"command": "deploy", "source": "mybranch", "app": "myapp"},
        ),
        (
            "deploy --image registry/img:tag --app x",
            {
                "command": "deploy",
                "image": "registry/img:tag",
                "app": "x",
                "source": None,
            },
        ),
        # Releases
        (
            "releases list --app a --env b",
            {"command": "releases", "subcommand": "list", "app": "a", "env": "b"},
        ),
        (
            "releases info r-123 --app a",
            {
                "command": "releases",
                "subcommand": "info",
                "release_id": "r-123",
                "app": "a",
            },
        ),
        (
            "releases rollback --app a --env p",
            {
                "command": "releases",
                "subcommand": "rollback",
                "release_id": None,
                "app": "a",
                "env": "p",
            },
        ),
        # Rollback to previous
        (
            "releases rollback r-456 --app a --env p",
            {
                "command": "releases",
                "subcommand": "rollback",
                "release_id": "r-456",
                "app": "a",
                "env": "p",
            },
        ),
        # Config/Secrets
        (
            "config list --app x",
            {"command": "config", "subcommand": "list", "app": "x"},
        ),
        (
            "config set A=1 B=2 --app x",
            {
                "command": "config",
                "subcommand": "set",
                "vars": ["A=1", "B=2"],
                "app": "x",
            },
        ),
        (
            "config unset MY_VAR --app x",
            {
                "command": "config",
                "subcommand": "unset",
                "keys": ["MY_VAR"],
                "app": "x",
            },
        ),
        (
            "config get DB_HOST --app x",
            {"command": "config", "subcommand": "get", "key": "DB_HOST", "app": "x"},
        ),
        (
            "secrets set S1=abc S2=- --app x",
            {
                "command": "secrets",
                "subcommand": "set",
                "vars": ["S1=abc", "S2=-"],
                "app": "x",
            },
        ),
        # Logs/Status
        (
            "logs -f --app x --lines 100",
            {
                "command": "logs",
                "follow": True,
                "app": "x",
                "lines": 100,
                "instance": None,
                "type": None,
            },
        ),
        ("status --app x --env y", {"command": "status", "app": "x", "env": "y"}),
        # Services (Basic)
        (
            "services list --app x",
            {"command": "services", "subcommand": "list", "app": "x"},
        ),
        (
            "services create postgres my-db --app x --plan large",
            {
                "command": "services",
                "subcommand": "create",
                "service_type": "postgres",
                "service_name": "my-db",
                "app": "x",
                "plan": "large",
            },
        ),
        (
            "services info main-db --app x",
            {
                "command": "services",
                "subcommand": "info",
                "service_name": ["main-db"],
                "app": "x",
            },
        ),
        # Note: name becomes a list due to nargs=1
        (
            "services attach shared-cache --app x --as REDIS",
            {
                "command": "services",
                "subcommand": "attach",
                "service_name": "shared-cache",
                "app": "x",
                "as": "REDIS",
            },
        ),
        # PG (Nested)
        ("pg list --app x", {"command": "pg", "subcommand": "list", "app": "x"}),
        (
            "pg connect",
            {"command": "pg", "subcommand": "connect", "service_name": None},
        ),  # Optional service name
        (
            "pg connect my-pg-db --app x",
            {
                "command": "pg",
                "subcommand": "connect",
                "service_name": "my-pg-db",
                "app": "x",
            },
        ),
        (
            "pg backup list --app x",
            {
                "command": "pg",
                "subcommand": "backup",
                "backup_subcommand": "list",
                "app": "x",
                "service_name": None,
            },
        ),
        (
            "pg backup restore bk-123 my-db --app x",
            {
                "command": "pg",
                "subcommand": "backup",
                "backup_subcommand": "restore",
                "backup_id": "bk-123",
                "service_name": "my-db",
                "app": "x",
            },
        ),
        # Redis
        (
            "redis cli --app x",
            {"command": "redis", "subcommand": "cli", "app": "x", "service_name": None},
        ),
        # Marketplace
        (
            "marketplace search cache",
            {"command": "marketplace", "subcommand": "search", "query": "cache"},
        ),
        (
            "marketplace info wordpress",
            {
                "command": "marketplace",
                "subcommand": "info",
                "template_name": "wordpress",
            },
        ),
        # Domains/Certs/IPs
        (
            "domains list --app x",
            {"command": "domains", "subcommand": "list", "app": "x"},
        ),
        (
            "domains add www.example.com --app x",
            {
                "command": "domains",
                "subcommand": "add",
                "domain_name": "www.example.com",
                "app": "x",
            },
        ),
        (
            "certs add --domain abc.com --app x",
            {"command": "certs", "subcommand": "add", "domain": "abc.com", "app": "x"},
        ),
        (
            "ips list",
            {"command": "ips", "subcommand": "list", "app": None, "env": None},
        ),
        (
            "ips allocate --type ipv6",
            {
                "command": "ips",
                "subcommand": "allocate",
                "type": "ipv6",
                "region": None,
            },
        ),
        (
            "ips release 1.2.3.4",
            {"command": "ips", "subcommand": "release", "ip_address": "1.2.3.4"},
        ),
        # Utility
        ("doctor", {"command": "doctor"}),
        ("update", {"command": "update"}),
    ],
)
def test_command_parsing(parser, cmd_str, expected_attrs):
    """Test parsing various valid command combinations."""
    args = parser.parse_args(cmd_str.split())
    for attr, expected_value in expected_attrs.items():
        assert hasattr(args, attr), (
            f"Attribute '{attr}' not found in parsed args for '{cmd_str}'"
        )
        assert getattr(args, attr) == expected_value, (
            f"Attribute '{attr}' has wrong value for '{cmd_str}'"
        )


# --- Tests for REMAINDER ---


@pytest.mark.parametrize(
    ("cmd_str", "expected_target, expected_command_list"),
    [
        (
            "instances exec my-inst -- ls -la /app",
            "my-inst",
            ["ls", "-la", "/app"],
        ),
        (
            "instances exec --app x --env y --select -- bash -c 'echo hello'",
            None,
            ["bash", "-c", "echo hello"],
        ),
        (
            "instances ssh my-inst",
            "my-inst",
            [],
        ),  # No remainder command
        (
            "instances ssh my-inst uptime",
            "my-inst",
            ["uptime"],
        ),
        (
            "dev exec -- pytest -k mytest",
            None,
            ["pytest", "-k", "mytest"],
        ),
    ],
)
def test_remainder_parsing(parser, cmd_str, expected_target, expected_command_list):
    """Test commands that use argparse.REMAINDER."""
    args = parser.parse_args(cmd_str.split())
    remainder_attr = None
    if args.command == "instances" and args.subcommand == "exec":
        remainder_attr = "exec_command"
        assert args.target == expected_target
    elif args.command == "instances" and args.subcommand == "ssh":
        remainder_attr = "ssh_command"
        assert args.target == expected_target
    elif args.command == "dev" and args.subcommand == "exec":
        remainder_attr = "exec_command"
    else:
        pytest.fail(f"Unhandled command structure in remainder test: {cmd_str}")

    assert hasattr(args, remainder_attr)
    assert getattr(args, remainder_attr) == expected_command_list


# --- Tests for Parsing Errors ---


@pytest.mark.parametrize(
    ("cmd_list", "error_fragment"),  # Part of the expected error message
    [
        (
            ["apps", "create"],
            "the following arguments are required: app_name",
        ),
        (
            ["instances", "restart"],
            "the following arguments are required: target/--app",
        ),  # Simplified check
        (
            ["config", "set", "--app", "x"],
            "the following arguments are required: vars",
        ),
        (
            ["ips", "allocate", "--type", "invalid"],
            "invalid choice: 'invalid'",
        ),
        (
            ["services", "info"],
            "the following arguments are required: service_name",
        ),  # Required positional
        (
            ["certs", "remove", "--app", "x"],
            "one of the arguments --domain --cert-id is required",
        ),
        # Our simplified check for the non-ideal declarative mutually exclusive
    ],
)
def test_parsing_errors(parser, cmd_list, error_fragment, capsys):
    """Test commands that should result in parsing errors (SystemExit != 0)."""
    with pytest.raises(SystemExit) as e:
        parser.parse_args(cmd_list)
    assert e.value.code != 0
    # Capture stderr and check if the error message contains the expected fragment
    captured = capsys.readouterr()
    assert error_fragment in captured.err


# --- Test Argument Group Resolution (Indirectly) ---
# These tests implicitly check if ARG_GROUPS were resolved correctly
# by verifying that commands using them parse the expected arguments.


def test_arg_group_context(parser):
    """Test a command relying heavily on the 'context' ARG_GROUP."""
    args = parser.parse_args(["logs", "--app", "myapp", "--env", "prod", "-f"])
    assert args.command == "logs"
    assert args.app == "myapp"
    assert args.env == "prod"
    assert args.follow is True


def test_arg_group_target_instance(parser):
    """Test a command using the 'target_instance' ARG_GROUP."""
    # By ID
    args = parser.parse_args(["instances", "restart", "i-abcdef"])
    assert args.command == "instances"
    assert args.subcommand == "restart"
    assert args.target == "i-abcdef"
    assert args.app is None
    assert args.env is None
    # By context
    args = parser.parse_args([
        "instances",
        "restart",
        "--app",
        "myapp",
        "--env",
        "staging",
    ])
    assert args.command == "instances"
    assert args.subcommand == "restart"
    assert args.target is None
    assert args.app == "myapp"
    assert args.env == "staging"


def test_arg_group_service_context(parser):
    """Test a command using the 'service_context' ARG_GROUP."""
    # Optional name provided
    args = parser.parse_args(["pg", "connect", "my-db", "--app", "x", "--env", "y"])
    assert args.command == "pg"
    assert args.subcommand == "connect"
    assert args.service_name == "my-db"
    assert args.app == "x"
    assert args.env == "y"

    # Optional name omitted
    args = parser.parse_args(["pg", "connect", "--app", "x"])
    assert args.command == "pg"
    assert args.subcommand == "connect"
    assert args.service_name is None
    assert args.app == "x"
    assert args.env is None
