#!/usr/bin/env python3
# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Hop3 Demo Launcher.

Run demos on a target server to showcase Hop3 deployment features.

Usage:
    python demo.py --host HOST [options] [demos...]
    python demo.py --help
    python demo.py --list

Examples:
    python demo.py --host 46.62.169.221                    # Run all demos
    python demo.py --host 46.62.169.221 demo1              # Run demo1 only
    python demo.py --host 46.62.169.221 --local demo1      # Use local code
    python demo.py --host 46.62.169.221 --keep demo2       # Keep apps running
    python demo.py --host 46.62.169.221 ~/my-app           # Run external app
"""

from __future__ import annotations

import argparse
import secrets
import subprocess
import sys
import textwrap
from pathlib import Path

# Add demos directory to path for imports
DEMOS_DIR = Path(__file__).parent
sys.path.insert(0, str(DEMOS_DIR))

from lib import DemoContext
from lib.output import (
    Colors,
    pause,
    print_error,
    print_header,
    print_info,
    print_success,
)


def discover_demos() -> dict[str, tuple[str, str]]:
    """Discover available built-in demos.

    Returns:
        Dict mapping demo name to (title, description) tuple.
    """
    demos = {}
    for path in sorted(DEMOS_DIR.iterdir()):
        if path.is_dir() and path.name.startswith("demo"):
            script = path / "demo-script.py"
            if script.exists():
                # Try to extract title from the script
                title = path.name
                description = ""
                try:
                    content = script.read_text()
                    for line in content.split("\n"):
                        if line.startswith("TITLE"):
                            # Extract value from TITLE = "..."
                            title = line.split("=", 1)[1].strip().strip("\"'")
                        elif line.startswith("DESCRIPTION"):
                            # Just note there is a description
                            description = "(has description)"
                            break
                except Exception:
                    pass
                demos[path.name] = (title, description)
    return demos


def load_demo_module(demo_path: Path):
    """Load a demo script module from a path.

    Args:
        demo_path: Path to the demo-script.py file

    Returns:
        The loaded module, or None on failure.
    """
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location("demo_script", demo_path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception as e:
        print_error(f"Failed to load demo script: {e}")
        return None


def resolve_demo(demo_arg: str) -> tuple[str, Path | None, bool]:
    """Resolve a demo argument to its details.

    Args:
        demo_arg: Demo name (e.g., "demo1") or path (e.g., "~/my-app")

    Returns:
        Tuple of (display_name, demo_dir, is_generic)
        - display_name: Name to show in output
        - demo_dir: Path to the demo/app directory
        - is_generic: True if this needs the generic demo runner
    """
    # Check if it's a built-in demo name
    builtin_path = DEMOS_DIR / demo_arg
    if builtin_path.is_dir() and (builtin_path / "demo-script.py").exists():
        return (demo_arg, builtin_path, False)

    # Check if it's an external path
    expanded_path = Path(demo_arg).expanduser().resolve()
    if expanded_path.is_dir():
        # Check if it has a demo-script.py
        if (expanded_path / "demo-script.py").exists():
            return (expanded_path.name, expanded_path, False)
        # It's a generic demo (app directory without demo script)
        return (expanded_path.name, expanded_path, True)

    # Not found
    return (demo_arg, None, False)


def print_banner() -> None:
    """Print the demo banner."""
    banner = """
    ╦ ╦╔═╗╔═╗┌─┐  ╔╦╗┌─┐┌┬┐┌─┐┌─┐
    ╠═╣║ ║╠═╝ ─┤   ║║├┤ ││││ │└─┐
    ╩ ╩╚═╝╩  └─┘  ═╩╝└─┘┴ ┴└─┘└─┘

    Hop3 Demo Launcher
    ==================
    """
    print(f"{Colors.CYAN}{Colors.BOLD}{banner}{Colors.RESET}")


def print_config(ctx: DemoContext, demos: list[str]) -> None:
    """Print demo configuration."""
    print(f"{Colors.BOLD}Configuration:{Colors.RESET}")
    print(f"  Server:          {ctx.server_ip}")
    print(f"  SSH Target:      {ctx.ssh_target}")
    print(f"  Admin User:      {ctx.admin_user}")
    print(f"  Demos to run:    {', '.join(demos)}")
    print(f"  Local code:      {ctx.use_local_code}")
    print(f"  Skip install:    {ctx.skip_install}")
    print(f"  Keep apps:       {ctx.no_cleanup}")
    print()


def list_demos() -> None:
    """List available demos and exit."""
    demos = discover_demos()

    print(f"{Colors.BOLD}Available built-in demos:{Colors.RESET}")
    print()
    if demos:
        for name, (title, _desc) in demos.items():
            print(f"  {Colors.CYAN}{name:12}{Colors.RESET}  {title}")
    else:
        print("  (no demos found)")
    print()
    print(f"{Colors.DIM}You can also specify external paths to Hop3 applications.{Colors.RESET}")
    print()


def configure_cli(ctx: DemoContext) -> None:
    """Configure the local Hop3 CLI."""
    from lib.commands import run_hop3
    from lib.output import print_command, print_step

    print_header("Configuring Hop3 CLI")

    # Check if hop3 CLI is available
    print_step("Checking hop3 CLI availability...")
    result = subprocess.run(
        "which hop3", shell=True, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        print_error("hop3 CLI not found. Please install it first.")
        print_info("Run: pip install hop3-cli")
        sys.exit(1)
    print_success("hop3 CLI found")
    pause(ctx.pause_between_steps)

    # Create admin user via SSH
    print_step(f"Setting up admin user '{ctx.admin_user}'...")
    print_info("This will connect via SSH and create/login the admin account.")

    init_cmd = (
        f"echo '{ctx.admin_password}' | hop3 init "
        f"--ssh {ctx.ssh_target} "
        f"--username {ctx.admin_user} "
        f"--email {ctx.admin_email} "
        f"--server http://{ctx.server_ip}:8000 "
        f"--password-stdin --yes"
    )
    print_command(
        f"hop3 init --ssh {ctx.ssh_target} --username {ctx.admin_user} --email {ctx.admin_email}"
    )

    result = subprocess.run(
        init_cmd, shell=True, capture_output=True, text=True, check=False
    )
    if result.stdout:
        print(result.stdout)

    if result.returncode != 0:
        if "already exists" in result.stderr:
            print_info("Admin user already exists, attempting login...")
            login_cmd = (
                f"hop3 login --ssh {ctx.ssh_target} "
                f"--username {ctx.admin_user} "
                f"--server http://{ctx.server_ip}:8000"
            )
            result = subprocess.run(
                login_cmd, shell=True, capture_output=True, text=True, check=False
            )
            if result.stdout:
                print(result.stdout)
            if result.returncode != 0:
                print_error("Failed to login")
                if result.stderr:
                    print(f"  {Colors.RED}{result.stderr.strip()}{Colors.RESET}")
                sys.exit(1)
            print_success(f"Logged in as '{ctx.admin_user}'")
        else:
            print_error("Failed to create admin user")
            if result.stderr:
                print(f"  {Colors.RED}{result.stderr.strip()}{Colors.RESET}")
            sys.exit(1)
    else:
        print_success(f"Admin user '{ctx.admin_user}' created")
    pause(ctx.pause_between_steps)

    # Verify authentication
    print_step("Verifying authentication...")
    run_hop3("auth:whoami")
    print_success("Authentication verified")


def run_demo(ctx: DemoContext, demo_name: str, demo_dir: Path, is_generic: bool) -> bool:
    """Run a single demo.

    Args:
        ctx: Demo context
        demo_name: Display name for the demo
        demo_dir: Path to the demo directory
        is_generic: If True, run generic demo instead of demo-script.py

    Returns:
        True if demo completed successfully, False otherwise.
    """
    try:
        if is_generic:
            # Run generic demo
            from lib.generic_demo import run_generic_demo

            run_generic_demo(ctx, demo_dir)
            print_success(f"Demo '{demo_name}' completed successfully")
            return True
        else:
            # Load and run custom demo script
            script_path = demo_dir / "demo-script.py"
            module = load_demo_module(script_path)
            if not module:
                print_error(f"Failed to load demo '{demo_name}'")
                return False

            # Print demo banner
            title = getattr(module, "TITLE", demo_name)
            description = getattr(module, "DESCRIPTION", "")

            print_header(f"Running: {title}")
            if description:
                print(f"{Colors.DIM}{description}{Colors.RESET}")
                print()

            # Run demo's main function
            if hasattr(module, "run"):
                module.run(ctx)
                print_success(f"Demo '{demo_name}' completed successfully")
                return True
            else:
                print_error(f"Demo '{demo_name}' has no run() function")
                return False

    except KeyboardInterrupt:
        print()
        print_error("Demo interrupted by user")
        return False
    except Exception as e:
        print_error(f"Demo '{demo_name}' failed: {e}")
        if ctx.verbose:
            import traceback
            traceback.print_exc()
        return False


class CustomHelpFormatter(argparse.RawDescriptionHelpFormatter):
    """Custom help formatter with better grouping."""

    def __init__(self, prog):
        super().__init__(prog, max_help_position=30, width=80)


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser with grouped options."""
    demos = discover_demos()
    demo_list = "\n".join(
        f"    {name:12}  {title}" for name, (title, _) in demos.items()
    ) if demos else "    (no demos found)"

    epilog = f"""
Demos:
  Specify one or more demos to run. If none specified, runs all built-in demos.

  Built-in demos:
{demo_list}

  You can also specify:
    - External paths: ~/my-project or /path/to/demo
      (runs demo-script.py if present, otherwise runs generic demo)
    - 'all': Explicitly run all built-in demos

Examples:
  python demo.py --host 46.62.169.221                  Run all demos
  python demo.py --host 46.62.169.221 demo1            Run specific demo
  python demo.py --host 46.62.169.221 -l demo1         Use local code
  python demo.py --host 46.62.169.221 -k demo2         Keep apps running
  python demo.py --host 46.62.169.221 ~/my-app         External app
  python demo.py --host 46.62.169.221 -p 2 -k          Screencast mode
"""

    parser = argparse.ArgumentParser(
        prog="demo.py",
        description="Hop3 Demo Launcher - Interactive demonstrations of Hop3 deployment features.",
        epilog=textwrap.dedent(epilog),
        formatter_class=CustomHelpFormatter,
        add_help=False,
    )

    # Required arguments
    required = parser.add_argument_group("Required")
    required.add_argument(
        "-H", "--host",
        required=True,
        metavar="HOST",
        help="Target server IP address",
    )

    # Server options
    server = parser.add_argument_group("Server Options")
    server.add_argument(
        "--ssh-user",
        default="root",
        metavar="USER",
        help="SSH user for server connection (default: root)",
    )
    server.add_argument(
        "--skip-install",
        action="store_true",
        help="Skip Hop3 installation (assume already installed)",
    )
    server.add_argument(
        "-l", "--local",
        action="store_true",
        dest="use_local_code",
        help="Sync local hop3-server code via rsync",
    )

    # Authentication
    auth = parser.add_argument_group("Authentication")
    auth.add_argument(
        "--admin-user",
        default="admin",
        metavar="USER",
        help="Admin username to create (default: admin)",
    )
    auth.add_argument(
        "--admin-email",
        default="admin@example.com",
        metavar="EMAIL",
        help="Admin email address (default: admin@example.com)",
    )
    auth.add_argument(
        "--admin-password",
        metavar="PWD",
        help="Admin password (auto-generated if not specified)",
    )

    # Demo execution
    execution = parser.add_argument_group("Demo Execution")
    execution.add_argument(
        "-k", "--keep",
        action="store_true",
        dest="no_cleanup",
        help="Keep deployed apps running after demo completes",
    )
    execution.add_argument(
        "-p", "--pause",
        type=float,
        default=0.5,
        metavar="SECS",
        help="Pause between demo steps in seconds (default: 0.5)",
    )
    execution.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show detailed output and stack traces",
    )

    # Information
    info = parser.add_argument_group("Information")
    info.add_argument(
        "-h", "--help",
        action="help",
        help="Show this help message and exit",
    )
    info.add_argument(
        "--list",
        action="store_true",
        help="List available built-in demos and exit",
    )

    # Positional arguments (demos)
    parser.add_argument(
        "demos",
        nargs="*",
        metavar="demo",
        help="Demo name(s) or path(s) to run",
    )

    return parser


