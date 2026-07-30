#!/usr/bin/env python3
# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""
Prove the Nix closure guard on a real target (plan 30, item 2).

**Self-contained. Docker by default; remote only for the harmless half.**
DETECTION deletes a live Nix store path on purpose and is therefore refused
against anything but a local container. RETENTION deletes nothing of its own —
it runs the collection an operator would run and asserts the platform's roots
held — so `--ssh-host` runs that one remotely, which is the only way to
establish it: a container cannot complete a collection at all (Nix scans
`/proc` for runtime roots and aborts on a read the sandbox refuses).

It configures its own CLI target rather than inheriting yours. The API port is
read from the container's port mapping and a token is minted inside it
(`hop3-server admin:token`), so every `hop3` call is aimed at the same container
whose store is being broken. That is not a convenience — a script that deleted a
path in a container while restarting an app on whatever host your shell happened
to point at would produce no information and possibly an outage.

Two properties, checked separately against a Docker target that has Nix:

  RETENTION  a garbage collection does not reclaim a deployed app's closure,
             because the builder roots it (`.nix-result` / `.nix-result-prev`).

  DETECTION  if a closure path goes missing anyway, the next start aborts
             naming the missing path, instead of letting uWSGI come up and the
             worker die into a 180-second health-check timeout.

DETECTION is the one that matters. The guard it exercises shipped, passed
review, and never once ran: it looked `nix-store` up on a `PATH` the deploy
process does not have, so every deploy logged "check skipped" and continued.
Nothing failed, which is why nobody noticed. A unit test asserted precisely
that behaviour and passed.

This script exists because the two `c_e2e` tests that automate the same
scenario cannot run yet: the e2e container image installs no Nix and its
fixture has no `--with` knob. Until those tests find a home in a harness that
provisions Nix, this is how the guard gets confirmed.

Usage:
    # everything, from nothing (provisions, deploys, checks; 10-30 min):
    uv run python scripts/check-nix-closure-guard.py --deploy

    # against a target already provisioned `--with nix` and carrying the app:
    uv run python scripts/check-nix-closure-guard.py

    # RETENTION on a remote host that can actually collect garbage.
    # --keep is required: without it the harness DESTROYS the app after the
    # test, and there is nothing left to check.
    uv run hop3-test run --host HOST --clean --keep --with nix apps/test-apps-nix/flask-hello
    uv run python scripts/check-nix-closure-guard.py --ssh-host HOST

No environment variables to set, no CLI context to arrange.

Exits 0 only if both properties hold. It never exits 0 because a step was
skipped — an inconclusive run is a failure, which is the whole point.

Two labels, and the difference is the deliverable:

  FAILED        a property was exercised and did not hold. A defect to fix.
  INCONCLUSIVE  the target could not exercise it. A target to change.

Both exit 1. Collapsing them would reproduce, in this script's own output, the
misreading it was written to prevent.
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass

# The name `hop3-test run --docker` actually gives its container. Note this is
# NOT `DockerConfig`'s default of "hop3-test" — the CLI overrides it
# (`cli/commands/test.py`), and assuming otherwise is how two runs of this script
# looked for a container that was never going to be there.
CONTAINER = "hop3-system-test"
# A uWSGI-backed app, deliberately not a static one. The closure guard sits on
# the worker-spawn path, so a static site — served by nginx with no worker —
# would not exercise it. `static-hello` also cannot be validated by the harness
# at all since 0.7 made HTTPS the default: it has no direct app port, so its
# only route is the nginx vhost, and the harness checks status over plain HTTP
# without following redirects (by design, so an app can assert `status = 302`),
# which now always yields the 301 to HTTPS.
APP = "flask-hello"
APP_PATH = "apps/test-apps-nix/flask-hello"

# The command that leaves a usable target behind. `--keep` is load-bearing: the
# runner removes the container on the way out without it, so the obvious form of
# this command provisions a target and then deletes it.
PROVISION_CMD = f"uv run hop3-test run --docker --clean --keep --with nix {APP_PATH}"

# The platform's service user, which owns a single-user Nix store. See `nix()`
# for why store operations must run as this user and not as root.
NIX_OWNER = "hop3"
NIX_OWNER_HOME = f"/home/{NIX_OWNER}"

