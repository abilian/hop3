# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""The console-facing deploy error is a concise root cause, not a KB-sized dump.

A failed compose deploy streams the whole container log (hundreds of DB-migration
lines) before the actual error. The console must surface the actionable tail; the
full transcript lives in the diagnostic bundle (`hop3-test why … --section deploy`).
"""

from __future__ import annotations

from hop3_testing.apps.deployment import _extract_deploy_root_cause


def test_drops_migration_noise_keeps_root_cause():
    out = "\n".join(
        [f"> web-1  |   Applying app.{i:04d}_migration... OK" for i in range(160)]
        + [
            "> web-1  | 1008 static files copied.",
            (
                "> Deployer can't start app: 'taiga' did not respond to health "
                "checks within 60.0s."
            ),
            "> Troubleshooting:",
            ">   - hop3 app logs --app taiga",
            "ERROR: deploying app failed",
        ]
    )
    r = _extract_deploy_root_cause(out)

    assert "Deployer can't start app" in r
    assert "hop3 app logs --app taiga" in r
    assert "Applying app." not in r  # 160 migration lines dropped
    assert len(r) < 600  # concise, not the ~8 KB transcript
    # "> " server-log prefixes are stripped for readability.
    assert not r.startswith("> ")


def test_empty_output():
    assert _extract_deploy_root_cause("") == "(no output captured)"


def test_keeps_short_output_verbatim():
    out = "boom: something broke\nERROR: deploying app failed"
    r = _extract_deploy_root_cause(out)
    assert "boom: something broke" in r
    assert "ERROR: deploying app failed" in r
