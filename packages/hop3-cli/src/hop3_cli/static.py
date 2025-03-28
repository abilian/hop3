from __future__ import annotations

import argparse

# --- Constants ---
APP_VERSION = "0.1.0-dev"

# --- Helper Functions ---


def _add_context_args(
    parser, app_required=False, env_required=False, instance_optional=False
):
    """Adds common arguments for application/environment context."""
    parser.add_argument(
        "--app",
        metavar="APP_NAME",
        help=f"Specify the application name{' (required)' if app_required else ' (defaults to linked app)'}.",
        required=app_required,
    )
    parser.add_argument(
        "--env",
        metavar="ENV_NAME",
        help=f"Specify the environment name{' (required)' if env_required else ' (defaults to default env)'}.",
        required=env_required,
    )
    if instance_optional:
        parser.add_argument(
            "--instance",
            metavar="INSTANCE_ID",
            help="Specify a specific instance ID.",
        )


def _add_target_args(parser, target_help="Specify the target instance ID."):
    """Adds arguments for targeting instances either by ID or app/env."""
    parser.add_argument(
        "target",
        nargs="?",
        help=target_help + " If omitted, requires --app and --env.",
    )
    _add_context_args(parser)  # Add --app and --env as optional ways to specify


def _add_service_context_args(parser, service_required=False):
    """Adds common arguments for service context."""
    parser.add_argument(
        "service_name",
        nargs="?" if not service_required else 1,
        metavar="SERVICE_NAME",
        help=f"Specify the service name{' (required)' if service_required else ' (inferred if only one exists for the context)'}.",
    )
    _add_context_args(parser)


# --- Parser Creation ---