def main() -> int:
    """Main entry point."""
    parser = create_parser()

    # Handle --list before requiring --host
    if "--list" in sys.argv:
        list_demos()
        return 0

    # Handle case where --host is not provided
    if "-H" not in sys.argv and "--host" not in sys.argv:
        if "-h" in sys.argv or "--help" in sys.argv:
            parser.print_help()
            return 0
        print_error("Missing required argument: --host HOST")
        print_info("Run with --help for usage information")
        return 2

    args = parser.parse_args()

    # Discover available built-in demos
    available_demos = discover_demos()

    # Process demo arguments
    demo_args = args.demos if args.demos else []

    # Handle 'all' keyword or empty list
    if not demo_args or (len(demo_args) == 1 and demo_args[0].lower() == "all"):
        demo_args = list(available_demos.keys())
        if not demo_args:
            print_error("No built-in demos found in demos/ directory")
            return 1

    # Resolve all demo arguments
    demos_to_run: list[tuple[str, Path, bool]] = []
    for demo_arg in demo_args:
        # Skip 'all' if mixed with other args
        if demo_arg.lower() == "all":
            continue

        name, demo_dir, is_generic = resolve_demo(demo_arg)
        if demo_dir is None:
            print_error(f"Demo not found: '{demo_arg}'")
            print_info("Use --list to see available built-in demos")
            print_info("Or specify a path to a Hop3 application directory")
            return 2

        demos_to_run.append((name, demo_dir, is_generic))

    if not demos_to_run:
        print_error("No valid demos specified")
        return 2

    # Generate password if not provided
    admin_password = args.admin_password or secrets.token_urlsafe(16)

    # Create context
    ctx = DemoContext(
        server_ip=args.host,
        ssh_user=args.ssh_user,
        admin_user=args.admin_user,
        admin_email=args.admin_email,
        admin_password=admin_password,
        pause_between_steps=args.pause,
        skip_install=args.skip_install,
        no_cleanup=args.no_cleanup,
        use_local_code=args.use_local_code,
        verbose=args.verbose,
    )

    # Print banner and config
    print_banner()
    demo_names = [name for name, _, _ in demos_to_run]
    print_config(ctx, demo_names)

    try:
        # Phase 1: Prerequisites
        from lib.server import (
            check_hop3_installed,
            check_ubuntu_version,
            install_hop3,
            update_hop3_server,
            verify_ssh_access,
        )

        print_header("Phase 1: Prerequisites")

        verify_ssh_access(ctx)
        pause(ctx.pause_between_steps)

        check_ubuntu_version(ctx)
        pause(ctx.pause_between_steps)

        hop3_installed = check_hop3_installed(ctx)

        if not hop3_installed and not ctx.skip_install:
            install_hop3(ctx)
        elif hop3_installed:
            # Update to latest code
            update_hop3_server(ctx)
        elif ctx.skip_install:
            print_error("Hop3 is not installed and --skip-install was specified")
            return 1

        pause(ctx.pause_between_steps)

        # Phase 2: Configure CLI
        configure_cli(ctx)
        pause(ctx.pause_between_steps)

        # Phase 3: Run demos
        results = {}
        for name, demo_dir, is_generic in demos_to_run:
            success = run_demo(ctx, name, demo_dir, is_generic)
            results[name] = success
            pause(ctx.pause_between_steps)

        # Summary
        print_header("Demo Summary")
        all_passed = all(results.values())

        for demo_name, passed in results.items():
            status = (
                f"{Colors.GREEN}PASS{Colors.RESET}"
                if passed
                else f"{Colors.RED}FAIL{Colors.RESET}"
            )
            print(f"  [{status}] {demo_name}")

        print()
        if all_passed:
            print_success("All demos completed successfully!")
            if ctx.no_cleanup:
                print()
                print("  Admin credentials:")
                print(f"    Username: {ctx.admin_user}")
                print(f"    Password: {ctx.admin_password}")
        else:
            print_error("Some demos failed")
            return 1

        return 0

    except KeyboardInterrupt:
        print()
        print_error("Demo interrupted by user")
        return 130


if __name__ == "__main__":
    sys.exit(main())
