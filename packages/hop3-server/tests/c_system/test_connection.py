#!/usr/bin/env python3
# Copyright (c) 2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Simple script to test SSH connection before running system integration tests.

Run this first to verify your setup:
    python packages/hop3-server/tests/c_system/test_connection.py
"""

from __future__ import annotations

import os
import subprocess
import sys

E2E_SERVER = os.environ.get("HOP3_DEV_HOST")


def test_ssh_connection():
    """Test basic SSH connectivity."""
    print("=" * 60)
    print("Testing SSH connection...")
    print("=" * 60)

    if not E2E_SERVER:
        print("❌ ERROR: HOP3_DEV_HOST environment variable not set")
        print("   Please set it: export HOP3_DEV_HOST=hop3@your-server.com")
        if __name__ != "__main__":
            msg = "HOP3_DEV_HOST not set"
            raise AssertionError(msg)
        return False

    print(f"Server: {E2E_SERVER}")

    # Extract user@host from server
    if "@" in E2E_SERVER:
        user_host = E2E_SERVER
    else:
        user_host = f"root@{E2E_SERVER}"

    print(f"\n1. Testing SSH connection to {user_host}...")
    try:
        result = subprocess.run(
            [
                "ssh",
                "-o",
                "ConnectTimeout=10",
                user_host,
                "echo",
                "Connection successful",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )

        if result.returncode == 0:
            print("   ✓ SSH connection successful")
            print(f"   Output: {result.stdout.strip()}")
            return True
        print("   ❌ SSH connection failed")
        print(f"   stderr: {result.stderr}")
        if __name__ != "__main__":
            msg = f"SSH connection failed: {result.stderr}"
            raise AssertionError(msg)
        return False

    except subprocess.TimeoutExpired:
        print("   ❌ SSH connection timed out after 15 seconds")
        print("   Check:")
        print("   - Is the server running?")
        print("   - Can you SSH manually? Try: ssh", user_host)
        print("   - Are SSH keys set up correctly?")
        if __name__ != "__main__":
            msg = "SSH connection timed out"
            raise AssertionError(msg)
        return False
    except FileNotFoundError:
        print("   ❌ ssh command not found")
        print("   Please install OpenSSH client")
        if __name__ != "__main__":
            msg = "ssh command not found"
            raise AssertionError(msg)
        return False


def test_hop3_cli_available():
    """Test if hop3-cli is installed."""
    print("\n2. Testing hop3-cli availability...")

    try:
        result = subprocess.run(
            ["hop3", "--help"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0:
            print("   ✓ hop3-cli is installed")
            return True
        print("   ❌ hop3-cli returned error")
        print(f"   stderr: {result.stderr}")
        if __name__ != "__main__":
            msg = f"hop3-cli error: {result.stderr}"
            raise AssertionError(msg)
        return False

    except FileNotFoundError:
        print("   ❌ hop3 command not found")
        print("   Please install hop3-cli:")
        print("   pip install -e packages/hop3-cli")
        if __name__ != "__main__":
            msg = "hop3 command not found"
            raise AssertionError(msg)
        return False
    except subprocess.TimeoutExpired:
        print("   ❌ hop3 command timed out")
        if __name__ != "__main__":
            msg = "hop3 command timed out"
            raise AssertionError(msg)
        return False


def test_hop3_cli_connection():
    """Test hop3-cli connection to server."""
    print("\n3. Testing hop3-cli connection...")

    # Set API URL
    os.environ["HOP3_API_URL"] = f"ssh://{E2E_SERVER}"

    try:
        result = subprocess.run(
            ["hop3", "help"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            print("   ✓ hop3-cli can connect to server")
            print(f"   Output (first 200 chars): {result.stdout[:200]}")
            return True
        print("   ❌ hop3-cli connection failed")
        print(f"   stderr: {result.stderr}")
        print(f"   stdout: {result.stdout}")
        if __name__ != "__main__":
            msg = f"hop3-cli connection failed: {result.stderr}"
            raise AssertionError(msg)
        return False

    except subprocess.TimeoutExpired:
        print("   ❌ hop3 command timed out after 30 seconds")
        print("   This usually means:")
        print("   - SSH tunnel setup is hanging")
        print("   - Server is not responding")
        print("   - Firewall blocking connection")
        if __name__ != "__main__":
            msg = "hop3-cli connection timed out"
            raise AssertionError(msg)
        return False


def test_auth_commands_available():
    """Test if authentication commands are available on the server."""
    print("\n4. Testing authentication commands availability...")

    # Set API URL
    os.environ["HOP3_API_URL"] = f"ssh://{E2E_SERVER}"

    try:
        result = subprocess.run(
            ["hop3", "help"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if (
            "auth:" in result.stdout
            or "auth:register" in result.stdout
            or "auth:login" in result.stdout
        ):
            print("   ✓ Authentication commands are available")
            return True
        print("   ⚠️  Authentication commands NOT found in help output")
        print("   This means:")
        print("   - E2E tests will be skipped (they require authentication)")
        print("   - You can still test manually without authentication")
        return False

    except Exception as e:
        print(f"   ❌ Failed to check auth commands: {e}")
        return False


def test_auth_register_command():
    """Test if auth:register command works (with timeout check)."""
    print("\n5. Testing auth:register command (quick check)...")

    # Set API URL
    os.environ["HOP3_API_URL"] = f"ssh://{E2E_SERVER}"

    try:
        # Try with a very short timeout to see if command starts responding
        result = subprocess.run(
            [
                "hop3",
                "auth:register",
                "test-diagnostic-user",
                "test@example.com",
                "test-pass-12345",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,  # Only 10 seconds to see if it responds at all
        )

        if result.returncode == 0:
            print("   ✓ auth:register command works")
            print("   Note: User 'test-diagnostic-user' was created")
            return True
        if "already exists" in result.stdout + result.stderr:
            print("   ✓ auth:register command works (user already exists)")
            return True
        if "Authentication not enabled" in result.stdout + result.stderr:
            print("   ⚠️  Authentication is not enabled on the server")
            print("   To enable authentication, set on the server:")
            print("   export HOP3_ENABLE_AUTH=true")
            print("   export HOP3_SECRET_KEY=your-secret-key")
            return False
        print("   ❌ auth:register returned error")
        print(f"   stdout: {result.stdout}")
        print(f"   stderr: {result.stderr}")
        return False

    except subprocess.TimeoutExpired:
        print("   ❌ auth:register command timed out after 10 seconds")
        print("   This is the problem causing E2E tests to hang!")
        print("\n   Possible causes:")
        print("   1. Command is waiting for input (shouldn't happen with CLI)")
        print("   2. Server is hanging while processing the command")
        print("   3. Database connection issue on server")
        print("\n   To debug, try manually on the server:")
        print(f"   ssh {E2E_SERVER}")
        print("   hop-server --help  # Check if server is working")
        return False
    except Exception as e:
        print(f"   ❌ Unexpected error: {e}")
        return False


def test_auth_login_command():
    """Test if auth:login command works."""
    print("\n6. Testing auth:login command...")

    # Set API URL
    os.environ["HOP3_API_URL"] = f"ssh://{E2E_SERVER}"

    try:
        result = subprocess.run(
            ["hop3", "auth:login", "test-diagnostic-user", "test-pass-12345"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0 and "Your API token:" in result.stdout:
            print("   ✓ auth:login command works")
            # Extract token to verify format
            lines = result.stdout.split("\n")
            for i, line in enumerate(lines):
                if "Your API token:" in line and i + 1 < len(lines):
                    token = lines[i + 1].strip()
                    if token:
                        print(f"   Token extracted (first 20 chars): {token[:20]}...")
                        return True
            print("   ⚠️  Login succeeded but couldn't extract token")
            print(f"   stdout: {result.stdout[:300]}")
            return False
        print("   ❌ auth:login failed")
        print(f"   Exit code: {result.returncode}")
        print(f"   stdout: {result.stdout[:200]}")
        print(f"   stderr: {result.stderr[:200]}")
        print("\n   This is causing E2E tests to fail!")
        print("   Possible causes:")
        print("   1. Invalid credentials")
        print("   2. Server authentication issue")
        print("   3. RPC request format problem")
        return False

    except subprocess.TimeoutExpired:
        print("   ❌ auth:login timed out")
        return False
    except Exception as e:
        print(f"   ❌ Unexpected error: {e}")
        return False


def main():
    """Run all connection tests."""
    print("\n" + "=" * 60)
    print("Hop3 E2E Test Connection Diagnostic")
    print("=" * 60 + "\n")

    all_passed = True
    auth_available = True

    if not test_ssh_connection():
        all_passed = False

    if not test_hop3_cli_available():
        all_passed = False

    if not test_hop3_cli_connection():
        all_passed = False

    if not test_auth_commands_available():
        auth_available = False

    if auth_available and not test_auth_register_command():
        all_passed = False

    if auth_available and not test_auth_login_command():
        all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("✓ All checks passed! You can run E2E tests.")
        print("\nTo run E2E tests:")
        print("  pytest packages/hop3-server/tests/c_e2e/ -v -s")
    elif not auth_available:
        print("⚠️  Basic connectivity works, but authentication is not available.")
        print("\nYou can:")
        print("1. Enable authentication on the server (see instructions above)")
        print("2. Run E2E tests (they will skip tests requiring authentication)")
    else:
        print("❌ Some checks failed. Fix the issues above before running E2E tests.")
        sys.exit(1)
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
