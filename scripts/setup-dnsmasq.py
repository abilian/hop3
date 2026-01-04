#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Setup dnsmasq for wildcard DNS resolution of *.hop3.local on macOS.

This script configures dnsmasq to resolve all *.hop3.local addresses
to a specified server IP, enabling local development and testing
with wildcard subdomains.

Usage:
    ./setup-dnsmasq.py <server-ip-or-hostname>

Examples:
    ./setup-dnsmasq.py 192.168.1.100
    ./setup-dnsmasq.py hop3.local
    ./setup-dnsmasq.py myserver.example.com
"""

from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

DOMAIN = "hop3.local"
DOCKER_DOMAIN = "hop3-docker.local"


def get_brew_prefix() -> Path:
    """Get the Homebrew prefix directory."""
    result = subprocess.run(
        ["brew", "--prefix"],
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(result.stdout.strip())


def resolve_to_ip(host: str) -> str:
    """Resolve a hostname to an IP address.

    If the input is already an IP address, return it as-is.
    """
    # Check if it's already an IP address
    ip_pattern = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")
    if ip_pattern.match(host):
        # Validate IP address
        try:
            socket.inet_aton(host)
            return host
        except OSError:
            raise ValueError(f"Invalid IP address: {host}")

    # Resolve hostname to IP
    try:
        ip = socket.gethostbyname(host)
        print(f"Resolved '{host}' to {ip}")
        return ip
    except socket.gaierror as e:
        raise ValueError(f"Could not resolve hostname '{host}': {e}")


def run_sudo(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a command with sudo."""
    return subprocess.run(
        ["sudo"] + args,
        capture_output=True,
        text=True,
        check=check,
    )


def write_file_sudo(path: Path, content: str, append: bool = False) -> None:
    """Write content to a file using sudo."""
    mode = "-a" if append else ""
    # Use tee to write with sudo privileges
    cmd = ["sudo", "tee"]
    if append:
        cmd.append("-a")
    cmd.append(str(path))

    subprocess.run(
        cmd,
        input=content,
        capture_output=True,
        text=True,
        check=True,
    )


def file_contains_line(path: Path, pattern: str) -> bool:
    """Check if a file contains a line matching the pattern."""
    if not path.exists():
        return False
    content = path.read_text()
    return bool(re.search(pattern, content, re.MULTILINE))


def ensure_config_line(
    path: Path, pattern: str, line: str, comment: str | None = None
) -> bool:
    """Ensure a configuration line exists in a file.

    Returns True if the line was added, False if it already existed.
    """
    if file_contains_line(path, pattern):
        print(f"  Already configured: {line}")
        return False

    content = ""
    if comment:
        content += f"\n# {comment}\n"
    content += f"{line}\n"

    write_file_sudo(path, content, append=True)
    print(f"  Added: {line}")
    return True


def stop_dnsmasq() -> None:
    """Stop any running dnsmasq processes."""
    subprocess.run(
        ["sudo", "pkill", "-x", "dnsmasq"],
        capture_output=True,
        check=False,
    )
    time.sleep(1)


