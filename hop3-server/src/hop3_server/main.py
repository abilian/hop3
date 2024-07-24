# Copyright (c) 2023-2024, Abilian SAS

from hop3_server.rpc.service import Hop3Service
from rpyc.utils.server import ThreadedServer

# Temporary port for testing
PORT = 18080


def main():
    print("Starting Hop3 server...")
    t = ThreadedServer(Hop3Service, port=PORT)
    t.start()


if __name__ == "__main__":
    main()
