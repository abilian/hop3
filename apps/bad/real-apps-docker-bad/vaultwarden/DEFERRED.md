# Vaultwarden (Docker & Native) — deferred

**Reason:** Vaultwarden upstream ships only Docker images — no prebuilt binaries for any platform. Building from source takes a full Rust release compile (~20–30 min), which exceeds both the Hop3 Docker builder's hardcoded 10-minute build timeout (`packages/hop3-server/src/hop3/plugins/build/nix/builder.py:303`) and the practical time budget for a native test deploy.

The native variant also requires the Rust toolchain (rustup / cargo) to be pre-installed on the Hop3 server; the current installer doesn't provision it, so `cargo build` is skipped and `target/release/vaultwarden` is never produced.

**Working variants (kept):**

- `apps/real-apps-nix/vaultwarden/` — hand-crafted `hop3.nix`, wraps `pkgs.vaultwarden` + `pkgs.vaultwarden.passthru.webvault`. nixpkgs has already done the compile, so this is fast and reproducible.

**Deferred variants (here):**

- `apps/bad/real-apps-docker-bad/vaultwarden/` — multi-stage Dockerfile that compiles from source. Blocked on the 10-min docker-build cap.
- `apps/bad/real-apps-native-bad/vaultwarden/` — native build. Blocked on missing Rust toolchain on the Hop3 server.

**Unblockers (in priority order):**

1. Teach `hop3-installer` to provision a Rust toolchain (or rustup) on demand. That revives the native variant immediately.
2. Make the Docker builder timeout tier-aware (fast=5m, medium=10m, slow=20m, very-slow=30m) to match the deploy timeout already landed in W16. That revives the Docker variant.
3. Alternative: add a "copy binary out of pkgs.vaultwarden" path to the Docker/native variants — but this blurs the variant boundaries and loses the "compile from source" property we want to exercise.
