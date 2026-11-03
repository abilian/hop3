# ADR 065: Workload Identity

- **Status**: Draft
- **Type**: Feature
- **Created**: 2026-10-27
- **Revised**: 2026-10-28 (per-app users from Hop3 0.9 identify native callers; no leases), 2026-10-29 (what enrolment hands over, the `rotate` message, the operator's key bound to an account and a role, the derivation audit as an open question)
- **Related-ADRs**: [017](./017-agent-based-architecture.md) (the phases; this ADR details Phase 2), [041](./041-privileged-operations-agent.md) (the privileged helper; §17 covers agents), [048](./048-server-config-and-secret-storage.md) (the server's secret directory), [055](./055-app-runtime-uid-separation.md) (per-app users), [061](./061-standard-roles-and-rpc-authorization.md) (the roles that allow an operator's operations), [063](./063-identity-layer.md) (the identity layer and the sign-in socket), [067](./067-microvm-execution-backend.md) (the micro-VM backend), [068](./068-guest-networking.md) (how a guest reaches addons, and the private network between servers), [069](./069-worker-servers.md) (worker servers and placement: the operations in the envelope)

## Context

This ADR details the identity of worker servers in [ADR 017](./017-agent-based-architecture.md)'s Phase 2, where a primary holds the control plane and worker servers run workers. It also details the identity of apps that call the platform, which the micro-VM backend makes checkable. The identity layer (ADR 063) knows which person is signing in; the platform does not yet know which workload is speaking to it.

**Apps.** Until Hop3 0.9, every native app ran as the same system user, so the addons and the privileged helper took the app's name on trust. The sign-in socket of ADR 063 would have done the same. From 0.9, each app runs under its own Unix user (ADR 055): on a Unix socket, the peer's credentials identify a native caller. An app in a micro-VM (ADR 067) has no Unix user on the host. A Unix socket does not cross a kernel boundary either. A guest reaches the addons it declared over the tap network, by firewall rules (ADR 068). It reaches the platform services (the sign-in socket, the guest agent) over vsock, which this ADR covers.

**Worker servers and the operator.** On a platform with worker servers (ADR 069), the control plane on the primary instructs each worker server to start and stop workers. The worker server reports their state. The operator's CLI sends commands to the control plane. The receiver of an instruction or a command must know who sends it, whether that sender may ask for this operation, and that the request is fresh and unaltered. A worker server must also join the private network between servers (ADR 068), and only after the operator has enrolled it.

In both cases the identity must come from something the platform created, never from a claim inside the message.

## Decision

We propose the following.

### 1. An app is known by the endpoint the platform created for it

Each micro-VM gets one vsock device. Under Cloud Hypervisor, the host side of a guest's vsock is a Unix socket per VM and port, in the app's run directory: a guest reaches only the sockets of the VM it runs in. Under QEMU, the host side is the kernel's `vhost-vsock` and the context id (CID) is host-wide. The host reads the peer's CID on each connection. The platform allocates the CID and records which app holds it. Either way, the guest sends nothing that says who it is, and cannot choose the endpoint or the CID.

A platform service exposed to guests listens per VM (Cloud Hypervisor) or checks the peer CID against the app it was opened for (QEMU). A connection from any other guest is refused and logged.

### 2. A relay adds the caller and changes nothing else

The server's services keep their protocols. The sign-in socket keeps the Dovecot SASL protocol. Between a guest and such a service sits a relay that:

- admits a connection only from the guest it serves;
- tells the service which app is calling, out of band of the protocol, or opens the service's per-app endpoint;
- passes bytes through as they arrive, never splitting, joining or rewriting a reply, since clients may read a greeting in one call;
- drops what only the VM's own plumbing adds: a client address that is the guest's gateway is not a client, so it is not used for the per-client attempt budget of ADR 063 §5;
- accepts bursts of connections without refusing them.

A service reachable this way only by apps that declared it (the `sasl` addon for the sign-in socket) is closed to other guests, as natively the socket is closed to any Unix user but the declared services' (ADR 063 §5).

### 3. A guest keeps its app's paths

Apps expect a Unix socket at a path (Radicale's `dovecot_socket`). The guest's init should listen at the host's path and forward each connection over vsock, on the port the platform assigned to that service for that app, so the recipe and the app's configuration stay the same natively and in a VM.

### 4. Worker servers and the operator hold enrolled keys

Each server, the primary included, should hold an Ed25519 key pair, created by the installer, the private key readable only by the platform's user in the server's secret directory (ADR 048). The operator enrols a worker server once, on the primary, with the server's public key and a name. In the same step the worker server receives four things: the primary's public key, the public endpoint (address and port) of the primary's WireGuard interface, the primary's address on the private network, and the server's address there. Enrolment on the primary adds the server as a peer of the private network with the server's public endpoint (ADR 068 §8). The server then brings up the tunnel. Its first message on it is `enrol` (ADR 069 §1). That message states the server's distribution release, which must equal the primary's, since a native release depends on the host's runtimes (ADR 069 §2). A mismatch stops the enrolment, with a diagnosis naming both releases.

The worker server uses the same key on the private network. The WireGuard key is derived from it (the Ed25519 to X25519 conversion libsodium provides), so enrolling the server admits it to the network and removing the enrolment takes it out (ADR 068).

A server's role fixes what it may send; no allow-list is enrolled for it. The control plane instructs; a worker server accepts instructions signed by the primary's key only. A worker server reports to the control plane and never instructs another server. Its reports travel over the private network, where the key that admitted it identifies it.

The operator's CLI holds a key pair on the operator's machine, enrolled on the primary against the operator's account. It signs each command it sends (§5). The control plane checks an operator's command as a worker server checks an instruction, and allows an operation by the role of that account (ADR 061): an enrolled key adds no authority beyond the account's.

### 5. A canonical signed envelope

An instruction from the control plane or a command from the operator's CLI is a canonical JSON payload (sorted keys, UTF-8, no insignificant whitespace) with fields `from`, `to`, `op`, `args`, `issued_at` and `nonce`, and a detached signature over those bytes. The receiver checks, in this order, and stops at the first failure with a reason it logs and returns:

1. the signer is enrolled;
2. the signature verifies, before the payload is parsed;
3. `from` equals the signer's enrolled name;
4. `to` is this server;
5. `op` is allowed for the signer: by role for the control plane, by the role of the enrolled account for an operator (ADR 061);
6. `issued_at` is within the time window (60 s by default);
7. `nonce` has not been seen within the window, recorded before the operation runs.

The envelope is the same for every operation; ADR 069 defines the operations and their arguments.

### 6. Key rotation and removal

A server or the operator rotates a key by sending the new public key, signed by the old one, in the `rotate` message of ADR 069 §1 or in a CLI command; receivers accept both for a stated overlap, then only the new one. On a server, the privileged helper writes the new key pair into the secret directory, since the platform's user cannot write there (ADR 048). A worker server's new key also gives it a new WireGuard key. Removing a worker server or an operator deletes the enrolment on the primary and, for a server, the peer on the private network; messages from that sender are refused from then on. An enrolment may have an expiry date.

### 7. Clocks

The window assumes synchronised clocks. Each worker server reports its clock offset to the control plane in each `report` (ADR 069 §1). A receiver whose offset to a signer exceeds half the window refuses with a diagnosis that names the clock. The operator's CLI reports no offset; a command refused as stale gets the same diagnosis, so the operator corrects the machine's clock. Time synchronisation (systemd-timesyncd or chrony) should be an installer prerequisite on the primary and the worker servers.

### 8. Privilege stays local

Workload identity authorises a request; it grants no privilege. An instruction a worker server accepts runs as the platform's user there. Any privileged step goes through that server's own privileged helper (ADR 041).

## Acceptance

- A guest connecting to a service it did not declare is refused; a guest cannot reach another app's service endpoint; a forged app name inside the protocol does not change who the service sees.
- A burst of concurrent sign-ins through a guest succeeds as natively.
- Each check of §5 refuses its case with a distinct reason: altered payload, unknown signer, signer claiming another name, wrong addressee, operation not allowed, stale message, replayed nonce.
- A worker server refuses an instruction signed by any key but the primary's; a server the operator did not enrol cannot join the private network.
- Enrolling a worker server whose distribution release differs from the primary's stops with a diagnosis naming both releases.
- A rotated key is accepted during the overlap and refused after. A removed worker server's or operator's key fails the first check of §5, and the removed server leaves the private network. A command from the operator's CLI passes the same checks as an instruction from the control plane.
- Each property above has failed its test once under a planted regression.

## Consequences

### Positive

- The platform's services stop trusting an app's word, without changing any protocol or any app.
- One envelope and one check order serve the control plane's instructions and the operator's commands.
- One enrolled key admits a worker server both to the control plane's protocol and to the private network, with no certificate authority to run.

### Negative

- A relay per service per VM: more sockets and processes, each to tear down with the app.
- Servers need synchronised clocks, and each receiver a nonce store bounded by the window.
- Each worker server takes one operator step to join.

## Alternatives considered

- **Peer credentials only (`SO_PEERCRED`)** work natively with per-app users (ADR 055) but do not cross into a VM. They are kept for native apps; vsock is the counterpart for guests.
- **Mutual TLS with a platform CA** is standard and widely tooled. It costs a CA to run, protect and rotate, which a small operator will not do. An operator who already runs a CA would change this choice.
- **Tokens issued by the identity layer to workloads** (SPIFFE-style) fit OIDC-speaking services. They cost an issuer every guest must reach and a token lifetime to manage. Platform services that speak HTTP rather than socket protocols would change this choice.

## Open questions

1. **CID checks under QEMU.** Under the QEMU fallback, whether checking the peer's CID gives the same guarantee as per-VM sockets. Decided with ADR 067's open question on monitor parity.
2. **One key for two uses.** Deriving the WireGuard key from the signing key keeps one key per server; two keys bound by one enrolment avoid using one secret with two algorithms. Decided by a security audit of the derivation, before the private network (ADR 068) is built on it.
3. **Nonce store.** In memory with a window, or persisted, and how large it grows under load. Decided by measurements under load.
4. **Keys narrower than their account.** Whether an enrolled key may be limited to part of the account's operations, for a key kept on a build machine. Decided by the first operator who asks for one.