# Both installer modes: multi-user where systemd exists, single-user in a
# container. The guard resolves these same two absolutely, for the same reason
# this script does — `docker exec` sources no profile either.
NIX_PROFILES = (
    "/nix/var/nix/profiles/default",
    f"{NIX_OWNER_HOME}/.nix-profile",
)

# The diagnosis the guard must produce. Matching on the wording is deliberate:
# a deploy that fails for some *other* reason must not count as a pass.
EXPECTED_DIAGNOSIS = ("no longer exist", "garbage-collected")

# Asked of the *deployed* interpreter: does its restart path call the guard?
RESTART_GUARD_PROBE = """\
import inspect
from hop3.orm.app import App
src = inspect.getsource(App._restart_uwsgi)
print("GUARDED" if "verify_nix_closure" in src else "UNGUARDED")
"""

GREEN, RED, YELLOW, BOLD, OFF = "\033[32m", "\033[31m", "\033[33m", "\033[1m", "\033[0m"


class CheckFailedError(Exception):
    """A property did not hold, or could not be established."""


class TargetUnusableError(CheckFailedError):
    """The target cannot perform a step, so the property was never exercised.

    Distinct from its parent because the two want different responses: a
    violated property is a defect to fix, an unusable target is a target to
    change. Both are failures — neither may exit 0 — but reporting one as the
    other sends the reader to the wrong place, which is the mistake the guard's
    own history is made of.
    """


API_PORT = 8000
HOP3_VENV = "/home/hop3/venv"
HOP3_SERVER_BIN = f"{HOP3_VENV}/bin/hop3-server"
ADMIN_USER = "admin"


@dataclass
class Target:
    """Where the store lives: a local container, or a remote host over SSH.

    Remote is permitted for RETENTION alone. Retention deletes nothing — it runs
    a collection and asserts that nothing of the app's was taken — whereas
    detection deliberately removes a live store path, which is not something to
    do to a machine reachable by hostname.
    """

    nix_bin: str
    container: str | None = None
    ssh_host: str | None = None
    cli_env: dict[str, str] | None = None

    @property
    def is_remote(self) -> bool:
        return self.ssh_host is not None

    @property
    def label(self) -> str:
        return self.ssh_host or self.container or "?"


def run(
    cmd: list[str], *, timeout: int = 300, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, capture_output=True, text=True, check=False, timeout=timeout, env=env
    )


def hop3(target: Target, *args: str, timeout: int = 300) -> subprocess.CompletedProcess:
    """Run the `hop3` CLI against **this** container, never an ambient target."""
    return run(["hop3", *args], timeout=timeout, env=target.cli_env)


def _api_url(target: Target) -> str:
    """Where this target's API answers, derived from the target itself.

    Derived rather than inherited, so the machine whose store is touched and the
    machine the CLI talks to cannot diverge.
    """
    if target.is_remote:
        host = target.ssh_host.split("@", 1)[-1]
        return f"http://{host}:{API_PORT}"

    ports = run(["docker", "port", target.container, str(API_PORT)])
    if ports.returncode != 0 or not ports.stdout.strip():
        msg = (
            f"'{target.container}' publishes no port for {API_PORT}, so the CLI\n"
            f"        has nowhere to connect. Was it started by `hop3-test --docker`?"
        )
        raise TargetUnusableError(msg)
    # "0.0.0.0:32770" (possibly several lines; the first is enough)
    port = ports.stdout.strip().splitlines()[0].rsplit(":", 1)[-1].strip()
    return f"http://localhost:{port}"


def build_cli_env(target: Target) -> dict[str, str]:
    """Point the CLI at this target: its own API, its own minted token."""
    api_url = _api_url(target)

    minted = dexec(target, [HOP3_SERVER_BIN, "admin:token", ADMIN_USER])
    if minted.returncode != 0:
        msg = (
            f"could not mint a token for '{ADMIN_USER}' on {target.label}:\n"
            f"        {(minted.stdout + minted.stderr).strip()[-600:]}"
        )
        raise TargetUnusableError(msg)
    token = _extract_token(minted.stdout)
    if not token:
        msg = f"`admin:token` produced no token:\n{minted.stdout[-600:]}"
        raise TargetUnusableError(msg)

    env = os.environ.copy()
    # Drop anything that could redirect the CLI elsewhere (ADR 043's taboo,
    # applied here for the same reason: a destructive step must not be able to
    # address a machine other than the one under test).
    for key in ("HOP3_DEV_HOST", "HOP3_TEST_HOST", "HOP3_CONTEXT", "HOP3_APP"):
        env.pop(key, None)
    env["HOP3_API_URL"] = api_url
    env["HOP3_API_TOKEN"] = token
    env["HOP3_NO_INPUT"] = "1"
    return env


