# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
E2E: `hop3 system status` on a supervisor-managed box.

The e2e container runs its services under supervisor, as a Docker install does.
The command used to shell out to `systemctl is-active`, which does not exist
there, so it failed outright; it now asks the process manager through
hop3-rootd. The assertion is the report itself: each service named, and
running.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

import pytest
from hop3_testing.targets.constants import hermetic_cli_cwd

from .conftest import cli_env


@pytest.mark.e2e
def test_the_services_are_reported_running(hop3_container: dict[str, Any]):
    result = subprocess.run(
        ["hop3", "system", "status", "--json"],
        env=cli_env(hop3_container),
        cwd=hermetic_cli_cwd(),
        capture_output=True,
        text=True,
        check=False,
    )

    # `--json` prints the response's elements; the report is the one data element.
    output = result.stdout + result.stderr
    reports = [e["data"] for e in json.loads(result.stdout) if e["t"] == "data"]
    assert len(reports) == 1, output
    services = next(s for s in reports[0]["sections"] if s["title"] == "Services")
    assert [(i["name"], i["severity"], i["detail"]) for i in services["items"]] == [
        ("Hop3 Server", "ok", "running"),
        ("Nginx", "ok", "running"),
        ("uWSGI Emperor", "ok", "running"),
    ], output
