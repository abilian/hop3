#!/usr/bin/env python3
import subprocess


def main():
    cmd = "ssh root@ssh.hop3.abilian.com rm -rf /home/hop3"
    subprocess.run(cmd, shell=True, check=True)

    cmd = "make install"
    subprocess.run(cmd, shell=True, check=True)

    cmd = "make test-e2e"
    subprocess.run(cmd, shell=True, check=True)


if __name__ == "__main__":
    main()