def _extract_token(stdout: str) -> str:
    """The JWT from `admin:token` output (printed alone on its own line)."""
    for line in stdout.splitlines():
        candidate = line.strip()
        if candidate.count(".") == 2 and " " not in candidate and len(candidate) > 40:
            return candidate
    return ""


def dexec(
    target: Target, cmd: list[str], *, timeout: int = 300
) -> subprocess.CompletedProcess:
    """Run a command on the target as root, whichever kind of target it is."""
    if target.is_remote:
        return run(
            ["ssh", "-o", "BatchMode=yes", target.ssh_host, shlex.join(cmd)],
            timeout=timeout,
        )
    return run(["docker", "exec", target.container, *cmd], timeout=timeout)


def nix(
    target: Target, cmd: list[str], *, timeout: int = 300
) -> subprocess.CompletedProcess:
    """Run a Nix command as the user that owns the store.

    Not root, for two reasons. This is a **single-user** install under
    `/home/hop3/.nix-profile`, so root writing to the store or its database
    leaves root-owned files behind that the hop3 user can no longer manage.

    And root is what breaks the collection outright: Nix scans `/proc/<pid>/`
    for runtime roots, reading another process's `environ` needs ptrace access,
    and Docker drops `CAP_SYS_PTRACE` by default — so root gets `EPERM` and Nix
    aborts (`error: read of 65536 bytes: Operation not permitted`). An
    unprivileged user gets `EACCES` on the same files, which Nix skips. The
    privileged path is the one that fails.

    `docker exec -u` does not set the environment for the new user, so HOME is
    passed explicitly; Nix needs it to find the profile. `sudo -H` does the
    equivalent on a remote host.
    """
    if target.is_remote:
        return run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                target.ssh_host,
                shlex.join(["sudo", "-H", "-u", NIX_OWNER, *cmd]),
            ],
            timeout=timeout,
        )
    return run(
        [
            "docker",
            "exec",
            "-u",
            NIX_OWNER,
            "-e",
            f"HOME={NIX_OWNER_HOME}",
            "-e",
            f"USER={NIX_OWNER}",
            target.container,
            *cmd,
        ],
        timeout=timeout,
    )


def step(msg: str) -> None:
    print(f"\n{BOLD}==> {msg}{OFF}")


def ok(msg: str) -> None:
    print(f"  {GREEN}PASS{OFF}  {msg}")


def info(msg: str) -> None:
    print(f"        {msg}")


def resolve_target(container: str) -> Target:
    """The container and its Nix profile, or a loud failure naming both paths."""
    probe = run(["docker", "ps", "--filter", f"name=^{container}$", "-q"])
    if probe.returncode != 0 or not probe.stdout.strip():
        # Name what IS running. The harness owns this name and has changed it
        # before; a bare "not found" sends the reader back to the same wrong
        # assumption, whereas the actual list settles it in one line.
        running = run(["docker", "ps", "--format", "{{.Names}}"]).stdout.split()
        msg = (
            f"no running container named '{container}'.\n"
            f"        Running now: {', '.join(running) or 'nothing'}\n"
            f"        Provision one with:\n"
            f"          {PROVISION_CMD}\n"
            f"        Or point this at an existing one with --container NAME."
        )
        raise TargetUnusableError(msg)

    return _resolve_nix_profile(Target(nix_bin="", container=container))


def ssh_destination(host: str, user: str) -> str:
    """`user@host`, unless the host already carries a user.

    Bare `ssh some.host` connects as your *local* username, which is not an
    account on a Hop3 server. The platform's convention is root (HOP3_SSH_USER),
    and every step here either needs root or needs sudo, which needs it first.
    """
    return host if "@" in host else f"{user}@{host}"


