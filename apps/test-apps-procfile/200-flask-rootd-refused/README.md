# 200-flask-rootd-refused

An app connects to hop3-rootd's socket and asks for its handshake. It must be refused: apps share the `hop3` uid with the control plane until ADR 055's per-app users, so rootd tells them apart by where the caller runs (the `uwsgi-hop3` cgroup, or the uWSGI Emperor's descendants on a host without systemd).
