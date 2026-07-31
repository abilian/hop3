# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
E2E: a garbage-collected Nix closure is detected at deploy time, not by timeout.

This is the on-box half of the closure guard (`hop3.run.nix_closure`). The unit
tests prove the decision logic; only a real host proves the guard *fires*, and
the reason that distinction matters here is specific: the guard shipped, passed
review, and never once ran, because it looked up `nix-store` on a `PATH` that
the deploy process does not have. Nothing failed. The 180 s health-check timeout
it was written to replace went on happening.

**The fault is constructed, not waited for.** The original plan for this was a
nightly job against a `/nix/store` persisted across runs, on the reasoning that
a fresh store contains nothing old enough to be collected. That reasoning does
not survive contact with the actual precondition: what the guard needs is a
store from which a path *has been* reclaimed, and that state can be created in
seconds by deleting one. Constructing it deterministically is better than
waiting for it to accumulate — it runs on a blank slate, it needs no state
carried between runs, and it therefore does not trade away the reproducibility
the blank-slate rebuild exists to provide.

Two properties, deliberately separate:

* **Retention** — a garbage collection does *not* break a deployed app, because
  the builder roots the closure (`.nix-result`) and the previous one
  (`.nix-result-prev`). This is the hardening working.
* **Detection** — if a closure path goes missing anyway, the next deploy aborts
  naming the missing path, instead of starting uWSGI and timing out.

Runs on any target provisioned `--with nix`, Docker included — the installer
falls back to single-user Nix in containers, so this needs no special host.
Skipped, visibly, where Nix is absent. See `local-notes/plans/30-nix-runtime-1.0.md`.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from .conftest import cli_env, deploy_app_dir, init_git_repo

pytestmark = [pytest.mark.needs_docker, pytest.mark.e2e]

NIX_APP = "nix-gc-demo"

# Absolute, for the same reason the guard resolves it absolutely: a
# non-interactive `docker exec` has no Nix profile sourced either. Both installer
# modes are probed — the installer falls back to single-user in containers, which
# is exactly the target this test most often runs on.
NIX_PROFILES = ("/nix/var/nix/profiles/default", "/home/hop3/.nix-profile")


def _exec(container: Any, cmd: list[str]) -> subprocess.CompletedProcess:
    """Run a command inside the target container, as root."""
    return subprocess.run(
        ["docker", "exec", container["name"], *cmd],
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )


@pytest.fixture
def nix_test_app_dir(test_app_dir: Path) -> Path:
    """The smallest Nix app in the corpus, as a deployable git repo.

    `static-hello` is chosen because its closure is small and its build pulls
    nothing from the network beyond nixpkgs — this test is about the closure's
    lifetime, not about building anything interesting.
    """
    source = (
        Path(__file__).resolve().parents[4] / "apps" / "test-apps-nix" / "static-hello"
    )
    if not source.is_dir():
        pytest.skip(f"nix test app not found at {source}")
    shutil.copytree(source, test_app_dir, dirs_exist_ok=True)
    init_git_repo(test_app_dir)
    return test_app_dir


@pytest.fixture
def nix_bin(hop3_container: dict[str, Any]) -> str:
    """The Nix profile present on the target, or a visible skip.

    An invisible skip is what let the guard's own breakage go unnoticed for a
    release, so the reason names what was looked for and how to provide it.
    """
    for profile in NIX_PROFILES:
        if (
            _exec(hop3_container, ["test", "-x", f"{profile}/bin/nix-store"]).returncode
            == 0
        ):
            return f"{profile}/bin"
    pytest.skip(
        "target carries no nix-store under "
        + " or ".join(NIX_PROFILES)
        + ": provision it with `--with nix` to exercise the closure guard"
    )
    raise AssertionError  # unreachable; satisfies the type checker


@pytest.fixture
def nix_target(hop3_container: dict[str, Any], nix_bin: str) -> dict[str, Any]:
    """The container, once Nix has been confirmed present on it."""
    return hop3_container


def _deploy_nix_app(
    target: dict[str, Any], app_dir: Path
) -> subprocess.CompletedProcess:
    return deploy_app_dir(target, app_dir, NIX_APP, timeout=1800)


def _closure_roots(target: dict[str, Any]) -> list[str]:
    """Store paths the deployed app's workers reference."""
    result = _exec(
        target,
        [
            "sh",
            "-c",
            f"readlink -f /home/hop3/apps/{NIX_APP}/.nix-result",
        ],
    )
    assert result.returncode == 0, result.stderr
    root = result.stdout.strip()
    assert root.startswith("/nix/store/"), f"unexpected gcroot target: {root!r}"
    return [root]


@pytest.mark.slow
def test_gc_does_not_break_a_deployed_app(
    nix_target, nix_bin, nix_test_app_dir
) -> None:
    """Retention: `nix-collect-garbage` leaves a running app's closure intact.

    The builder registers the current closure as a gcroot before building and
    retains the previous one, so a collection has nothing of the app's to take.
    """
    assert _deploy_nix_app(nix_target, nix_test_app_dir).returncode == 0
    roots = _closure_roots(nix_target)

    gc = _exec(nix_target, [f"{nix_bin}/nix-collect-garbage", "-d"])
    assert gc.returncode == 0, gc.stderr

    for root in roots:
        present = _exec(nix_target, ["test", "-e", root])
        assert present.returncode == 0, (
            f"{root} was reclaimed by a garbage collection despite being "
            f"rooted — the retention hardening has regressed"
        )


@pytest.mark.slow
def test_broken_closure_aborts_the_deploy_by_name(
    nix_target, nix_bin, nix_test_app_dir
) -> None:
    """Detection: a missing closure path fails the deploy with a named error.

    The path is deleted deliberately (`--ignore-liveness`, which is why this
    cannot happen by accident on a rooted closure) to create exactly the state a
    garbage collection would leave behind on an *unrooted* one. Without the
    guard this deploy starts uWSGI, the worker dies "No such file or directory",
    and the operator waits out a 180 s health-check timeout for an error that
    names nothing.
    """
    assert _deploy_nix_app(nix_target, nix_test_app_dir).returncode == 0
    (root,) = _closure_roots(nix_target)

    broken = _exec(
        nix_target, [f"{nix_bin}/nix-store", "--delete", "--ignore-liveness", root]
    )
    assert broken.returncode == 0, broken.stderr
    gone = _exec(nix_target, ["test", "-e", root])
    assert gone.returncode != 0, "precondition failed: the store path still exists"

    # Restart rather than redeploy: a redeploy would rebuild the closure and
    # repair the very condition under test.
    result = subprocess.run(
        ["hop3", "app", "restart", "--app", NIX_APP],
        env=cli_env(nix_target),
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )

    assert result.returncode != 0, (
        "restart succeeded against a broken closure — the guard did not fire"
    )
    output = result.stdout + result.stderr
    assert "no longer exist" in output or "garbage-collected" in output, (
        f"the deploy failed, but not with the closure diagnosis: {output[-800:]}"
    )
    assert root in output, "the diagnosis must name the missing store path"