def resolve_ssh_target(ssh_host: str) -> Target:
    """A remote host and its Nix profile, or a loud failure."""
    reachable = run([
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=10",
        ssh_host,
        "true",
    ])
    if reachable.returncode != 0:
        msg = (
            f"cannot reach '{ssh_host}' over SSH (BatchMode, so no password "
            f"prompt).\n        Pass --ssh-user if the account is not root, or "
            f"user@host directly.\n        {reachable.stderr.strip()[-400:]}"
        )
        raise TargetUnusableError(msg)
    return _resolve_nix_profile(Target(nix_bin="", ssh_host=ssh_host))


def _resolve_nix_profile(target: Target) -> Target:
    """Locate `nix-store` on the target, trying both installer modes."""
    for profile in NIX_PROFILES:
        candidate = Target(
            nix_bin=f"{profile}/bin",
            container=target.container,
            ssh_host=target.ssh_host,
        )
        if dexec(candidate, ["test", "-x", f"{profile}/bin/nix-store"]).returncode == 0:
            return candidate

    msg = (
        f"'{target.label}' carries no nix-store under "
        + " or ".join(NIX_PROFILES)
        + ".\n        The target was not provisioned with Nix. Re-provision:\n"
        + (
            f"          uv run hop3-test run --host {target.ssh_host} "
            f"--clean --with nix {APP_PATH}"
            if target.is_remote
            else f"          {PROVISION_CMD}"
        )
    )
    raise TargetUnusableError(msg)


def deploy(container: str) -> None:
    step(f"Deploying {APP} (nix builder) to {container}")
    # --keep is required, not optional: `hop3-test run` stops and removes the
    # container in a `finally:` unless it is passed, so without it this deploys
    # a target and then destroys it before anything can be checked against it.
    result = run(
        [
            "uv",
            "run",
            "hop3-test",
            "run",
            "--docker",
            "--clean",
            "--keep",
            "--with",
            "nix",
            APP_PATH,
        ],
        timeout=3600,
    )
    if result.returncode != 0:
        msg = f"deploy failed:\n{result.stdout[-2000:]}\n{result.stderr[-2000:]}"
        raise TargetUnusableError(msg)
    ok(f"{APP} deployed")


def resolve_app_name(target: Target) -> str:
    """The deployed app's real name.

    `hop3-test` suffixes app names with a run timestamp (`flask-hello-1785422946`),
    so the recipe directory name is not the app name. Assuming it was is how an
    earlier version of this script would have failed every CLI call.
    """
    listing = dexec(target, ["ls", "/home/hop3/apps"])
    names = [n for n in listing.stdout.split() if n == APP or n.startswith(f"{APP}-")]
    if not names:
        msg = (
            f"no deployed app matching '{APP}' in /home/hop3/apps "
            f"(found: {' '.join(listing.stdout.split()) or 'nothing'}).\n"
            f"        Deploy it first, or re-run with --deploy."
        )
        raise TargetUnusableError(msg)
    return max(names)


def closure_root(target: Target, app: str) -> str:
    """The store path the deployed app's gcroot points at."""
    result = dexec(target, ["readlink", "-f", f"/home/hop3/apps/{app}/.nix-result"])
    root = result.stdout.strip()
    if result.returncode != 0 or not root.startswith("/nix/store/"):
        msg = (
            f"could not read the gcroot for '{app}' "
            f"(got {root!r}); is the app deployed?"
        )
        raise TargetUnusableError(msg)
    return root


