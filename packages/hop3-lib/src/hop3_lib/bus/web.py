# Copyright (c) 2023-2024, Abilian SAS

from flask import Flask, jsonify, request
from hop3_lib.bus.bus import (
    HelloWasSaidEvent,
    SayHelloCommand,
    SayHelloListener,
    TransactionalCommandBus,
    TransactionalSayHelloHandler,
)
from hop3_lib.bus.event_store import EventBusWithStore, EventStore

app = Flask(__name__)


@app.route("/api/command/dispatch", methods=["POST"])
def dispatch_command():
    command_data = request.json
    command_name = request.args.get("command")
    command = globals()[command_name](**command_data)
    command_bus.dispatch(command)
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    event_bus = EventBusWithStore(EventStore())
    command_bus = TransactionalCommandBus(event_bus)
    command_bus.register_handler(
        SayHelloCommand,
        TransactionalSayHelloHandler(event_bus, command_bus.event_buffer).handle,
    )
    event_bus.register_listener(HelloWasSaidEvent, SayHelloListener().on_hello_was_said)

    app.run()