def create_parser():
    """Creates the main argument parser for the Hop3 CLI."""
    parser = argparse.ArgumentParser(
        prog="hop3",
        description="Command Line Interface for the Hop3 Platform.",
        epilog="Run 'hop3 <command> --help' for more information on a specific command.",
    )

    # --- Global Options ---
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {APP_VERSION}"
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase output verbosity (-v, -vv, -vvv).",
    )
    parser.add_argument(
        "--json", action="store_true", help="Output results in JSON format."
    )
    parser.add_argument(
        "-y",
        "--non-interactive",
        action="store_true",
        help="Assume 'yes' to all prompts; disable interactive features.",
    )
    parser.add_argument(
        "--api-url", metavar="URL", help="Override the default Hop3 API server URL."
    )

    # --- Top-Level Subparsers (Nouns or Direct Actions) ---
    subparsers = parser.add_subparsers(
        dest="command",
        title="Available Commands",
        metavar="<command>",
        help="Use 'hop3 <command> --help' for details",
        required=True,  # Make selecting a command mandatory
    )

    # --- Auth ---
    auth_parser = subparsers.add_parser(
        "auth", help="Manage authentication and login status."
    )
    auth_subparsers = auth_parser.add_subparsers(
        dest="subcommand", title="Auth Commands", required=True, metavar="<subcommand>"
    )

    login_parser = auth_subparsers.add_parser("login", help="Log in to a Hop3 server.")
    login_parser.add_argument(
        "--token", metavar="API_TOKEN", help="Log in using an API token directly."
    )
    login_parser.add_argument(
        "--sso", metavar="PROVIDER", help="Log in via a specific SSO provider."
    )

    auth_subparsers.add_parser("logout", help="Log out and clear local credentials.")
    auth_subparsers.add_parser(
        "status", help="Display current logged-in user and server info."
    )
    auth_subparsers.add_parser(
        "whoami", help="Alias for 'auth status'."
    )  # Common alias

    # --- Link / Unlink / Init (Top Level Actions) ---
    link_parser = subparsers.add_parser(
        "link",
        help="Associate the current directory with an existing Hop3 application.",
    )
    link_parser.add_argument(
        "app_name", metavar="APP_NAME", help="The name of the application to link."
    )
    link_parser.add_argument(
        "--org",
        metavar="ORG_NAME",
        help="Specify the organization owner of the application.",
    )

    subparsers.add_parser(
        "unlink",
        help="Remove the Hop3 application association from the current directory.",
    )

    init_parser = subparsers.add_parser(
        "init", help="Initialize a new Hop3 project in the current directory."
    )
    init_parser.add_argument(
        "--template",
        metavar="TEMPLATE_NAME",
        help="Initialize from a specific template.",
    )
    init_parser.add_argument(
        "--from-git", metavar="REPO_URL", help="Initialize by cloning a git repository."
    )
    init_parser.add_argument(
        "--name",
        metavar="APP_NAME",
        help="Specify the application name during initialization.",
    )
    init_parser.add_argument(
        "--org",
        metavar="ORG_NAME",
        help="Specify the organization for the new application.",
    )

    # --- Apps ---
    apps_parser = subparsers.add_parser("apps", help="Manage application definitions.")
    apps_subparsers = apps_parser.add_subparsers(
        dest="subcommand", title="Apps Commands", required=True, metavar="<subcommand>"
    )

    apps_list_parser = apps_subparsers.add_parser(
        "list", help="List applications you have access to."
    )
    apps_list_parser.add_argument(
        "--org", metavar="ORG_NAME", help="Filter applications by organization."
    )

    apps_create_parser = apps_subparsers.add_parser(
        "create", help="Create a new application definition."
    )
    apps_create_parser.add_argument(
        "app_name", metavar="APP_NAME", help="The name for the new application."
    )
    apps_create_parser.add_argument(
        "--org",
        metavar="ORG_NAME",
        help="Specify the organization for the new application.",
    )
    apps_create_parser.add_argument(
        "--region", metavar="REGION_ID", help="Specify the region for the application."
    )

    apps_info_parser = apps_subparsers.add_parser(
        "info", help="Show detailed information about an application."
    )
    apps_info_parser.add_argument(
        "app_name",
        nargs="?",
        metavar="APP_NAME",
        help="The name of the application (defaults to linked app).",
    )

    apps_delete_parser = apps_subparsers.add_parser(
        "delete", help="Delete an application definition (irreversible)."
    )
    apps_delete_parser.add_argument(
        "app_name", metavar="APP_NAME", help="The name of the application to delete."
    )

    apps_open_parser = apps_subparsers.add_parser(
        "open", help="Open the application's dashboard in a web browser."
    )
    apps_open_parser.add_argument(
        "app_name",
        nargs="?",
        metavar="APP_NAME",
        help="The name of the application (defaults to linked app).",
    )

    # --- Instances ---
    instances_parser = subparsers.add_parser(
        "instances", help="Manage running instances of applications."
    )
    instances_subparsers = instances_parser.add_subparsers(
        dest="subcommand",
        title="Instances Commands",
        required=True,
        metavar="<subcommand>",
    )

    inst_list_parser = instances_subparsers.add_parser(
        "list", help="List running instances."
    )
    _add_context_args(inst_list_parser)

    inst_info_parser = instances_subparsers.add_parser(
        "info", help="Show detailed info about a specific instance."
    )
    inst_info_parser.add_argument(
        "instance_id", metavar="INSTANCE_ID", help="The ID of the instance."
    )

    inst_restart_parser = instances_subparsers.add_parser(
        "restart", help="Restart instance(s)."
    )
    _add_target_args(
        inst_restart_parser, target_help="The ID of the instance to restart."
    )
    inst_restart_parser.add_argument(
        "--type",
        metavar="PROCESS_TYPE",
        help="Restart only instances of a specific process type (e.g., 'web', 'worker').",
    )

    inst_stop_parser = instances_subparsers.add_parser(
        "stop", help="Stop instance(s) (scale to zero or pause)."
    )
    _add_target_args(inst_stop_parser, target_help="The ID of the instance to stop.")

    inst_start_parser = instances_subparsers.add_parser(
        "start", help="Start stopped instance(s)."
    )
    _add_target_args(inst_start_parser, target_help="The ID of the instance to start.")

    inst_destroy_parser = instances_subparsers.add_parser(
        "destroy", help="Permanently destroy instance(s) and ephemeral data."
    )
    _add_target_args(
        inst_destroy_parser, target_help="The ID of the instance to destroy."
    )

    inst_ssh_parser = instances_subparsers.add_parser(
        "ssh", help="SSH into a running instance."
    )
    inst_ssh_parser.add_argument(
        "target",
        nargs="?",
        metavar="INSTANCE_ID",
        help="The ID of the instance to SSH into. If omitted, uses --app/--env and may prompt.",
    )
    _add_context_args(inst_ssh_parser)
    inst_ssh_parser.add_argument(
        "--select",
        action="store_true",
        help="Prompt to select instance if multiple match.",
    )
    inst_ssh_parser.add_argument(
        "ssh_command",
        nargs=argparse.REMAINDER,
        metavar="COMMAND",
        help="Optional command to run directly via SSH.",
    )

    inst_exec_parser = instances_subparsers.add_parser(
        "exec", help="Execute a one-off command inside a running instance."
    )
    inst_exec_parser.add_argument(
        "target",
        nargs="?",
        metavar="INSTANCE_ID",
        help="The ID of the instance to execute in. If omitted, uses --app/--env and may prompt.",
    )
    _add_context_args(inst_exec_parser)
    inst_exec_parser.add_argument(
        "--select",
        action="store_true",
        help="Prompt to select instance if multiple match.",
    )
    inst_exec_parser.add_argument(
        "exec_command",
        nargs=argparse.REMAINDER,  # Use REMAINDER to capture command and args
        metavar="COMMAND [ARGS...]",
        help="The command and arguments to execute.",
    )

    # --- Scale (Noun-Verb) ---
    scale_parser = subparsers.add_parser(
        "scale", help="Manage application instance scaling."
    )
    scale_subparsers = scale_parser.add_subparsers(
        dest="subcommand", title="Scale Commands", required=True, metavar="<subcommand>"
    )

    scale_set_parser = scale_subparsers.add_parser(
        "set", help="Set instance counts for process types."
    )
    scale_set_parser.add_argument(
        "scale_args",
        nargs="+",
        metavar="TYPE=COUNT",
        help="One or more process type scaling arguments (e.g., web=3 worker=1).",
    )
    _add_target_args(
        scale_set_parser,
        target_help="Optional instance ID (usually scaling is per app/env).",
    )

    scale_show_parser = scale_subparsers.add_parser(
        "show", help="Display current scaling settings."
    )
    _add_target_args(scale_show_parser, target_help="Optional instance ID.")

    # --- Build (Top Level Action) ---
    build_parser = subparsers.add_parser(
        "build", help="Build the application artifact (e.g., Docker image)."
    )
    build_parser.add_argument(
        "--tag", metavar="TAG", help="Tag for the built artifact (e.g., image tag)."
    )
    build_parser.add_argument(
        "--push",
        action="store_true",
        help="Push the artifact to the registry after building.",
    )
    build_parser.add_argument(
        "--builder",
        metavar="BUILDER_NAME",
        help="Specify a specific builder (e.g., buildpack builder).",
    )
    # Implicitly uses current directory context

    # --- Dev (Noun-Verb for Local Development) ---
    dev_parser = subparsers.add_parser(
        "dev", help="Run and manage the application locally."
    )
    dev_subparsers = dev_parser.add_subparsers(
        dest="subcommand", title="Dev Commands", required=True, metavar="<subcommand>"
    )

    dev_run_parser = dev_subparsers.add_parser(
        "run", help="Run the application locally (like production)."
    )
    dev_run_parser.add_argument(
        "process_type",
        nargs="?",
        metavar="PROCESS_TYPE",
        help="Specify a process type to run (defaults to web or as defined).",
    )

    dev_exec_parser = dev_subparsers.add_parser(
        "exec", help="Run a one-off command in the local dev environment."
    )
    dev_exec_parser.add_argument(
        "exec_command",
        nargs=argparse.REMAINDER,
        metavar="COMMAND [ARGS...]",
        help="The command and arguments to execute locally.",
    )

    # --- Deploy (Top Level Action) ---
    deploy_parser = subparsers.add_parser(
        "deploy", help="Deploy the application to a Hop3 environment."
    )
    deploy_parser.add_argument(
        "source",
        nargs="?",
        metavar="SOURCE",
        help="Source to deploy (e.g., git ref, local path). Defaults to current directory.",
    )
    _add_context_args(deploy_parser)  # --app and --env are crucial here
    deploy_parser.add_argument(
        "--image",
        metavar="IMAGE_NAME",
        help="Deploy a specific pre-built image instead of building.",
    )
    deploy_parser.add_argument(
        "-m",
        "--message",
        metavar="MSG",
        help="Add a message to the deployment/release.",
    )

    # --- Releases ---
    releases_parser = subparsers.add_parser(
        "releases", help="Manage application deployments (releases)."
    )
    releases_subparsers = releases_parser.add_subparsers(
        dest="subcommand",
        title="Releases Commands",
        required=True,
        metavar="<subcommand>",
    )

    rel_list_parser = releases_subparsers.add_parser(
        "list", help="List past deployments/releases."
    )
    _add_context_args(rel_list_parser)

    rel_info_parser = releases_subparsers.add_parser(
        "info", help="Show details about a specific release."
    )
    rel_info_parser.add_argument(
        "release_id", metavar="RELEASE_ID", help="The ID of the release."
    )
    _add_context_args(rel_info_parser)

    rel_rollback_parser = releases_subparsers.add_parser(
        "rollback", help="Rollback to a previous release."
    )
    rel_rollback_parser.add_argument(
        "release_id",
        nargs="?",
        metavar="RELEASE_ID",
        help="The ID of the release to roll back to (defaults to the previous one).",
    )
    _add_context_args(rel_rollback_parser)

    # --- Config ---
    config_parser = subparsers.add_parser(
        "config", help="Manage application environment variables."
    )
    config_subparsers = config_parser.add_subparsers(
        dest="subcommand",
        title="Config Commands",
        required=True,
        metavar="<subcommand>",
    )

    conf_list_parser = config_subparsers.add_parser(
        "list", help="List environment variables (excludes secrets)."
    )
    _add_context_args(conf_list_parser)

    conf_set_parser = config_subparsers.add_parser(
        "set", help="Set one or more environment variables."
    )
    conf_set_parser.add_argument(
        "vars", nargs="+", metavar="KEY=VALUE", help="Variable(s) to set."
    )
    _add_context_args(conf_set_parser)

    conf_unset_parser = config_subparsers.add_parser(
        "unset", help="Unset one or more environment variables."
    )
    conf_unset_parser.add_argument(
        "keys", nargs="+", metavar="KEY", help="Variable key(s) to unset."
    )
    _add_context_args(conf_unset_parser)

    conf_get_parser = config_subparsers.add_parser(
        "get", help="Get the value of a single environment variable."
    )
    conf_get_parser.add_argument("key", metavar="KEY", help="The variable key to get.")
    _add_context_args(conf_get_parser)

    # --- Secrets ---
    secrets_parser = subparsers.add_parser(
        "secrets", help="Manage application secrets (sensitive environment variables)."
    )
    secrets_subparsers = secrets_parser.add_subparsers(
        dest="subcommand",
        title="Secrets Commands",
        required=True,
        metavar="<subcommand>",
    )

    sec_list_parser = secrets_subparsers.add_parser(
        "list", help="List secret keys (values are masked)."
    )
    _add_context_args(sec_list_parser)

    sec_set_parser = secrets_subparsers.add_parser(
        "set", help="Set one or more secrets. Use '-' for VALUE to read from stdin."
    )
    sec_set_parser.add_argument(
        "vars",
        nargs="+",
        metavar="KEY=VALUE",
        help="Secret(s) to set (e.g., SECRET_KEY=myvalue SECRET_TOKEN=-).",
    )
    _add_context_args(sec_set_parser)

    sec_unset_parser = secrets_subparsers.add_parser(
        "unset", help="Unset one or more secrets."
    )
    sec_unset_parser.add_argument(
        "keys", nargs="+", metavar="KEY", help="Secret key(s) to unset."
    )
    _add_context_args(sec_unset_parser)

    sec_reveal_parser = secrets_subparsers.add_parser(
        "reveal", help="Show the value of a secret (use with caution!)."
    )
    sec_reveal_parser.add_argument(
        "key", metavar="KEY", help="The secret key to reveal."
    )
    _add_context_args(sec_reveal_parser)

    # --- Logs (Top Level Action) ---
    logs_parser = subparsers.add_parser("logs", help="View or stream application logs.")
    _add_context_args(logs_parser, instance_optional=True)
    logs_parser.add_argument(
        "-f", "--follow", action="store_true", help="Follow log output (stream)."
    )
    logs_parser.add_argument(
        "-n", "--lines", type=int, metavar="NUM", help="Number of lines to show."
    )
    logs_parser.add_argument(
        "--type",
        metavar="PROCESS_TYPE",
        help="Filter logs by process type (e.g., 'web', 'worker').",
    )

    # --- Status (Top Level Action) ---
    status_parser = subparsers.add_parser(
        "status", help="Show the overall status of an application/environment."
    )
    _add_context_args(status_parser)

    # --- Services ---
    services_parser = subparsers.add_parser(
        "services", help="Manage backing services (addons)."
    )
    services_subparsers = services_parser.add_subparsers(
        dest="subcommand",
        title="Services Commands",
        required=True,
        metavar="<subcommand>",
    )

    svc_list_parser = services_subparsers.add_parser(
        "list", help="List attached services."
    )
    _add_context_args(svc_list_parser)

    svc_create_parser = services_subparsers.add_parser(
        "create", help="Provision a new service."
    )
    svc_create_parser.add_argument(
        "service_type",
        metavar="TYPE",
        help="Type of service to create (e.g., postgres, redis, marketplace:...).",
    )
    svc_create_parser.add_argument(
        "service_name", metavar="NAME", help="Name for the new service instance."
    )
    _add_context_args(svc_create_parser)
    svc_create_parser.add_argument(
        "--plan", metavar="PLAN_NAME", help="Specify the service plan (size/tier)."
    )
    svc_create_parser.add_argument(
        "--region", metavar="REGION_ID", help="Specify the region for the service."
    )

    svc_info_parser = services_subparsers.add_parser(
        "info", help="Show details about a service."
    )
    _add_service_context_args(svc_info_parser, service_required=True)

    svc_delete_parser = services_subparsers.add_parser(
        "delete", help="Delete a service instance (irreversible)."
    )
    _add_service_context_args(svc_delete_parser, service_required=True)

    svc_attach_parser = services_subparsers.add_parser(
        "attach", help="Attach an existing service to an app/environment."
    )
    svc_attach_parser.add_argument(
        "service_name", metavar="SERVICE_NAME", help="Name of the service to attach."
    )
    _add_context_args(svc_attach_parser, app_required=True)  # Need --app to attach TO
    svc_attach_parser.add_argument(
        "--as",
        metavar="ALIAS",
        help="Attach the service under a specific alias/prefix.",
    )

    svc_detach_parser = services_subparsers.add_parser(
        "detach", help="Detach a service from an app/environment."
    )
    svc_detach_parser.add_argument(
        "service_name", metavar="SERVICE_NAME", help="Name of the service to detach."
    )
    _add_context_args(svc_detach_parser, app_required=True)  # Need --app to detach FROM

    # --- Service-Specific Commands (Example: Postgres) ---
    pg_parser = subparsers.add_parser("pg", help="Manage Postgres services.")
    pg_subparsers = pg_parser.add_subparsers(
        dest="subcommand",
        title="Postgres Commands",
        required=True,
        metavar="<subcommand>",
    )

    pg_list_parser = pg_subparsers.add_parser(
        "list", help="List Postgres services for the context."
    )
    _add_context_args(pg_list_parser)

    pg_connect_parser = pg_subparsers.add_parser(
        "connect", help="Open a psql shell to the database."
    )
    _add_service_context_args(pg_connect_parser)  # Service name optional

    pg_info_parser = pg_subparsers.add_parser(
        "info", help="Show connection info for the database."
    )
    _add_service_context_args(pg_info_parser)  # Service name optional

    pg_creds_parser = pg_subparsers.add_parser(
        "credentials", help="Show database credentials."
    )
    _add_service_context_args(pg_creds_parser)  # Service name optional

    pg_promote_parser = pg_subparsers.add_parser(
        "promote", help="Promote a follower/replica database (if applicable)."
    )
    _add_service_context_args(pg_promote_parser, service_required=True)

    # Nested backup commands for PG
    pg_backup_parser = pg_subparsers.add_parser(
        "backup", help="Manage Postgres backups."
    )
    pg_backup_subparsers = pg_backup_parser.add_subparsers(
        dest="backup_subcommand",
        title="Backup Commands",
        required=True,
        metavar="<subcommand>",
    )
    pg_backup_create_parser = pg_backup_subparsers.add_parser(
        "create", help="Create a new database backup."
    )
    _add_service_context_args(pg_backup_create_parser)  # Service name optional
    # Add backup-specific args if needed, e.g., --name

    pg_backup_list_parser = pg_backup_subparsers.add_parser(
        "list", help="List available database backups."
    )
    _add_service_context_args(pg_backup_list_parser)  # Service name optional

    pg_backup_restore_parser = pg_backup_subparsers.add_parser(
        "restore", help="Restore a database from a backup."
    )
    pg_backup_restore_parser.add_argument(
        "backup_id", metavar="BACKUP_ID", help="The ID of the backup to restore."
    )
    _add_service_context_args(pg_backup_restore_parser)  # Service name optional
    # Add restore-specific args if needed, e.g., --target-service

    # --- Service-Specific Commands (Example: Redis) ---
    redis_parser = subparsers.add_parser("redis", help="Manage Redis services.")
    redis_subparsers = redis_parser.add_subparsers(
        dest="subcommand", title="Redis Commands", required=True, metavar="<subcommand>"
    )

    redis_list_parser = redis_subparsers.add_parser(
        "list", help="List Redis services for the context."
    )
    _add_context_args(redis_list_parser)

    redis_cli_parser = redis_subparsers.add_parser(
        "cli", help="Open a redis-cli shell to the service."
    )
    _add_service_context_args(redis_cli_parser)  # Service name optional

    redis_info_parser = redis_subparsers.add_parser(
        "info", help="Show connection info for the Redis service."
    )
    _add_service_context_args(redis_info_parser)  # Service name optional

    # Add other redis commands as needed (e.g., flushdb)

    # --- Marketplace ---
    marketplace_parser = subparsers.add_parser(
        "marketplace", help="Discover apps and services in the Hop3 Marketplace."
    )
    marketplace_subparsers = marketplace_parser.add_subparsers(
        dest="subcommand",
        title="Marketplace Commands",
        required=True,
        metavar="<subcommand>",
    )

    mkt_search_parser = marketplace_subparsers.add_parser(
        "search", help="Search the marketplace."
    )
    mkt_search_parser.add_argument("query", metavar="QUERY", help="Search term(s).")

    mkt_info_parser = marketplace_subparsers.add_parser(
        "info", help="Show details about a marketplace item."
    )
    mkt_info_parser.add_argument(
        "template_name",
        metavar="TEMPLATE_NAME",
        help="Name of the marketplace app or service template.",
    )

    marketplace_subparsers.add_parser("list", help="List available marketplace items.")
    # Installation is handled via 'hop3 apps create --from-marketplace ...' or 'hop3 services create marketplace:...'

    # --- Networking (Domains) ---
    domains_parser = subparsers.add_parser(
        "domains", help="Manage custom domains for applications."
    )
    domains_subparsers = domains_parser.add_subparsers(
        dest="subcommand",
        title="Domains Commands",
        required=True,
        metavar="<subcommand>",
    )

    dom_list_parser = domains_subparsers.add_parser("list", help="List custom domains.")
    _add_context_args(dom_list_parser)

    dom_add_parser = domains_subparsers.add_parser(
        "add", help="Add a custom domain to an application environment."
    )
    dom_add_parser.add_argument(
        "domain_name",
        metavar="DOMAIN_NAME",
        help="The domain name to add (e.g., www.example.com).",
    )
    _add_context_args(dom_add_parser)

    dom_remove_parser = domains_subparsers.add_parser(
        "remove", help="Remove a custom domain."
    )
    dom_remove_parser.add_argument(
        "domain_name", metavar="DOMAIN_NAME", help="The domain name to remove."
    )
    _add_context_args(dom_remove_parser)

    # --- Networking (Certs) ---
    certs_parser = subparsers.add_parser("certs", help="Manage SSL/TLS certificates.")
    certs_subparsers = certs_parser.add_subparsers(
        dest="subcommand",
        title="Certificates Commands",
        required=True,
        metavar="<subcommand>",
    )

    cert_list_parser = certs_subparsers.add_parser(
        "list", help="List SSL/TLS certificates."
    )
    _add_context_args(cert_list_parser)

    cert_add_parser = certs_subparsers.add_parser(
        "add", help="Add/provision an SSL/TLS certificate for a domain."
    )
    cert_add_parser.add_argument(
        "--domain",
        metavar="DOMAIN_NAME",
        required=True,
        help="The domain name the certificate is for.",
    )
    # Add args for custom cert upload if needed (--cert-file, --key-file)
    _add_context_args(cert_add_parser)

    cert_remove_parser = certs_subparsers.add_parser(
        "remove", help="Remove an SSL/TLS certificate."
    )
    cert_remove_group = cert_remove_parser.add_mutually_exclusive_group(required=True)
    cert_remove_group.add_argument(
        "--domain",
        metavar="DOMAIN_NAME",
        help="Remove the certificate associated with this domain.",
    )
    cert_remove_group.add_argument(
        "--cert-id", metavar="CERT_ID", help="Remove the certificate by its ID."
    )
    _add_context_args(cert_remove_parser)

    # --- Networking (IPs) ---
    ips_parser = subparsers.add_parser("ips", help="Manage dedicated IP addresses.")
    ips_subparsers = ips_parser.add_subparsers(
        dest="subcommand", title="IP Commands", required=True, metavar="<subcommand>"
    )

    ips_list_parser = ips_subparsers.add_parser(
        "list", help="List IP addresses associated with the app/env or organization."
    )
    _add_context_args(ips_list_parser)
    # Maybe add --org flag here too

    ips_alloc_parser = ips_subparsers.add_parser(
        "allocate", help="Allocate a new dedicated IP address."
    )
    ips_alloc_parser.add_argument(
        "--type",
        choices=["ipv4", "ipv6"],
        default="ipv4",
        help="Type of IP address to allocate.",
    )
    ips_alloc_parser.add_argument(
        "--region",
        metavar="REGION_ID",
        help="Allocate IP in a specific region (if applicable).",
    )
    # Maybe add --app/--env to associate directly

    ips_release_parser = ips_subparsers.add_parser(
        "release", help="Release a dedicated IP address."
    )
    ips_release_parser.add_argument(
        "ip_address", metavar="IP_ADDRESS", help="The IP address to release."
    )

    # --- System / Utility ---
    subparsers.add_parser(
        "update", help="Check for and install updates to the Hop3 CLI."
    )
    subparsers.add_parser(
        "doctor", help="Run diagnostic checks for CLI setup and connectivity."
    )

    return parser