def check_retention(target: Target, app: str, root: str) -> str:
    """Retention: a rebuild while running, then a GC, must not break the app.

    This is the forgejo class, and the sequence matters. Deploying and then
    collecting garbage proves nothing: the closure is the *current* gcroot, so
    nothing would reclaim it anyway. The fault appears when a **rebuild** makes
    the running worker's closure the *old* one — at which point it is
    unreferenced unless something deliberately holds it, and a collection takes
    it out from under a process still exec'ing its store path.

    The builder is supposed to prevent exactly that by re-rooting the previous
    closure as `.nix-result-prev` **before** the rebuild starts (ADR 053). That
    root is what this checks, and a deploy-then-GC test never touches it.

    Returns the post-rebuild closure root.
    """
    step("RETENTION — rebuild while running, then collect garbage")
    info(f"closure before rebuild: {root}")

    rebuilt = hop3(target, "app", "upgrade", "--app", app, timeout=1800)
    if rebuilt.returncode != 0:
        msg = (
            f"the rebuild failed, so the retention case was never set up:\n"
            f"        {(rebuilt.stdout + rebuilt.stderr).strip()[-800:]}"
        )
        raise TargetUnusableError(msg)

    new_root = closure_root(target, app)
    if new_root == root:
        info("rebuild produced the same closure (inputs unchanged)")
    else:
        info(f"closure after rebuild:  {new_root}")

    prev = dexec(target, ["readlink", "-f", f"/home/hop3/apps/{app}/.nix-result-prev"])
    prev_root = prev.stdout.strip()
    if prev_root.startswith("/nix/store/"):
        info(f"previous closure rooted as .nix-result-prev: {prev_root}")
    else:
        info("no .nix-result-prev (first rebuild, or the rebuild was a no-op)")

    gc = nix(target, [f"{target.nix_bin}/nix-collect-garbage", "-d"], timeout=1800)
    if gc.returncode != 0:
        msg = (
            f"the target cannot run a garbage collection, so retention was\n"
            f"        never exercised — this says nothing about the property.\n"
            f"        Nix scans /proc for runtime roots and aborts on any read\n"
            f"        it is refused; under Docker it is refused as root (no\n"
            f"        CAP_SYS_PTRACE) and as {NIX_OWNER} alike.\n"
            f"        {gc.stderr.strip()[-500:]}"
        )
        raise TargetUnusableError(msg)
    collected = gc.stdout.strip().splitlines()
    info(f"collected: {collected[-1] if collected else 'nothing'}")

    for label, path in (("current", new_root), ("previous", prev_root)):
        if not path.startswith("/nix/store/"):
            continue
        if dexec(target, ["test", "-e", path]).returncode != 0:
            msg = (
                f"the {label} closure was reclaimed: {path}\n"
                f"        A running app can now lose its files to a garbage\n"
                f"        collection. This is the defect ADR 053's rooting exists\n"
                f"        to prevent, and it is more serious than the guard."
            )
            raise CheckFailedError(msg)
    ok("both closures survived the collection")

    served = hop3(target, "app", "status", "--app", app, timeout=120)
    if served.returncode != 0:
        msg = (
            "the app is not healthy after rebuild + garbage collection:\n"
            f"        {(served.stdout + served.stderr).strip()[-600:]}"
        )
        raise CheckFailedError(msg)
    ok("app still healthy after rebuild + collection")
    return new_root


def _requisites(target: Target, root: str) -> list[str]:
    """Every store path the closure of `root` depends on."""
    result = nix(target, [f"{target.nix_bin}/nix-store", "-q", "--requisites", root])
    if result.returncode != 0:
        msg = (
            f"could not query the closure of {root}:\n"
            f"        {result.stderr.strip()[-400:]}"
        )
        raise TargetUnusableError(msg)
    return [p for p in result.stdout.split() if p.startswith("/nix/store/")]


