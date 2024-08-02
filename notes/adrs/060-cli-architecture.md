# ADR: CLI<->Server Communication

Status: Accepted

## Introduction

This ADR addresses the architecture of the communication protocol between the Command-Line Interface (CLI) and the server for the Hop3 project. The chosen approach aims to simplify the CLI by implementing both the logic and formatting on the server, while the CLI will focus on handling user input and presenting responses based on server instructions.

## Summary

The decision is to use a "dumb" CLI, where the server manages both the logic and formatting of responses. Communication between the CLI and the server will use a simple RPC mechanism, specifically JSON-RPC, over HTTPS. The server will use ad-hoc certificates for security.

## Context and Goals

### Context

The current requirement is to develop an efficient and secure communication protocol between the CLI and the server. The CLI should be lightweight, with minimal processing and logic, allowing for easier updates and maintenance. By offloading the logic and formatting to the server, we can centralize the control and simplify the CLI's implementation.

### Goals

- Implement a lightweight and maintainable CLI.
- Centralize the business logic and formatting on the server.
- Ensure secure communication between the CLI and the server.
- Provide a simple and efficient protocol for communication.
- Allow for future scalability and easy updates to the CLI.
- Support streaming responses for real-time data and file transfers.

## Tenets

- **Simplicity**: Keep the CLI implementation as simple as possible.
- **Centralized Logic**: All logic and formatting are managed on the server.
- **Security**: Ensure secure communication using HTTPS.
- **Scalability**: Design the system to be scalable and easy to update.
- **Real-Time Capability**: Support streaming responses for commands requiring real-time data or large file transfers.

## Decision

We will implement a JSON-RPC protocol over HTTPS for the communication between the CLI and the server. The server will handle all business logic and formatting, sending formatted instructions to the CLI, which will then present the results to the user. The server will use ad-hoc certificates to secure the communication. Additionally, we will implement support for streaming responses to handle real-time data needs such as log tailing and file downloads.

## Consequences

### Benefits

- **Simplified CLI**: The CLI will be lightweight and easy to maintain.
- **Centralized Management**: All updates to logic and most updates to formatting can be made on the server, reducing the need for frequent CLI updates.
- **Security**: HTTPS ensures secure communication, protecting data in transit.
- **Consistency**: Centralized formatting ensures a consistent user experience across different CLI instances.
- **Real-Time Data Handling**: Streaming support allows for real-time data operations and efficient file transfers.

### Drawbacks

- **Server Dependency**: The CLI is entirely dependent on the server for processing and formatting.
- **Initial Setup**: Setting up HTTPS with ad-hoc certificates may require additional initial configuration.
- **Complexity in Streaming Implementation**: Implementing streaming responses adds complexity to the server-side implementation.

## Lessons Learned

In a previous project (Nua), a "smart" CLI with embedded presentation logic proved difficult to maintain and update. Centralizing the logic and formatting on the server simplifies maintenance and ensures consistency across all CLI instances.

## Action Items

### Strategic Priorities

1. **Develop Server-Side Logic and Formatting**:
   - Implement the necessary business logic on the server.
   - Develop a robust formatting engine to prepare responses for the CLI.

2. **Implement JSON-RPC Protocol**:
   - Set up the JSON-RPC protocol on the server.
   - Ensure the CLI can send and receive JSON-RPC requests and responses.

3. **Configure HTTPS with Ad-Hoc Certificates**:
   - Set up HTTPS on the server.
   - Generate and configure ad-hoc certificates for secure communication.

4. **Develop and Test CLI**:
   - Implement the CLI to handle user input and display formatted responses.
   - Conduct thorough testing to ensure reliability and performance.

5. **Implement Streaming Support**:
   - Develop server-side support for streaming responses.
   - Ensure the CLI can handle and present streaming data effectively.

## Alternatives

- **RESTful API**: Using a RESTful API instead of JSON-RPC. This was rejected because JSON-RPC provides a simpler and more efficient protocol for our needs.
- **Smart CLI**: Embedding logic within the CLI. This was rejected due to the increased complexity and maintenance overhead.
- **Custom Protocol**: Developing a custom communication protocol (over sockets). This was rejected in favor of using a well-established standard like JSON-RPC and the fear that it might not play well with corporate firewalls.
- **ZeroMQ/NNG**: Using ZeroMQ or a ZeroMQ-like protocol for communication. This was rejected due to the additional complexity, lack of built-in security features, and the fear that it might not play well with corporate firewalls.
- **gRPC**: Using gRPC for communication. This was rejected due to the additional complexity and the need for protocol buffers.

## Related

- CLI commands overview (TODO)
- CLI API (TODO)

## References

- JSON-RPC 2.0 Specification: https://www.jsonrpc.org/specification

## Notes

Additional considerations include ensuring that the server is both lightweight and scalable and can handle multiple simultaneous connections efficiently. Future enhancements may involve automating certificate renewal and exploring advanced security measures.

## Appendix

- Example JSON-RPC request and response.
- Configuration scripts for setting up HTTPS with ad-hoc certificates.
