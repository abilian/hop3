from __future__ import annotations

import argparse

APP_VERSION = "0.1.0-dev"

# Define common sets of arguments to avoid repetition

ARG_GROUPS = {
    "context": [
        {
            "flags": ["--app"],
            "metavar": "APP_NAME",
            "help": "Specify the application name (defaults to linked app).",
            # 'required' will be set dynamically where needed
        },
        {
            "flags": ["--env"],
            "metavar": "ENV_NAME",
            "help": "Specify the environment name (defaults to default env).",
            # 'required' will be set dynamically where needed
        },
    ],
    "instance_optional": [
        {
            "flags": ["--instance"],
            "metavar": "INSTANCE_ID",
            "help": "Specify a specific instance ID.",
        }
    ],
    "target_instance": [
        {
            "name": "target",  # Positional
            "nargs": "?",
            "metavar": "INSTANCE_ID",
            # Help text will be customized where used
        },
        # Include context args as optional ways to specify
        # Special syntax: embed the 'context' group
        *["context"],
    ],
    "service_context": [
        {
            "name": "service_name",
            # Positional 'nargs' and 'required' status customized where used
            "metavar": "SERVICE_NAME",
            # Help text customized where used
        },
        *["context"],  # Embed app/env context
    ],
}

# --- Main CLI Definition ---