def check_retention_remote(target: Target, app: str) -> None:
    """Retention on a host whose Nix can actually collect.

    The Docker target cannot run a collection at all, so this property has only
    ever been established by reading the builder's code. Here it is exercised:
    collect, then assert that both the current closure and the one the running
    workers came from are still whole.

    Whole, not merely present. Checking that the gcroot's own store path
    survived would pass while a dependency three levels down had been reclaimed
    — which is the shape the failure actually takes, since it is the *inner*
    paths a wrapper execs that go missing. So every requisite is enumerated
    before the collection and checked after it.

    This deletes nothing of its own. It runs the collection an operator would
    run, which is the whole scenario, and asserts the platform's roots held.
    """
    step("RETENTION — collect garbage, then assert both closures are whole")

    # The rebuild has to happen here, through the CLI. `hop3-test --reuse` looks
    # like it would do it and does not: it deploys a *new* app under a fresh
    # timestamped name, leaving the original untouched, so no .nix-result-prev
    # is ever written and the collection would have nothing of interest to take.
    info(f"closure before rebuild: {closure_root(target, app)}")
    rebuilt = hop3(target, "app", "upgrade", "--app", app, timeout=1800)
    if rebuilt.returncode != 0:
        msg = (
            f"the rebuild failed, so the retention case was never set up:\n"
            f"        {(rebuilt.stdout + rebuilt.stderr).strip()[-800:]}"
        )
        raise TargetUnusableError(msg)

    current = closure_root(target, app)
    prev = dexec(
        target, ["readlink", "-f", f"{NIX_OWNER_HOME}/apps/{app}/.nix-result-prev"]
    )
    prev_root = prev.stdout.strip()

    if not prev_root.startswith("/nix/store/"):
        msg = (
            f"'{app}' has no .nix-result-prev after a rebuild, so the closure\n"
            f"        the running workers came from was never rooted. That is the\n"
            f"        retention mechanism absent rather than failing, and a\n"
            f"        collection now would be testing nothing."
        )
        raise TargetUnusableError(msg)

    if prev_root == current:
        msg = (
            f"the rebuild produced the same closure, so .nix-result-prev points\n"
            f"        at the path .nix-result already roots:\n"
            f"          {current}\n"
            f"        A collection cannot threaten it, and passing here would\n"
            f"        report retention as proven while the mechanism that carries\n"
            f"        it — rooting the SUPERSEDED closure — went unexercised.\n"
            f"        The precondition needs a rebuild whose inputs differ, so the\n"
            f"        running workers are left executing a closure nothing else\n"
            f"        references. Change the recipe (a version, a source file),\n"
            f"        redeploy the same app, then re-run."
        )
        raise TargetUnusableError(msg)

    info(f"current closure:  {current}")
    info(f"previous closure: {prev_root}")

    guarded = {
        "current": _requisites(target, current),
        "previous": _requisites(target, prev_root),
    }
    for label, paths in guarded.items():
        info(f"{label} closure: {len(paths)} store paths")

    gc = nix(target, [f"{target.nix_bin}/nix-collect-garbage", "-d"], timeout=3600)
    if gc.returncode != 0:
        msg = (
            f"the target cannot run a garbage collection, so retention was\n"
            f"        never exercised — this says nothing about the property.\n"
            f"        {gc.stderr.strip()[-500:]}"
        )
        raise TargetUnusableError(msg)
    collected = gc.stdout.strip().splitlines()
    info(f"collected: {collected[-1] if collected else 'nothing'}")

    for label, paths in guarded.items():
        missing = [p for p in paths if dexec(target, ["test", "-e", p]).returncode != 0]
        if missing:
            msg = (
                f"the {label} closure lost {len(missing)} of {len(paths)} paths to\n"
                f"        the collection, starting with {missing[0]}.\n"
                f"        A running app can lose its files to a garbage collect.\n"
                f"        This is the defect ADR 053's rooting exists to prevent,\n"
                f"        and it is more serious than a missing detector."
            )
            raise CheckFailedError(msg)
        ok(f"{label} closure intact: all {len(paths)} paths survived")


def break_closure(target: Target, root: str) -> None:
    step("Breaking the closure deliberately")
    # --ignore-liveness is required precisely because the path IS rooted; that
    # is what makes this a construction of the fault rather than a reproduction
    # of a bug in retention.
    deleted = nix(
        target,
        [f"{target.nix_bin}/nix-store", "--delete", "--ignore-liveness", root],
        timeout=600,
    )
    if deleted.returncode != 0:
        msg = f"could not delete {root}: {deleted.stderr[-800:]}"
        raise TargetUnusableError(msg)
    if dexec(target, ["test", "-e", root]).returncode == 0:
        msg = f"precondition failed: {root} still exists after --delete"
        raise TargetUnusableError(msg)
    ok(f"store path removed: {root}")


def preflight_server_is_current(target: Target) -> None:
    """The deployed server must call the guard on the restart path.

    Without this, a run against a container deployed before the fix reports
    "the guard did not fire" — which is true of that box and says nothing about
    the code you are testing. That misattribution is the exact failure this
    script exists to prevent, so it must not be one of its own outputs.

    Asks the deployed interpreter about its own source rather than comparing
    versions: what matters is whether the call is there, and a version string
    would only be a proxy for it.
    """
    step("Pre-flight — the deployed server must guard the restart path")
    probe = dexec(target, [f"{HOP3_VENV}/bin/python", "-c", RESTART_GUARD_PROBE])
    verdict = probe.stdout.strip()

    if verdict == "UNGUARDED":
        msg = (
            "the deployed server does not check the closure on restart, so a\n"
            "        restart would succeed against a broken closure no matter\n"
            "        what the code in your checkout says.\n"
            "        This container predates the restart-path fix. Redeploy it:\n"
            f"          uv run python {sys.argv[0]} --deploy\n"
            "        (`--from` defaults to local, so that ships your checkout.)"
        )
        raise TargetUnusableError(msg)

    if verdict != "GUARDED":
        msg = (
            "could not establish whether the deployed server guards the restart\n"
            "        path, so a DETECTION result would not be attributable.\n"
            f"        {(probe.stdout + probe.stderr).strip()[-500:]}"
        )
        raise TargetUnusableError(msg)

    ok("the deployed server calls the closure guard on restart")


