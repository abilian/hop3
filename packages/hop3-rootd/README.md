# hop3-rootd

Privileged-operations agent for Hop3. Runs as root; exposes a narrow control-plane API to `hop3-server` (running unprivileged as the `hop3` user) over a Unix domain socket.

See `notes/adrs/041-privileged-operations-agent.md` for the design rationale and `notes/adrs/040-network-firewall-and-port-exposure.md` for the firewall integration that motivated v1's op set.

## What this is

`hop3-rootd` is the kernel-boundary executor for Hop3's runtime privileged actions. The unprivileged `hop3-server` reaches it via a Unix socket; rootd validates each request structurally, applies the privileged action (nftables mutation, nginx reload, etc.), and returns a typed result.

In v1 the operations are:

- `firewall.add_rule`, `firewall.remove_rule`, `firewall.list_rules` — manage rules in a dedicated `inet hop3` nftables table.
- `nginx.reload`, `nginx.validate_config` — wrap the privileged nginx commands previously granted to `hop3-server` via `/etc/sudoers.d/hop3` (now retired).
- `daemon.health`, `daemon.handshake` — introspection.

## What this is not

- A policy enforcement layer. SO_PEERCRED admits the `hop3` user; structural validation rejects malformed requests. There is no per-op authorization, no policy file. Operator-level "did you mean this?" prompts live in `hop3 deploy`, not in rootd.
- A general-purpose privileged-shell daemon. Rootd never accepts shell strings; every operation is a typed intent with a fixed argument schema.

## Deployment

`hop3-rootd` ships as a stdlib-only Python package and is installed by `hop3-installer` alongside `hop3-server`. It runs as a hardened systemd unit (full ProtectX suite, `CapabilityBoundingSet=CAP_NET_ADMIN`, syscall filter, resource limits). The socket is at `/run/hop3-rootd/socket`, mode `0660`, group `hop3`.

## Development

```bash
# Run unit tests (no privileges needed)
pytest tests/a_unit/ -v

# Run integration tests (requires root + nftables)
sudo pytest tests/b_integration/ -v

# Lint
ruff check src tests
ruff format src tests
```

## License

Apache-2.0 — Copyright (c) 2026, Abilian SAS