CLI_CONFIG = {
    "prog": "hop3",
    "description": "Command Line Interface for the Hop3 Platform.",
    "epilog": "Run 'hop3 <command> --help' for more information on a specific command.",
    # Global options
    "arguments": [
        {
            "flags": ["--version"],
            "action": "version",
            "version": f"%(prog)s {APP_VERSION}",
        },
        {
            "flags": ["-v", "--verbose"],
            "action": "count",
            "default": 0,
            "help": "Increase output verbosity (-v, -vv, -vvv).",
        },
        {
            "flags": ["--json"],
            "action": "store_true",
            "help": "Output results in JSON format.",
        },
        {
            "flags": ["-y", "--non-interactive"],
            "action": "store_true",
            "help": "Assume 'yes' to all prompts; disable interactive features.",
        },
        {
            "flags": ["--api-url"],
            "metavar": "URL",
            "help": "Override the default Hop3 API server URL.",
        },
    ],
    # Options for the main subparser group
    "subparser_options": {
        "dest": "command",
        "title": "Available Commands",
        "metavar": "<command>",
        "help": "Use 'hop3 <command> --help' for details",
        "required": True,
    },
    "subcommands": [
        # --- Auth ---
        {
            "name": "auth",
            "help": "Manage authentication and login status.",
            "subparser_options": {
                "dest": "subcommand",
                "title": "Auth Commands",
                "required": True,
                "metavar": "<subcommand>",
            },
            "subcommands": [
                {
                    "name": "login",
                    "help": "Log in to a Hop3 server.",
                    "arguments": [
                        {
                            "flags": ["--token"],
                            "metavar": "API_TOKEN",
                            "help": "Log in using an API token directly.",
                        },
                        {
                            "flags": ["--sso"],
                            "metavar": "PROVIDER",
                            "help": "Log in via a specific SSO provider.",
                        },
                    ],
                },
                {"name": "logout", "help": "Log out and clear local credentials."},
                {
                    "name": "status",
                    "help": "Display current logged-in user and server info.",
                },
                {"name": "whoami", "help": "Alias for 'auth status'."},  # Common alias
            ],
        },
        # --- Link / Unlink / Init (Top Level Actions) ---
        {
            "name": "link",
            "help": "Associate the current directory with an existing Hop3 application.",
            "arguments": [
                {
                    "name": "app_name",
                    "metavar": "APP_NAME",
                    "help": "The name of the application to link.",
                },
                {
                    "flags": ["--org"],
                    "metavar": "ORG_NAME",
                    "help": "Specify the organization owner of the application.",
                },
            ],
        },
        {
            "name": "unlink",
            "help": "Remove the Hop3 application association from the current directory.",
        },
        {
            "name": "init",
            "help": "Initialize a new Hop3 project in the current directory.",
            "arguments": [
                {
                    "flags": ["--template"],
                    "metavar": "TEMPLATE_NAME",
                    "help": "Initialize from a specific template.",
                },
                {
                    "flags": ["--from-git"],
                    "metavar": "REPO_URL",
                    "help": "Initialize by cloning a git repository.",
                },
                {
                    "flags": ["--name"],
                    "metavar": "APP_NAME",
                    "help": "Specify the application name during initialization.",
                },
                {
                    "flags": ["--org"],
                    "metavar": "ORG_NAME",
                    "help": "Specify the organization for the new application.",
                },
            ],
        },
        # --- Apps ---
        {
            "name": "apps",
            "help": "Manage application definitions.",
            "subparser_options": {
                "dest": "subcommand",
                "title": "Apps Commands",
                "required": True,
                "metavar": "<subcommand>",
            },
            "subcommands": [
                {
                    "name": "list",
                    "help": "List applications you have access to.",
                    "arguments": [
                        {
                            "flags": ["--org"],
                            "metavar": "ORG_NAME",
                            "help": "Filter applications by organization.",
                        }
                    ],
                },
                {
                    "name": "create",
                    "help": "Create a new application definition.",
                    "arguments": [
                        {
                            "name": "app_name",
                            "metavar": "APP_NAME",
                            "help": "The name for the new application.",
                        },
                        {
                            "flags": ["--org"],
                            "metavar": "ORG_NAME",
                            "help": "Specify the organization for the new application.",
                        },
                        {
                            "flags": ["--region"],
                            "metavar": "REGION_ID",
                            "help": "Specify the region for the application.",
                        },
                    ],
                },
                {
                    "name": "info",
                    "help": "Show detailed information about an application.",
                    "arguments": [
                        {
                            "name": "app_name",
                            "nargs": "?",
                            "metavar": "APP_NAME",
                            "help": "The name of the application (defaults to linked app).",
                        }
                    ],
                },
                {
                    "name": "delete",
                    "help": "Delete an application definition (irreversible).",
                    "arguments": [
                        {
                            "name": "app_name",
                            "metavar": "APP_NAME",
                            "help": "The name of the application to delete.",
                        }
                    ],
                },
                {
                    "name": "open",
                    "help": "Open the application's dashboard in a web browser.",
                    "arguments": [
                        {
                            "name": "app_name",
                            "nargs": "?",
                            "metavar": "APP_NAME",
                            "help": "The name of the application (defaults to linked app).",
                        }
                    ],
                },
            ],
        },
        # --- Instances ---
        {
            "name": "instances",
            "help": "Manage running instances of applications.",
            "subparser_options": {
                "dest": "subcommand",
                "title": "Instances Commands",
                "required": True,
                "metavar": "<subcommand>",
            },
            "subcommands": [
                {
                    "name": "list",
                    "help": "List running instances.",
                    "arguments": [*ARG_GROUPS["context"]],  # Use shorthand
                },
                {
                    "name": "info",
                    "help": "Show detailed info about a specific instance.",
                    "arguments": [
                        {
                            "name": "instance_id",
                            "metavar": "INSTANCE_ID",
                            "help": "The ID of the instance.",
                        }
                    ],
                },
                {
                    "name": "restart",
                    "help": "Restart instance(s).",
                    "arguments": [
                        # Customize help for the 'target' argument
                        {
                            **ARG_GROUPS["target_instance"][0],
                            "help": "The ID of the instance to restart. If omitted, requires --app and --env.",
                        },
                        *ARG_GROUPS["target_instance"][1:],  # Include context args
                        {
                            "flags": ["--type"],
                            "metavar": "PROCESS_TYPE",
                            "help": "Restart only instances of a specific process type (e.g., 'web', 'worker').",
                        },
                    ],
                },
                {
                    "name": "stop",
                    "help": "Stop instance(s) (scale to zero or pause).",
                    "arguments": [
                        {
                            **ARG_GROUPS["target_instance"][0],
                            "help": "The ID of the instance to stop. If omitted, requires --app and --env.",
                        },
                        *ARG_GROUPS["target_instance"][1:],
                    ],
                },
                {
                    "name": "start",
                    "help": "Start stopped instance(s).",
                    "arguments": [
                        {
                            **ARG_GROUPS["target_instance"][0],
                            "help": "The ID of the instance to start. If omitted, requires --app and --env.",
                        },
                        *ARG_GROUPS["target_instance"][1:],
                    ],
                },
                {
                    "name": "destroy",
                    "help": "Permanently destroy instance(s) and ephemeral data.",
                    "arguments": [
                        {
                            **ARG_GROUPS["target_instance"][0],
                            "help": "The ID of the instance to destroy. If omitted, requires --app and --env.",
                        },
                        *ARG_GROUPS["target_instance"][1:],
                    ],
                },
                {
                    "name": "ssh",
                    "help": "SSH into a running instance.",
                    "arguments": [
                        {
                            "name": "target",
                            "nargs": "?",
                            "metavar": "INSTANCE_ID",
                            "help": "The ID of the instance to SSH into. If omitted, uses --app/--env and may prompt.",
                        },
                        *ARG_GROUPS["context"],
                        {
                            "flags": ["--select"],
                            "action": "store_true",
                            "help": "Prompt to select instance if multiple match.",
                        },
                        {
                            "name": "ssh_command",
                            "nargs": argparse.REMAINDER,
                            "metavar": "COMMAND",
                            "help": "Optional command to run directly via SSH.",
                        },
                    ],
                },
                {
                    "name": "exec",
                    "help": "Execute a one-off command inside a running instance.",
                    "arguments": [
                        {
                            "name": "target",
                            "nargs": "?",
                            "metavar": "INSTANCE_ID",
                            "help": "The ID of the instance to execute in. If omitted, uses --app/--env and may prompt.",
                        },
                        *ARG_GROUPS["context"],
                        {
                            "flags": ["--select"],
                            "action": "store_true",
                            "help": "Prompt to select instance if multiple match.",
                        },
                        {
                            "name": "exec_command",
                            "nargs": argparse.REMAINDER,
                            "metavar": "COMMAND [ARGS...]",
                            "help": "The command and arguments to execute.",
                        },
                    ],
                },
            ],
        },
        # --- Scale ---
        {
            "name": "scale",
            "help": "Manage application instance scaling.",
            "subparser_options": {
                "dest": "subcommand",
                "title": "Scale Commands",
                "required": True,
                "metavar": "<subcommand>",
            },
            "subcommands": [
                {
                    "name": "set",
                    "help": "Set instance counts for process types.",
                    "arguments": [
                        {
                            "name": "scale_args",
                            "nargs": "+",
                            "metavar": "TYPE=COUNT",
                            "help": "One or more process type scaling arguments (e.g., web=3 worker=1).",
                        },
                        # Customize target help
                        {
                            **ARG_GROUPS["target_instance"][0],
                            "help": "Optional instance ID (usually scaling is per app/env).",
                        },
                        *ARG_GROUPS["target_instance"][1:],
                    ],
                },
                {
                    "name": "show",
                    "help": "Display current scaling settings.",
                    "arguments": [
                        {
                            **ARG_GROUPS["target_instance"][0],
                            "help": "Optional instance ID.",
                        },
                        *ARG_GROUPS["target_instance"][1:],
                    ],
                },
            ],
        },
        # --- Build ---
        {
            "name": "build",
            "help": "Build the application artifact (e.g., Docker image).",
            "arguments": [
                {
                    "flags": ["--tag"],
                    "metavar": "TAG",
                    "help": "Tag for the built artifact (e.g., image tag).",
                },
                {
                    "flags": ["--push"],
                    "action": "store_true",
                    "help": "Push the artifact to the registry after building.",
                },
                {
                    "flags": ["--builder"],
                    "metavar": "BUILDER_NAME",
                    "help": "Specify a specific builder (e.g., buildpack builder).",
                },
            ],
        },
        # --- Dev ---
        {
            "name": "dev",
            "help": "Run and manage the application locally.",
            "subparser_options": {
                "dest": "subcommand",
                "title": "Dev Commands",
                "required": True,
                "metavar": "<subcommand>",
            },
            "subcommands": [
                {
                    "name": "run",
                    "help": "Run the application locally (like production).",
                    "arguments": [
                        {
                            "name": "process_type",
                            "nargs": "?",
                            "metavar": "PROCESS_TYPE",
                            "help": "Specify a process type to run (defaults to web or as defined).",
                        }
                    ],
                },
                {
                    "name": "exec",
                    "help": "Run a one-off command in the local dev environment.",
                    "arguments": [
                        {
                            "name": "exec_command",
                            "nargs": argparse.REMAINDER,
                            "metavar": "COMMAND [ARGS...]",
                            "help": "The command and arguments to execute locally.",
                        }
                    ],
                },
            ],
        },
        # --- Deploy ---
        {
            "name": "deploy",
            "help": "Deploy the application to a Hop3 environment.",
            "arguments": [
                {
                    "name": "source",
                    "nargs": "?",
                    "metavar": "SOURCE",
                    "help": "Source to deploy (e.g., git ref, local path). Defaults to current directory.",
                },
                *ARG_GROUPS["context"],  # App/Env context is important
                {
                    "flags": ["--image"],
                    "metavar": "IMAGE_NAME",
                    "help": "Deploy a specific pre-built image instead of building.",
                },
                {
                    "flags": ["-m", "--message"],
                    "metavar": "MSG",
                    "help": "Add a message to the deployment/release.",
                },
            ],
        },
        # --- Releases ---
        {
            "name": "releases",
            "help": "Manage application deployments (releases).",
            "subparser_options": {
                "dest": "subcommand",
                "title": "Releases Commands",
                "required": True,
                "metavar": "<subcommand>",
            },
            "subcommands": [
                {
                    "name": "list",
                    "help": "List past deployments/releases.",
                    "arguments": [*ARG_GROUPS["context"]],
                },
                {
                    "name": "info",
                    "help": "Show details about a specific release.",
                    "arguments": [
                        {
                            "name": "release_id",
                            "metavar": "RELEASE_ID",
                            "help": "The ID of the release.",
                        },
                        *ARG_GROUPS["context"],
                    ],
                },
                {
                    "name": "rollback",
                    "help": "Rollback to a previous release.",
                    "arguments": [
                        {
                            "name": "release_id",
                            "nargs": "?",
                            "metavar": "RELEASE_ID",
                            "help": "The ID of the release to roll back to (defaults to the previous one).",
                        },
                        *ARG_GROUPS["context"],
                    ],
                },
            ],
        },
        # --- Config ---
        {
            "name": "config",
            "help": "Manage application environment variables.",
            "subparser_options": {
                "dest": "subcommand",
                "title": "Config Commands",
                "required": True,
                "metavar": "<subcommand>",
            },
            "subcommands": [
                {
                    "name": "list",
                    "help": "List environment variables (excludes secrets).",
                    "arguments": [*ARG_GROUPS["context"]],
                },
                {
                    "name": "set",
                    "help": "Set one or more environment variables.",
                    "arguments": [
                        {
                            "name": "vars",
                            "nargs": "+",
                            "metavar": "KEY=VALUE",
                            "help": "Variable(s) to set.",
                        },
                        *ARG_GROUPS["context"],
                    ],
                },
                {
                    "name": "unset",
                    "help": "Unset one or more environment variables.",
                    "arguments": [
                        {
                            "name": "keys",
                            "nargs": "+",
                            "metavar": "KEY",
                            "help": "Variable key(s) to unset.",
                        },
                        *ARG_GROUPS["context"],
                    ],
                },
                {
                    "name": "get",
                    "help": "Get the value of a single environment variable.",
                    "arguments": [
                        {
                            "name": "key",
                            "metavar": "KEY",
                            "help": "The variable key to get.",
                        },
                        *ARG_GROUPS["context"],
                    ],
                },
            ],
        },
        # --- Secrets ---
        {
            "name": "secrets",
            "help": "Manage application secrets (sensitive environment variables).",
            "subparser_options": {
                "dest": "subcommand",
                "title": "Secrets Commands",
                "required": True,
                "metavar": "<subcommand>",
            },
            "subcommands": [
                {
                    "name": "list",
                    "help": "List secret keys (values are masked).",
                    "arguments": [*ARG_GROUPS["context"]],
                },
                {
                    "name": "set",
                    "help": "Set one or more secrets. Use '-' for VALUE to read from stdin.",
                    "arguments": [
                        {
                            "name": "vars",
                            "nargs": "+",
                            "metavar": "KEY=VALUE",
                            "help": "Secret(s) to set (e.g., SECRET_KEY=myvalue SECRET_TOKEN=-).",
                        },
                        *ARG_GROUPS["context"],
                    ],
                },
                {
                    "name": "unset",
                    "help": "Unset one or more secrets.",
                    "arguments": [
                        {
                            "name": "keys",
                            "nargs": "+",
                            "metavar": "KEY",
                            "help": "Secret key(s) to unset.",
                        },
                        *ARG_GROUPS["context"],
                    ],
                },
                {
                    "name": "reveal",
                    "help": "Show the value of a secret (use with caution!).",
                    "arguments": [
                        {
                            "name": "key",
                            "metavar": "KEY",
                            "help": "The secret key to reveal.",
                        },
                        *ARG_GROUPS["context"],
                    ],
                },
            ],
        },
        # --- Logs ---
        {
            "name": "logs",
            "help": "View or stream application logs.",
            "arguments": [
                *ARG_GROUPS["context"],
                *ARG_GROUPS["instance_optional"],
                {
                    "flags": ["-f", "--follow"],
                    "action": "store_true",
                    "help": "Follow log output (stream).",
                },
                {
                    "flags": ["-n", "--lines"],
                    "type": int,
                    "metavar": "NUM",
                    "help": "Number of lines to show.",
                },
                {
                    "flags": ["--type"],
                    "metavar": "PROCESS_TYPE",
                    "help": "Filter logs by process type (e.g., 'web', 'worker').",
                },
            ],
        },
        # --- Status ---
        {
            "name": "status",
            "help": "Show the overall status of an application/environment.",
            "arguments": [*ARG_GROUPS["context"]],
        },
        # --- Services ---
        {
            "name": "services",
            "help": "Manage backing services (addons).",
            "subparser_options": {
                "dest": "subcommand",
                "title": "Services Commands",
                "required": True,
                "metavar": "<subcommand>",
            },
            "subcommands": [
                {
                    "name": "list",
                    "help": "List attached services.",
                    "arguments": [*ARG_GROUPS["context"]],
                },
                {
                    "name": "create",
                    "help": "Provision a new service.",
                    "arguments": [
                        {
                            "name": "service_type",
                            "metavar": "TYPE",
                            "help": "Type of service to create (e.g., postgres, redis, marketplace:...).",
                        },
                        {
                            "name": "service_name",
                            "metavar": "NAME",
                            "help": "Name for the new service instance.",
                        },
                        *ARG_GROUPS["context"],
                        {
                            "flags": ["--plan"],
                            "metavar": "PLAN_NAME",
                            "help": "Specify the service plan (size/tier).",
                        },
                        {
                            "flags": ["--region"],
                            "metavar": "REGION_ID",
                            "help": "Specify the region for the service.",
                        },
                    ],
                },
                {
                    "name": "info",
                    "help": "Show details about a service.",
                    "arguments": [
                        {
                            **ARG_GROUPS["service_context"][0],
                            "nargs": 1,
                            "help": "Specify the service name (required).",
                        },  # service_name required
                        *ARG_GROUPS["service_context"][1:],  # context args
                    ],
                },
                {
                    "name": "delete",
                    "help": "Delete a service instance (irreversible).",
                    "arguments": [
                        {
                            **ARG_GROUPS["service_context"][0],
                            "nargs": 1,
                            "help": "Specify the service name (required).",
                        },
                        *ARG_GROUPS["service_context"][1:],
                    ],
                },
                {
                    "name": "attach",
                    "help": "Attach an existing service to an app/environment.",
                    "arguments": [
                        {
                            "name": "service_name",
                            "metavar": "SERVICE_NAME",
                            "help": "Name of the service to attach.",
                        },
                        # Need --app specifically required here
                        {
                            **ARG_GROUPS["context"][0],
                            "required": True,
                            "help": "Specify the application name (required).",
                        },
                        ARG_GROUPS["context"][1],  # --env optional
                        {
                            "flags": ["--as"],
                            "metavar": "ALIAS",
                            "help": "Attach the service under a specific alias/prefix.",
                        },
                    ],
                },
                {
                    "name": "detach",
                    "help": "Detach a service from an app/environment.",
                    "arguments": [
                        {
                            "name": "service_name",
                            "metavar": "SERVICE_NAME",
                            "help": "Name of the service to detach.",
                        },
                        # Need --app specifically required here
                        {
                            **ARG_GROUPS["context"][0],
                            "required": True,
                            "help": "Specify the application name (required).",
                        },
                        ARG_GROUPS["context"][1],  # --env optional
                    ],
                },
            ],
        },
        # --- Service-Specific Commands (Example: Postgres) ---
        {
            "name": "pg",
            "help": "Manage Postgres services.",
            "subparser_options": {
                "dest": "subcommand",
                "title": "Postgres Commands",
                "required": True,
                "metavar": "<subcommand>",
            },
            "subcommands": [
                {
                    "name": "list",
                    "help": "List Postgres services for the context.",
                    "arguments": [*ARG_GROUPS["context"]],
                },
                {
                    "name": "connect",
                    "help": "Open a psql shell to the database.",
                    "arguments": [
                        {
                            **ARG_GROUPS["service_context"][0],
                            "nargs": "?",
                            "help": "Specify the service name (inferred if only one exists for the context).",
                        },
                        *ARG_GROUPS["service_context"][1:],
                    ],
                },
                {
                    "name": "info",
                    "help": "Show connection info for the database.",
                    "arguments": [
                        {
                            **ARG_GROUPS["service_context"][0],
                            "nargs": "?",
                            "help": "Specify the service name (inferred if only one exists for the context).",
                        },
                        *ARG_GROUPS["service_context"][1:],
                    ],
                },
                {
                    "name": "credentials",
                    "help": "Show database credentials.",
                    "arguments": [
                        {
                            **ARG_GROUPS["service_context"][0],
                            "nargs": "?",
                            "help": "Specify the service name (inferred if only one exists for the context).",
                        },
                        *ARG_GROUPS["service_context"][1:],
                    ],
                },
                {
                    "name": "promote",
                    "help": "Promote a follower/replica database (if applicable).",
                    "arguments": [
                        {
                            **ARG_GROUPS["service_context"][0],
                            "nargs": 1,
                            "help": "Specify the service name (required).",
                        },
                        *ARG_GROUPS["service_context"][1:],
                    ],
                },
                # --- Nested PG Backup ---
                {
                    "name": "backup",
                    "help": "Manage Postgres backups.",
                    "subparser_options": {
                        "dest": "backup_subcommand",
                        "title": "Backup Commands",
                        "required": True,
                        "metavar": "<subcommand>",
                    },
                    "subcommands": [
                        {
                            "name": "create",
                            "help": "Create a new database backup.",
                            "arguments": [
                                {
                                    **ARG_GROUPS["service_context"][0],
                                    "nargs": "?",
                                    "help": "Specify the service name (inferred if only one exists for the context).",
                                },
                                *ARG_GROUPS["service_context"][1:],
                                # Add backup-specific args if needed, e.g., --name
                            ],
                        },
                        {
                            "name": "list",
                            "help": "List available database backups.",
                            "arguments": [
                                {
                                    **ARG_GROUPS["service_context"][0],
                                    "nargs": "?",
                                    "help": "Specify the service name (inferred if only one exists for the context).",
                                },
                                *ARG_GROUPS["service_context"][1:],
                            ],
                        },
                        {
                            "name": "restore",
                            "help": "Restore a database from a backup.",
                            "arguments": [
                                {
                                    "name": "backup_id",
                                    "metavar": "BACKUP_ID",
                                    "help": "The ID of the backup to restore.",
                                },
                                {
                                    **ARG_GROUPS["service_context"][0],
                                    "nargs": "?",
                                    "help": "Specify the service name (inferred if only one exists for the context).",
                                },
                                *ARG_GROUPS["service_context"][1:],
                                # Add restore-specific args if needed, e.g., --target-service
                            ],
                        },
                    ],
                },
            ],
        },
        # --- Service-Specific Commands (Example: Redis) ---
        {
            "name": "redis",
            "help": "Manage Redis services.",
            "subparser_options": {
                "dest": "subcommand",
                "title": "Redis Commands",
                "required": True,
                "metavar": "<subcommand>",
            },
            "subcommands": [
                {
                    "name": "list",
                    "help": "List Redis services for the context.",
                    "arguments": [*ARG_GROUPS["context"]],
                },
                {
                    "name": "cli",
                    "help": "Open a redis-cli shell to the service.",
                    "arguments": [
                        {
                            **ARG_GROUPS["service_context"][0],
                            "nargs": "?",
                            "help": "Specify the service name (inferred if only one exists for the context).",
                        },
                        *ARG_GROUPS["service_context"][1:],
                    ],
                },
                {
                    "name": "info",
                    "help": "Show connection info for the Redis service.",
                    "arguments": [
                        {
                            **ARG_GROUPS["service_context"][0],
                            "nargs": "?",
                            "help": "Specify the service name (inferred if only one exists for the context).",
                        },
                        *ARG_GROUPS["service_context"][1:],
                    ],
                },
                # Add other redis commands as needed
            ],
        },
        # --- Marketplace ---
        {
            "name": "marketplace",
            "help": "Discover apps and services in the Hop3 Marketplace.",
            "subparser_options": {
                "dest": "subcommand",
                "title": "Marketplace Commands",
                "required": True,
                "metavar": "<subcommand>",
            },
            "subcommands": [
                {
                    "name": "search",
                    "help": "Search the marketplace.",
                    "arguments": [
                        {"name": "query", "metavar": "QUERY", "help": "Search term(s)."}
                    ],
                },
                {
                    "name": "info",
                    "help": "Show details about a marketplace item.",
                    "arguments": [
                        {
                            "name": "template_name",
                            "metavar": "TEMPLATE_NAME",
                            "help": "Name of the marketplace app or service template.",
                        }
                    ],
                },
                {"name": "list", "help": "List available marketplace items."},
            ],
        },
        # --- Domains ---
        {
            "name": "domains",
            "help": "Manage custom domains for applications.",
            "subparser_options": {
                "dest": "subcommand",
                "title": "Domains Commands",
                "required": True,
                "metavar": "<subcommand>",
            },
            "subcommands": [
                {
                    "name": "list",
                    "help": "List custom domains.",
                    "arguments": [*ARG_GROUPS["context"]],
                },
                {
                    "name": "add",
                    "help": "Add a custom domain to an application environment.",
                    "arguments": [
                        {
                            "name": "domain_name",
                            "metavar": "DOMAIN_NAME",
                            "help": "The domain name to add (e.g., www.example.com).",
                        },
                        *ARG_GROUPS["context"],
                    ],
                },
                {
                    "name": "remove",
                    "help": "Remove a custom domain.",
                    "arguments": [
                        {
                            "name": "domain_name",
                            "metavar": "DOMAIN_NAME",
                            "help": "The domain name to remove.",
                        },
                        *ARG_GROUPS["context"],
                    ],
                },
            ],
        },
        # --- Certs ---
        {
            "name": "certs",
            "help": "Manage SSL/TLS certificates.",
            "subparser_options": {
                "dest": "subcommand",
                "title": "Certificates Commands",
                "required": True,
                "metavar": "<subcommand>",
            },
            "subcommands": [
                {
                    "name": "list",
                    "help": "List SSL/TLS certificates.",
                    "arguments": [*ARG_GROUPS["context"]],
                },
                {
                    "name": "add",
                    "help": "Add/provision an SSL/TLS certificate for a domain.",
                    "arguments": [
                        {
                            "flags": ["--domain"],
                            "metavar": "DOMAIN_NAME",
                            "required": True,
                            "help": "The domain name the certificate is for.",
                        },
                        *ARG_GROUPS["context"],
                        # Add args for custom cert upload if needed (--cert-file, --key-file)
                    ],
                },
                {
                    "name": "remove",
                    "help": "Remove an SSL/TLS certificate.",
                    "arguments": [
                        # Mutually exclusive group not directly supported declaratively,
                        # would need logic in the builder or post-parsing validation.
                        # For simplicity here, we list both options.
                        {
                            "flags": ["--domain"],
                            "metavar": "DOMAIN_NAME",
                            "help": "Remove the certificate associated with this domain.",
                        },
                        {
                            "flags": ["--cert-id"],
                            "metavar": "CERT_ID",
                            "help": "Remove the certificate by its ID.",
                        },
                        *ARG_GROUPS["context"],
                    ],
                    # Need validation: exactly one of --domain or --cert-id must be provided.
                },
            ],
        },
        # --- IPs ---
        {
            "name": "ips",
            "help": "Manage dedicated IP addresses.",
            "subparser_options": {
                "dest": "subcommand",
                "title": "IP Commands",
                "required": True,
                "metavar": "<subcommand>",
            },
            "subcommands": [
                {
                    "name": "list",
                    "help": "List IP addresses associated with the app/env or organization.",
                    "arguments": [
                        *ARG_GROUPS["context"]
                        # Maybe add --org flag here too
                    ],
                },
                {
                    "name": "allocate",
                    "help": "Allocate a new dedicated IP address.",
                    "arguments": [
                        {
                            "flags": ["--type"],
                            "choices": ["ipv4", "ipv6"],
                            "default": "ipv4",
                            "help": "Type of IP address to allocate.",
                        },
                        {
                            "flags": ["--region"],
                            "metavar": "REGION_ID",
                            "help": "Allocate IP in a specific region (if applicable).",
                        },
                        # Maybe add --app/--env to associate directly
                    ],
                },
                {
                    "name": "release",
                    "help": "Release a dedicated IP address.",
                    "arguments": [
                        {
                            "name": "ip_address",
                            "metavar": "IP_ADDRESS",
                            "help": "The IP address to release.",
                        }
                    ],
                },
            ],
        },
        # --- System / Utility ---
        {"name": "update", "help": "Check for and install updates to the Hop3 CLI."},
        {
            "name": "doctor",
            "help": "Run diagnostic checks for CLI setup and connectivity.",
        },
    ],  # end top-level subcommands
}