# --- Main Execution & Example ---

if __name__ == "__main__":
    parser = create_parser()

    # Example command lines to test parsing
    example_commands = [
        "login",
        "login --token mysecrettoken",
        "auth status",
        "apps list",
        "apps create my-new-app --org myorg --region us-east-1",
        "link existing-app",
        "init --template nodejs --name my-node-proj",
        "deploy -m 'Initial deploy' --env production",
        "deploy --image myregistry/myimage:latest --app myapp --env staging",
        "build --push --tag latest",
        "dev run worker",
        "dev exec -- ls -la /app",
        "instances list --app myapp",
        "instances restart i-123abc456",
        "instances stop --app myapp --env staging",
        "instances exec --app myapp --env prod --select -- bash",
        "scale set web=2 worker=1 --app myapp --env prod",
        "scale show --app otherapp",
        "releases list --app myapp",
        "releases rollback --app myapp --env prod",
        "config list --app myapp",
        "config set DB_HOST=localhost POOL_SIZE=10 --app myapp --env dev",
        "config unset POOL_SIZE --app myapp --env dev",
        "secrets set API_KEY=supersecret --app myapp",
        "secrets set JWT_SECRET=- --app otherapp --env prod",  # Read from stdin
        "secrets reveal API_KEY --app myapp",
        "logs --app myapp -f -n 100",
        "logs --instance i-abcdef123 --follow",
        "status --app myapp --env prod",
        "services list --app myapp",
        "services create postgres my-db --plan standard-1 --app myapp --env staging",
        "services attach shared-redis --app myapp --env staging --as CACHE",
        "pg connect my-db --app myapp",
        "pg backup create --app myapp --env prod",
        "pg backup list my-db --app myapp",
        "redis cli --app myapp --env prod",  # Assumes only one redis service
        "marketplace search database",
        "marketplace info wordpress-template",
        "domains add www.myapp.com --app myapp --env production",
        "certs list --app myapp",
        "certs add --domain www.myapp.com --app myapp --env production",
        "ips list",
        "ips allocate --type ipv6",
        "ips release 192.0.2.1",
        "doctor",
        "update",
        "--version",
        "-h",  # Help
        "apps",  # Should show help for apps
        "pg backup",  # Should show help for pg backup
    ]

    print("--- Testing CLI Argument Parsing ---")

    for i, cmd_str in enumerate(example_commands):
        print(f"\n[{i + 1}] Testing: hop3 {cmd_str}")
        cmd_list = cmd_str.split()
        try:
            # Simulate command line arguments (excluding the script name itself)
            args = parser.parse_args(cmd_list)
            print(f"  Parsed Args: {args}")
        except SystemExit as e:
            # Catch SystemExit typically raised by --help, --version, or errors
            if e.code == 0:
                print("  Caught SystemExit with code 0 (likely --help or --version)")
            else:
                print(
                    f"  Caught SystemExit with code {e.code} (likely a parsing error)"
                )
        except Exception as e:
            print(f"  Unexpected Error: {e}")

    print("\n--- Testing Complete ---")

    # Example of how to use after parsing in a real application:
    # args = parser.parse_args() # Parses sys.argv[1:] by default
    #
    # if args.command == "apps":
    #     if args.subcommand == "list":
    #         # Call your function to list apps
    #         # list_apps(org=args.org, output_format='json' if args.json else 'text')
    #         pass
    #     elif args.subcommand == "create":
    #         # Call function to create app
    #         # create_app(args.app_name, org=args.org, region=args.region, ...)
    #         pass
    #     # ... etc ...
    # elif args.command == "login":
    #     # Call login function
    #     # login(token=args.token, sso=args.sso, ...)
    #     pass
    # # ... etc ...
