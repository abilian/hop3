# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""WAF (Web Application Firewall) CLI commands.

Commands for managing the WAF service, checking status, viewing logs,
and configuring per-app WAF settings.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, ClassVar

from hop3.config import HopConfig
from hop3.core.plugins import get_waf_engine, is_waf_enabled
from hop3.lib.registry import register

from ._base import Command

if TYPE_CHECKING:
    pass


@register
class WafCmd(Command):
    """Manage the Web Application Firewall."""

    name: ClassVar[str] = "waf"


@register
class WafStatusCmd(Command):
    """Show WAF service status.

    Displays the current status of the WAF service, including:
    - Whether WAF is enabled at the server level
    - The configured WAF engine
    - Service running state
    - List of apps with WAF enabled

    Usage: hop waf:status

    Examples:
        hop waf:status
    """

    name: ClassVar[str] = "waf:status"

    def call(self, *args):
        config = HopConfig.get_instance()
        output = []

        # Server-level WAF status
        waf_enabled = is_waf_enabled()
        output.append(f"WAF Enabled: {'Yes' if waf_enabled else 'No'}")
        output.append(f"WAF Engine: {config.HOP3_WAF_ENGINE}")
        output.append(f"Default Mode: {config.HOP3_WAF_DEFAULT_MODE}")
        output.append(f"Default Paranoia Level: {config.HOP3_WAF_DEFAULT_PARANOIA}")
        output.append("")

        if not waf_enabled:
            output.append("WAF is disabled at server level.")
            output.append("Set HOP3_WAF_ENABLED=true in hop3-server.toml to enable.")
            return [{"t": "text", "text": "\n".join(output)}]

        # Check service status
        waf_engine = get_waf_engine()
        if waf_engine:
            running = waf_engine.is_running()
            output.append(f"Service Status: {'Running' if running else 'Stopped'}")
            output.append(f"Socket Path: {waf_engine.get_upstream_socket()}")
        else:
            output.append("Service Status: Not Available")
        output.append("")

        # List apps with WAF configured
        apps_config_dir = config.WAF_APPS_CONFIG
        if apps_config_dir.exists():
            app_configs = list(apps_config_dir.glob("*.yaml"))
            if app_configs:
                output.append("Apps with WAF enabled:")
                for config_file in sorted(app_configs):
                    app_name = config_file.stem
                    output.append(f"  - {app_name}")
            else:
                output.append("No apps have WAF enabled.")
        else:
            output.append("No apps have WAF enabled.")

        return [{"t": "text", "text": "\n".join(output)}]


@register
class WafReloadCmd(Command):
    """Reload WAF configuration.

    Reloads the WAF configuration without restarting the service.
    Use this after modifying WAF settings to apply changes.

    Usage: hop waf:reload

    Examples:
        hop waf:reload
    """

    name: ClassVar[str] = "waf:reload"

    def call(self, *args):
        if not is_waf_enabled():
            return [{"t": "error", "text": "WAF is not enabled at server level"}]

        waf_engine = get_waf_engine()
        if waf_engine is None:
            return [{"t": "error", "text": "WAF engine not available"}]

        if not waf_engine.is_running():
            return [{"t": "error", "text": "WAF service is not running"}]

        waf_engine.reload()
        return [{"t": "text", "text": "WAF configuration reloaded"}]


