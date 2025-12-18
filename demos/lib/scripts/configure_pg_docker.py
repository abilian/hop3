#!/usr/bin/env python3
# Copyright (c) 2025, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Configure PostgreSQL to accept connections from Docker containers.

Docker containers connect via host.docker.internal which routes to various IPs.
PostgreSQL must be configured to:
1. Listen on all interfaces (not just localhost)
2. Allow password auth from Docker networks (172.16.0.0/12 and 192.168.0.0/16)
"""

from pathlib import Path

# Find PostgreSQL config directory
pg_dirs = list(Path("/etc/postgresql").glob("*/main"))
if not pg_dirs:
    print("ERROR: PostgreSQL config directory not found")
    exit(1)

pg_conf_dir = pg_dirs[0]
pg_conf = pg_conf_dir / "postgresql.conf"
pg_hba = pg_conf_dir / "pg_hba.conf"

# Update listen_addresses
conf_content = pg_conf.read_text()
if "listen_addresses = '*'" not in conf_content:
    new_lines = []
    for line in conf_content.split("\n"):
        if line.strip().startswith("listen_addresses"):
            new_lines.append(f"# {line}  # commented by hop3")
        else:
            new_lines.append(line)
    new_lines.append("")
    new_lines.append("# Added by hop3 for Docker container access")
    new_lines.append("listen_addresses = '*'")
    pg_conf.write_text("\n".join(new_lines))
    print("Updated postgresql.conf: listen_addresses = '*'")

# Add pg_hba.conf rules for Docker networks
# 172.16.0.0/12 covers Docker bridge networks (172.16.x.x - 172.31.x.x)
# 192.168.0.0/16 covers Docker Compose networks (192.168.x.x)
hba_content = pg_hba.read_text()
docker_rules = [
    "host    all    all    172.16.0.0/12    scram-sha-256",
    "host    all    all    192.168.0.0/16    scram-sha-256",
]
if "172.16.0.0/12" not in hba_content or "192.168.0.0/16" not in hba_content:
    new_lines = []
    docker_rule_added = False
    for line in hba_content.split("\n"):
        if not docker_rule_added and line.strip().startswith("host"):
            new_lines.append("# Added by hop3 for Docker container access")
            for rule in docker_rules:
                new_lines.append(rule)
            new_lines.append("")
            docker_rule_added = True
        new_lines.append(line)
    if not docker_rule_added:
        new_lines.append("")
        new_lines.append("# Added by hop3 for Docker container access")
        for rule in docker_rules:
            new_lines.append(rule)
    pg_hba.write_text("\n".join(new_lines))
    print("Updated pg_hba.conf: added Docker network rules")

print("PostgreSQL configured for Docker access")
