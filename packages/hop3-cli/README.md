# hop3-cli

This subproject provides a command-line interface for the hop3 project.

## Current Implementation

The basically just does a ssh connection to the server, with the command to be executed as an argument, and prints the output.

## Future Implementation

The CLI will interact with the `hop3-server` subproject, which will provide the API endpoints for the CLI.

There is already a basic implementation, but it needs to be revised and improved.

## TODO

- [ ] Implement an "hop init" or "hop seed" to create a new hop3 project with default settings.
- [ ] Revise the communication protocol between the CLI and the server.
- [ ] Implement the CLI as a minimalistic client where most of the presentation logic is handled by the server.