def start_dnsmasq(dnsmasq_bin: Path) -> bool:
    """Start dnsmasq and verify it's running.

    Returns True if dnsmasq started successfully.
    """
    # Try to start dnsmasq directly
    result = subprocess.run(
        ["sudo", str(dnsmasq_bin)],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        print(f"  Warning: dnsmasq start returned: {result.stderr.strip()}")

    # Give it a moment to start
    time.sleep(1)

    # Verify it's running
    return is_dnsmasq_running()


def is_dnsmasq_running() -> bool:
    """Check if dnsmasq is listening on port 53."""
    result = subprocess.run(
        ["sudo", "lsof", "-i", ":53"],
        capture_output=True,
        text=True,
        check=False,
    )
    return "dnsmasq" in result.stdout


def test_dns_resolution(domain: str, expected_ip: str) -> bool:
    """Test if DNS resolution works correctly."""
    if not shutil.which("dig"):
        print("  dig not found, skipping DNS test")
        return True

    result = subprocess.run(
        ["dig", "+short", f"test.{domain}", "@127.0.0.1"],
        capture_output=True,
        text=True,
        check=False,
    )

    resolved_ip = result.stdout.strip()
    return resolved_ip == expected_ip


def setup_dnsmasq(server_ip: str) -> bool:
    """Configure dnsmasq for wildcard DNS resolution.

    Returns True if setup was successful.
    """
    print(f"\n=== dnsmasq Setup for *.{DOMAIN} ===\n")
    print(f"Server IP: {server_ip}")

    # Get paths
    brew_prefix = get_brew_prefix()
    print(f"Homebrew prefix: {brew_prefix}\n")

    dnsmasq_bin = brew_prefix / "opt/dnsmasq/sbin/dnsmasq"
    dnsmasq_conf = brew_prefix / "etc/dnsmasq.conf"
    dnsmasq_conf_dir = brew_prefix / "etc/dnsmasq.d"
    hop3_conf = dnsmasq_conf_dir / "hop3.conf"
    resolver_dir = Path("/etc/resolver")
    resolver_file = resolver_dir / DOMAIN

    # Verify dnsmasq is installed
    if not dnsmasq_bin.exists():
        print(f"Error: dnsmasq binary not found at {dnsmasq_bin}")
        print("Install it with: brew install dnsmasq")
        return False

    # Create dnsmasq.d directory
    print(f"Creating {dnsmasq_conf_dir}...")
    run_sudo(["mkdir", "-p", str(dnsmasq_conf_dir)])

    # Configure dnsmasq.conf
    print(f"\nConfiguring {dnsmasq_conf}...")

    ensure_config_line(
        dnsmasq_conf,
        rf"^conf-dir={re.escape(str(dnsmasq_conf_dir))}",
        f"conf-dir={dnsmasq_conf_dir}/,*.conf",
        "Include additional config files",
    )

    ensure_config_line(
        dnsmasq_conf,
        r"^listen-address=127\.0\.0\.1",
        "listen-address=127.0.0.1",
        "Listen on localhost",
    )

    # Create hop3.local wildcard config (for remote testing)
    # and hop3-docker.local (for Docker testing)
    print(f"\nCreating {hop3_conf}...")
    hop3_config_content = f"""# Wildcard DNS for Hop3 testing
# Generated by setup-dnsmasq.py

# Remote server testing: *.{DOMAIN} -> {server_ip}
address=/{DOMAIN}/{server_ip}

# Docker testing: *.{DOCKER_DOMAIN} -> 127.0.0.1
address=/{DOCKER_DOMAIN}/127.0.0.1
"""
    write_file_sudo(hop3_conf, hop3_config_content, append=False)
    print(f"  Configured *.{DOMAIN} -> {server_ip}")
    print(f"  Configured *.{DOCKER_DOMAIN} -> 127.0.0.1")

    # Create resolver directory and files for both domains
    print(f"\nConfiguring macOS resolver...")
    run_sudo(["mkdir", "-p", str(resolver_dir)])

    resolver_content = """# DNS resolver for Hop3
# Generated by setup-dnsmasq.py
nameserver 127.0.0.1
"""
    # Create resolver for hop3.local
    write_file_sudo(resolver_file, resolver_content, append=False)
    print(f"  Created {resolver_file}")

    # Create resolver for hop3-docker.local
    docker_resolver_file = resolver_dir / DOCKER_DOMAIN
    write_file_sudo(docker_resolver_file, resolver_content, append=False)
    print(f"  Created {docker_resolver_file}")

    # Restart dnsmasq
    print("\nRestarting dnsmasq...")
    stop_dnsmasq()

    if not start_dnsmasq(dnsmasq_bin):
        print("Error: Failed to start dnsmasq")
        print(f"Try running manually: sudo {dnsmasq_bin}")
        return False

    print("  dnsmasq is running on port 53")

    # Test the configuration
    print("\n=== Testing Configuration ===\n")

    print(f"Testing: dig test.{DOMAIN} @127.0.0.1")
    if test_dns_resolution(DOMAIN, server_ip):
        print(f"✓ dnsmasq is resolving *.{DOMAIN} to {server_ip}")
    else:
        print(f"✗ DNS resolution test failed")
        return False

    # Print success message
    print(f"""
=== Setup Complete ===

DNS configuration:
  *.{DOMAIN} -> {server_ip} (for remote/SSH testing)
  *.{DOCKER_DOMAIN} -> 127.0.0.1 (for Docker testing)

To verify:
  dig test.{DOMAIN} @127.0.0.1
  dig test.{DOCKER_DOMAIN} @127.0.0.1

Usage:
  # For remote testing (default):
  python scripts/run-all-tutorials.py

  # For Docker testing:
  HOP3_TEST_DOMAIN={DOCKER_DOMAIN} python scripts/run-all-tutorials.py

NOTE: dnsmasq must be started manually after reboot:
  sudo {dnsmasq_bin}

To undo this setup:
  sudo pkill dnsmasq
  sudo rm {hop3_conf}
  sudo rm {resolver_file}
  sudo rm {docker_resolver_file}
""")

    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description=f"Setup dnsmasq for wildcard DNS resolution of *.{DOMAIN}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s 192.168.1.100       # Use IP address directly
  %(prog)s hop3.local          # Resolve hostname to IP
  %(prog)s myserver.example.com
""",
    )
    parser.add_argument(
        "server",
        help="Server IP address or hostname to resolve *.hop3.local to",
    )
    args = parser.parse_args()

    # Check platform
    if platform.system() != "Darwin":
        print("Error: This script is for macOS only.")
        return 1

    # Check if dnsmasq is installed
    if not shutil.which("dnsmasq"):
        print("Error: dnsmasq is not installed.")
        print("Install it with: brew install dnsmasq")
        return 1

    # Resolve server to IP address
    try:
        server_ip = resolve_to_ip(args.server)
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    # Run setup
    try:
        success = setup_dnsmasq(server_ip)
        return 0 if success else 1
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {e.cmd}")
        if e.stderr:
            print(f"  {e.stderr.strip()}")
        return 1
    except PermissionError as e:
        print(f"Permission error: {e}")
        print("This script requires sudo privileges.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