def preflight_cli(target: Target, app: str) -> None:
    """The CLI must reach the app, before anything is broken.

    The *which machine* question no longer needs asking: `build_cli_env` derived
    this CLI target from the same container, so the store being broken and the
    app being restarted are the same host by construction. What remains worth
    checking is that the app is actually there and reachable — otherwise the
    detection step could not tell a fired guard from an unreachable server.
    """
    step("Pre-flight — the CLI must reach the app on this container")
    status = hop3(target, "app", "status", "--app", app, timeout=120)
    if status.returncode != 0:
        msg = (
            f"`hop3 app status --app {app}` failed against "
            f"{target.cli_env['HOP3_API_URL']}.\n"
            f"        Is the app deployed? Re-run with --deploy, or:\n"
            f"          {PROVISION_CMD}\n"
            f"        Output: {(status.stdout + status.stderr).strip()[-600:]}"
        )
        raise TargetUnusableError(msg)
    ok(f"CLI reaches {app} at {target.cli_env['HOP3_API_URL']}")


def check_detection(target: Target, app: str, root: str) -> None:
    step("DETECTION — starting the app must abort, naming the missing path")
    # Restart, not redeploy: a redeploy rebuilds the closure and repairs the
    # very condition under test. Driven through the operator-facing CLI,
    # because that is the path the guard protects.
    result = hop3(target, "app", "restart", "--app", app, timeout=600)
    output = result.stdout + result.stderr

    if result.returncode == 0:
        msg = (
            "the app restarted successfully against a broken closure.\n"
            "        The guard did not fire. This is the defect the guard exists\n"
            "        to prevent, and it is what shipped before 2026-07-30.\n"
            f"        Output:\n{output[-1500:]}"
        )
        raise CheckFailedError(msg)

    if not any(phrase in output for phrase in EXPECTED_DIAGNOSIS):
        msg = (
            "the restart failed, but not with the closure diagnosis — so this\n"
            "        run does not establish that the guard fired.\n"
            f"        Expected one of {EXPECTED_DIAGNOSIS} in:\n{output[-1500:]}"
        )
        raise CheckFailedError(msg)

    if root not in output:
        msg = (
            f"the closure diagnosis appeared but did not name {root}.\n"
            f"        An operator needs the path to act on it.\n{output[-1500:]}"
        )
        raise CheckFailedError(msg)

    ok("aborted with the closure diagnosis, naming the missing path")
    for line in output.strip().splitlines()[:12]:
        info(line)


def run_remote_retention(args: argparse.Namespace) -> int:
    """RETENTION against a remote host. Detection stays local, by design."""
    if args.deploy:
        msg = (
            "--deploy is refused with --ssh-host: this script will not "
            "provision\n        a remote machine. Deploy the app yourself, then "
            "point this at it:\n"
            f"          uv run hop3-test run --host {args.ssh_host} --clean "
            f"--keep --with nix {APP_PATH}"
        )
        raise TargetUnusableError(msg)

    destination = ssh_destination(args.ssh_host, args.ssh_user)
    step(f"Locating Nix on '{destination}'")
    target = resolve_ssh_target(destination)
    ok(f"nix-store at {target.nix_bin}/nix-store")

    step("Configuring the CLI against this host")
    target.cli_env = build_cli_env(target)
    ok(f"API {target.cli_env['HOP3_API_URL']}, token minted over SSH")

    app = resolve_app_name(target)
    info(f"deployed app: {app}")

    preflight_cli(target, app)
    check_retention_remote(target, app)

    print(f"\n{GREEN}{BOLD}RETENTION holds.{OFF}")
    print("  - a garbage collection left both closures whole, every path")
    print("\nDETECTION is not run here — it deletes a live store path, which is")
    print("not something to do to a machine reachable by hostname. Run it on")
    print("Docker: uv run python scripts/check-nix-closure-guard.py --deploy")
    return 0