@register
class WafLogsCmd(Command):
    """Show WAF audit logs.

    Displays recent WAF audit log entries including blocked requests,
    detected attacks, and errors.

    Usage: hop waf:logs [--lines N] [--app APP_NAME]

    Arguments:
        --lines N      Number of lines to show (default: 50)
        --app APP_NAME Filter by application name

    Examples:
        hop waf:logs
        hop waf:logs --lines 100
        hop waf:logs --app my-app
    """

    name: ClassVar[str] = "waf:logs"

    def call(self, *args):
        config = HopConfig.get_instance()
        log_dir = config.WAF_LOG

        # Parse arguments
        lines = 50
        app_filter = None

        args_list = list(args)
        i = 0
        while i < len(args_list):
            if args_list[i] == "--lines" and i + 1 < len(args_list):
                try:
                    lines = int(args_list[i + 1])
                except ValueError:
                    pass
                i += 2
            elif args_list[i] == "--app" and i + 1 < len(args_list):
                app_filter = args_list[i + 1]
                i += 2
            else:
                i += 1

        # Read summary log (human-readable)
        summary_log = log_dir / "summary.log"
        if not summary_log.exists():
            return [{"t": "text", "text": "No WAF logs available yet."}]

        try:
            content = summary_log.read_text()
            log_lines = content.strip().split("\n")

            # Filter by app if specified
            if app_filter:
                log_lines = [line for line in log_lines if f" {app_filter} |" in line]

            # Get last N lines
            log_lines = log_lines[-lines:]

            if not log_lines:
                msg = "No matching log entries."
                if app_filter:
                    msg = f"No log entries for app '{app_filter}'."
                return [{"t": "text", "text": msg}]

            return [{"t": "text", "text": "\n".join(log_lines)}]

        except Exception as e:
            return [{"t": "error", "text": f"Error reading logs: {e}"}]


@register
class WafAuditCmd(Command):
    """Show WAF audit log (JSON format).

    Displays recent WAF audit log entries in JSON format.
    Useful for scripting and detailed analysis.

    Usage: hop waf:audit [--lines N] [--app APP_NAME]

    Arguments:
        --lines N      Number of entries to show (default: 20)
        --app APP_NAME Filter by application name

    Examples:
        hop waf:audit
        hop waf:audit --lines 50
        hop waf:audit --app my-app
    """

    name: ClassVar[str] = "waf:audit"

    def call(self, *args):
        config = HopConfig.get_instance()
        log_dir = config.WAF_LOG

        # Parse arguments
        lines = 20
        app_filter = None

        args_list = list(args)
        i = 0
        while i < len(args_list):
            if args_list[i] == "--lines" and i + 1 < len(args_list):
                try:
                    lines = int(args_list[i + 1])
                except ValueError:
                    pass
                i += 2
            elif args_list[i] == "--app" and i + 1 < len(args_list):
                app_filter = args_list[i + 1]
                i += 2
            else:
                i += 1

        # Read audit log (JSON format)
        audit_log = log_dir / "audit.log"
        if not audit_log.exists():
            return [{"t": "text", "text": "No WAF audit logs available yet."}]

        try:
            content = audit_log.read_text()
            log_lines = content.strip().split("\n")

            # Parse and filter
            events = []
            for line in log_lines:
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                    if app_filter and event.get("app_name") != app_filter:
                        continue
                    events.append(event)
                except json.JSONDecodeError:
                    continue

            # Get last N events
            events = events[-lines:]

            if not events:
                msg = "No matching audit entries."
                if app_filter:
                    msg = f"No audit entries for app '{app_filter}'."
                return [{"t": "text", "text": msg}]

            # Format as pretty JSON
            output = json.dumps(events, indent=2)
            return [{"t": "text", "text": output}]

        except Exception as e:
            return [{"t": "error", "text": f"Error reading audit logs: {e}"}]


