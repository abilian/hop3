# Vaultwarden native — deferred

See `apps/bad/real-apps-docker-bad/vaultwarden/DEFERRED.md` for the full explanation. Short version: upstream ships no prebuilt binaries, the Hop3 installer does not provision a Rust toolchain on the server, so `cargo build` is skipped and `target/release/vaultwarden` never exists. Unblocked by teaching `hop3-installer` to provision rustup.
