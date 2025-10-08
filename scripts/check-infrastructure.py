#!/usr/bin/env python3
"""Quick test to verify E2E infrastructure is working."""

import subprocess
import time
import docker


def check_infrastructure():
    """Test that the E2E infrastructure can make RPC calls successfully."""
    print("Starting E2E infrastructure test...")

    # Start a container
    client = docker.from_env()

    print("Starting container...")
    container = client.containers.run(
        "hop3-e2e:test",
        detach=True,
        ports={
            "22/tcp": None,
            "8000/tcp": None,
        },
    )

    try:
        time.sleep(5)
        container.reload()

        # Get ports
        ports = container.attrs["NetworkSettings"]["Ports"]
        ssh_port = ports["22/tcp"][0]["HostPort"]

        # Get SSH key
        ssh_key_result = container.exec_run("cat /home/hop3/.ssh/id_rsa")
        ssh_key = ssh_key_result.output.decode()

        # Save SSH key
        import tempfile
        from pathlib import Path
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.pem') as f:
            f.write(ssh_key)
            ssh_key_path = f.name

        Path(ssh_key_path).chmod(0o600)

        # Wait for server
        print("Waiting for server...")
        time.sleep(10)

        # Test RPC call
        print(f"Testing RPC call via SSH tunnel (port {ssh_port})...")
        env = {
            "HOP3_API_URL": f"ssh://hop3@localhost:{ssh_port}",
            "HOP3_SSH_KEY": ssh_key_path,
        }

        result = subprocess.run(
            ["hop3", "apps"],
            capture_output=True,
            text=True,
            env={**subprocess.os.environ, **env},
            timeout=10,
        )

        print(f"Return code: {result.returncode}")
        print(f"Stdout: {result.stdout}")
        print(f"Stderr: {result.stderr}")

        if result.returncode == 0:
            print("\n✅ SUCCESS! E2E infrastructure is working correctly!")
            print("   - SSH tunnel established")
            print("   - RPC communication succeeded")
            print("   - Server responded to 'apps' command")
            return True
        else:
            print("\n❌ FAILED! RPC call returned non-zero exit code")
            return False

    finally:
        print("\nCleaning up...")
        container.stop(timeout=5)
        container.remove()
        Path(ssh_key_path).unlink(missing_ok=True)
        print("Done!")


if __name__ == "__main__":
    success = check_infrastructure()
    exit(0 if success else 1)