def run_docker_checks(args: argparse.Namespace) -> int:
    """Both properties against a local container. Detection is the point."""
    if args.deploy:
        deploy(args.container)

    step(f"Locating Nix on '{args.container}'")
    target = resolve_target(args.container)
    ok(f"nix-store at {target.nix_bin}/nix-store")

    step("Configuring the CLI against this container")
    target.cli_env = build_cli_env(target)
    ok(f"API {target.cli_env['HOP3_API_URL']}, token minted in-container")

    app = resolve_app_name(target)
    info(f"deployed app: {app}")
    root = closure_root(target, app)

    preflight_cli(target, app)
    preflight_server_is_current(target)

    # The two properties are independent, and DETECTION is the one plan 30 gates
    # on. Retention needs a garbage collection; detection constructs the missing
    # path directly and needs none. Letting an unusable target abort the run
    # before detection threw away the result that mattered because of the one
    # that mattered less.
    retention: CheckFailedError | None = None
    try:
        root = check_retention(target, app, root)
    except TargetUnusableError as e:
        retention = e
        print(f"\n  {YELLOW}INCONCLUSIVE{OFF}  {e}", file=sys.stderr)
        info("continuing to DETECTION, which needs no collection")
        root = closure_root(target, app)

    break_closure(target, root)
    check_detection(target, app, root)

    # Said once, before either verdict: the app is broken on both paths, and a
    # run that ends non-zero is exactly when the reader most needs to be told.
    info("")
    info("The app is broken on purpose now. Restore it with:")
    info(f"  uv run hop3-test run --docker --reuse {APP_PATH}")
    info("Or leave it: the next --deploy rebuilds from a clean container.")

    if retention is not None:
        print(f"\n{YELLOW}{BOLD}DETECTION holds; RETENTION was not exercised.{OFF}")
        print("  - a broken closure aborts the start, naming the missing path")
        print("  - the target could not collect garbage, so retention is unproven")
        print("\nDetection is the property the guard exists for, and it is now")
        print("confirmed on a box. Retention needs a target whose Nix can run a")
        print("collection — run this with --ssh-host to establish it there.")
        return 1

    print(f"\n{GREEN}{BOLD}Both properties hold.{OFF}")
    print("  - a garbage collection leaves a deployed app's closure intact")
    print("  - a broken closure aborts the start, naming the missing path")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--deploy",
        action="store_true",
        help="provision the target and deploy the app first (slow, ~10-30 min)",
    )
    parser.add_argument("--container", default=CONTAINER, help="target container name")
    parser.add_argument(
        "--ssh-host",
        metavar="HOST",
        help=(
            "run RETENTION ONLY against a remote host (ssh target). "
            "Detection is refused remotely: it deletes a live store path."
        ),
    )
    parser.add_argument(
        "--ssh-user",
        default="root",
        help="SSH user, matching HOP3_SSH_USER's default (default: root)",
    )
    args = parser.parse_args()

    try:
        if args.ssh_host:
            return run_remote_retention(args)
        return run_docker_checks(args)

    except TargetUnusableError as e:
        # Not FAILED: nothing was established about the guard either way, and
        # labelling an unusable target as a failed property is the same
        # misattribution this script exists to stop other people making.
        print(f"\n{YELLOW}{BOLD}INCONCLUSIVE{OFF}  {e}", file=sys.stderr)
        print(
            f"\n{YELLOW}The target could not exercise the property.{OFF} "
            f"That is not a\npass and not a defect — it is a target to change. "
            f"Still exit 1: a\nrun that establishes nothing must never look "
            f"like a green one.",
            file=sys.stderr,
        )
        return 1
    except CheckFailedError as e:
        print(f"\n{RED}{BOLD}FAILED{OFF}  {e}", file=sys.stderr)
        print(
            f"\n{YELLOW}This run establishes nothing about the guard.{OFF} "
            f"An inconclusive\nresult is a failure here, not a pass — that "
            f"confusion is what the\nguard's own breakage hid behind.",
            file=sys.stderr,
        )
        return 1
    except subprocess.TimeoutExpired as e:
        print(f"\n{RED}{BOLD}TIMEOUT{OFF}  {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
