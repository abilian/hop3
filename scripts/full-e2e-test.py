#!/usr/bin/env python3
import subprocess


def main():
    cmd = "ssh root@ssh.hop.abilian.com rm -rf /home/hop3"
    subprocess.run(cmd, shell=True, check=True)

    cmd = "make deploy"
    subprocess.run(cmd, shell=True, check=True)

    cmd = "hop-test --ff"
    subprocess.run(cmd, shell=True, check=True)


if __name__ == "__main__":
    main()