@register
class WafAppCmd(Command):
    """Show WAF configuration for an app.

    Displays the WAF configuration for a specific application.

    Usage: hop waf:app <app_name>

    Arguments:
        app_name  Name of the application

    Examples:
        hop waf:app my-app
    """

    name: ClassVar[str] = "waf:app"

    def call(self, *args):
        if not args:
            return [{"t": "error", "text": "Usage: hop waf:app <app_name>"}]

        app_name = args[0]
        config = HopConfig.get_instance()

        config_file = config.WAF_APPS_CONFIG / f"{app_name}.yaml"
        if not config_file.exists():
            return [
                {
                    "t": "text",
                    "text": f"No WAF configuration found for app '{app_name}'.",
                }
            ]

        try:
            import yaml  # noqa: PLC0415

            content = config_file.read_text()
            waf_config = yaml.safe_load(content)

            output = [f"WAF Configuration for '{app_name}':", ""]
            output.append(f"  Enabled: {waf_config.get('enabled', False)}")
            output.append(f"  Mode: {waf_config.get('mode', 'block')}")
            output.append(f"  Paranoia Level: {waf_config.get('paranoia_level', 1)}")
            output.append(f"  Ruleset: {waf_config.get('ruleset', 'owasp-crs')}")

            rules = waf_config.get("rules", {})
            if rules.get("allow_paths"):
                output.append(f"  Allow Paths: {', '.join(rules['allow_paths'])}")
            if rules.get("deny_paths"):
                output.append(f"  Deny Paths: {', '.join(rules['deny_paths'])}")
            if rules.get("allow_ips"):
                output.append(f"  Allow IPs: {', '.join(rules['allow_ips'])}")
            if rules.get("deny_ips"):
                output.append(f"  Deny IPs: {', '.join(rules['deny_ips'])}")
            if rules.get("exclusions"):
                output.append(f"  Exclusions: {', '.join(rules['exclusions'])}")
            if rules.get("disabled_rule_ids"):
                output.append(f"  Disabled Rules: {rules['disabled_rule_ids']}")

            return [{"t": "text", "text": "\n".join(output)}]

        except Exception as e:
            return [{"t": "error", "text": f"Error reading WAF config: {e}"}]


@register
class WafStatsCmd(Command):
    """Show WAF statistics.

    Displays WAF statistics including blocked requests, detected attacks,
    and top triggered rules.

    Usage: hop waf:stats [--period PERIOD]

    Arguments:
        --period PERIOD  Time period: today, week, month, all (default: today)

    Examples:
        hop waf:stats
        hop waf:stats --period week
    """

    name: ClassVar[str] = "waf:stats"

    def call(self, *args):
        config = HopConfig.get_instance()
        log_dir = config.WAF_LOG

        audit_log = log_dir / "audit.log"
        if not audit_log.exists():
            return [
                {"t": "text", "text": "No WAF audit logs available for statistics."}
            ]

        try:
            content = audit_log.read_text()
            log_lines = content.strip().split("\n")

            # Count events
            blocked = 0
            detected = 0
            allowed = 0
            errors = 0
            rule_counts: dict[int, int] = {}
            app_counts: dict[str, int] = {}

            for line in log_lines:
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                    level = event.get("level", "")

                    if level == "BLOCK":
                        blocked += 1
                        rule_id = event.get("rule_id", 0)
                        if rule_id:
                            rule_counts[rule_id] = rule_counts.get(rule_id, 0) + 1
                    elif level == "DETECT":
                        detected += 1
                    elif level == "ALLOW":
                        allowed += 1
                    elif level == "ERROR":
                        errors += 1

                    app_name = event.get("app_name", "unknown")
                    if level in ("BLOCK", "DETECT"):
                        app_counts[app_name] = app_counts.get(app_name, 0) + 1

                except json.JSONDecodeError:
                    continue

            # Build output
            output = [
                "WAF Statistics",
                "=" * 40,
                "",
                f"Total Blocked: {blocked}",
                f"Total Detected: {detected}",
                f"Total Allowed: {allowed}",
                f"Total Errors: {errors}",
                "",
            ]

            if rule_counts:
                output.append("Top Triggered Rules:")
                sorted_rules = sorted(
                    rule_counts.items(), key=lambda x: x[1], reverse=True
                )[:10]
                for rule_id, count in sorted_rules:
                    output.append(f"  Rule {rule_id}: {count} triggers")
                output.append("")

            if app_counts:
                output.append("Events by App:")
                sorted_apps = sorted(
                    app_counts.items(), key=lambda x: x[1], reverse=True
                )
                for app_name, count in sorted_apps:
                    output.append(f"  {app_name}: {count} events")

            return [{"t": "text", "text": "\n".join(output)}]

        except Exception as e:
            return [{"t": "error", "text": f"Error computing statistics: {e}"}]
