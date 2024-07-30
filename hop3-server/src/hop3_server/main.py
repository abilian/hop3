# Copyright (c) 2023-2024, Abilian SAS

from __future__ import annotations

import subprocess
import sys

import watchfiles
from hop3_server.rpc.service import Hop3Service
from rpyc.utils.server import ThreadedServer

# Temporary port for testing
PORT = 18080


def main():
    print("Starting Hop3 server...")
    t = ThreadedServer(Hop3Service, port=PORT)
    t.start()


def start_server() -> subprocess.Popen:
    # Start the server process
    return subprocess.Popen(["python", "-m", "hop3_server.main"])


def restart_server(server_process: subprocess.Popen) -> subprocess.Popen:
    # Terminate the current server process
    server_process.terminate()
    server_process.wait()
    # Start a new server process
    return start_server()


def watch():
    server_process = start_server()
    try:
        for changes in watchfiles.watch("./"):
            for change in changes:
                if change[1].endswith(".py"):
                    print(f"File {change[1]} changed, restarting server.")
                    server_process = restart_server(server_process)
    except KeyboardInterrupt:
        pass
    finally:
        server_process.terminate()


if __name__ == "__main__":
    if "-w" in sys.argv[1:]:
        print("Watching for changes...")
        watch()
    else:
        main()
