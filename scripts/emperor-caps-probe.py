#!/usr/bin/env python3
# Copyright (c) 2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Measure what a capability-scoped uWSGI Emperor needs, and what it leaks.

ADR 055 §4.1 proposes an Emperor that runs as ``hop3`` with ambient
``CAP_SETUID``/``CAP_SETGID`` (plus ``CAP_CHOWN``/``CAP_DAC_OVERRIDE`` if uWSGI
needs them) and drops each vassal to a per-app user. Open question 2 asks
whether that set is enough. The question that decides the design is whether
the capabilities survive into the app: the kernel clears them on a switch
*from uid 0*, and ``hop3`` -> ``hop3-app-<name>`` is a switch between two
non-root uids. If they survive, app code can ``setuid(0)``.

Usage:
    python scripts/emperor-caps-probe.py [--image hop3-e2e:test]

Runs in a throwaway container from the e2e image (build it with ``make
test-e2e`` or ``hop3_testing.e2e_image.ensure_e2e_image``). Touches no server
and no other container. For each Emperor (``hop3`` with a capability set
started through ``setpriv``, the same kernel state as systemd's
``AmbientCapabilities=``; a root Emperor; ``hop3`` with a ``setpriv`` vassal
wrapper) it runs one vassal dropping to ``hop3-app-probe``: a WSGI app, and an
``attach-daemon`` built the way ``run/uwsgi/worker.py`` builds it, with an
``export`` of a planted secret on the shell line. It reports:

- whether the vassal starts and answers, and who owns its log file;
- the capability sets of every process below the Emperor, and which user each
  runs as;
- whether app code can ``setuid(0)``, in a forked child and an exec'd one;
- whether the app can connect to a ``0660 root:hop3`` socket (rootd's mode);
- whether touching the vassal file reloads it and deleting it stops it;
- what ``hop3`` can still do to the app (read its log, read its cwd, signal
  it), and whether an unrelated user can read its secret.

The filesystem follows ADR 055 §3, with the log directory owned by the app
user, group ``hop3`` and setgid, so the control plane reads logs without
joining the app's group. Anything the probe had to change beyond that layout
is printed, because it is a finding too.
"""

from __future__ import annotations

import argparse
import contextlib
import grp
import json
import os
import pwd
import signal
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from operator import itemgetter
from pathlib import Path

DEFAULT_IMAGE = "hop3-e2e:test"

HOP3 = "hop3"
APP_USER = "hop3-app-probe"
APP_ROOT = Path("/home/hop3/apps/probe")
VASSALS = Path("/home/hop3/probe-vassals")
UWSGI = Path("/home/hop3/venv/bin/uwsgi")
PORT = 18080
ROOTD_SOCK = Path("/run/probe-rootd.sock")
#: Planted in the app's environment the way ``worker.py`` delivers it, as an
#: ``export`` on the ``attach-daemon`` shell line.
CANARY = "probe-canary-7f3a9"
START_TIMEOUT = 20.0
#: What uWSGI logs when it changes identity. It prints these only when it runs
#: as root; nothing at all is logged when it ignores ``uid``/``gid``.
IDENTITY_MARK = "() to "

WRAPPER = Path("/usr/local/libexec/probe-vassal-wrapper")


@dataclass(frozen=True)
class Emperor:
    """How the Emperor runs: as ``hop3`` with ``caps``, or as root (None)."""

    caps: list[str] | None
    #: Start each vassal through WRAPPER (``--emperor-wrapper``), which drops
    #: to the app user with ``setpriv`` instead of leaving it to uWSGI.
    wrapper: bool = False


#: Emperors under test: ``hop3`` with each capability set in ADR 055 §4.1's
#: order; a root Emperor (§4.2); and ``hop3`` with only setuid/setgid and a
#: setpriv wrapper doing the drop. The empty set shows whether the privilege is
#: needed at all.
EMPERORS: dict[str, Emperor] = {
    "hop3, no caps": Emperor([]),
    "hop3 +setuid,setgid": Emperor(["setuid", "setgid"]),
    "hop3 +chown": Emperor(["setuid", "setgid", "chown"]),
    "hop3 +dac_override": Emperor(["setuid", "setgid", "chown", "dac_override"]),
    "root": Emperor(None),
    "hop3 +setuid,setgid, setpriv wrapper": Emperor(["setuid", "setgid"], True),
}

#: Starts one vassal as its app's own user with no capabilities and
#: no_new_privs (setuid binaries stop working). The Emperor calls it the way
#: it would call uWSGI: ``<wrapper> --ini <app>.ini``, from the vassal dir.
WRAPPER_SH = f"""#!/bin/sh
if [ "$1" != "--ini" ] || [ -z "$2" ]; then
    echo "probe-vassal-wrapper: expected --ini <app>.ini, got: $*" >&2
    exit 1
fi
user="hop3-app-$(basename "$2" .ini)"
exec setpriv --reuid="$user" --regid="$user" --init-groups \\
    --inh-caps=-all --ambient-caps=-all --no-new-privs -- {UWSGI} "$@"
"""

#: linux/capability.h, bit -> name.
CAP_NAMES = [
    "chown", "dac_override", "dac_read_search", "fowner", "fsetid", "kill",
    "setgid", "setuid", "setpcap", "linux_immutable", "net_bind_service",
    "net_broadcast", "net_admin", "net_raw", "ipc_lock", "ipc_owner",
    "sys_module", "sys_rawio", "sys_chroot", "sys_ptrace", "sys_pacct",
    "sys_admin", "sys_boot", "sys_nice", "sys_resource", "sys_time",
    "sys_tty_config", "mknod", "lease", "audit_write", "audit_control",
    "setfcap", "mac_override", "mac_admin", "syslog", "wake_alarm",
    "block_suspend", "audit_read", "perfmon", "bpf", "checkpoint_restore",
]  # fmt: skip


# ---------------------------------------------------------------------------
# Host side: one throwaway container, removed however the run ends.
# ---------------------------------------------------------------------------


def run_on_host(image: str) -> int:
    name = f"hop3-emperor-caps-probe-{os.getpid()}"
    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--rm",
            # pid 1 must reap: a killed vassal's orphans would linger as zombies.
            "--init",
            "--name",
            name,
            "--entrypoint",
            "sleep",
            image,
            "infinity",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    try:
        subprocess.run(["docker", "cp", __file__, f"{name}:/probe.py"], check=True)
        return subprocess.run(
            ["docker", "exec", name, "python3", "/probe.py", "--inner"], check=False
        ).returncode
    finally:
        subprocess.run(
            ["docker", "rm", "-f", name], check=False, stdout=subprocess.DEVNULL
        )


# ---------------------------------------------------------------------------
# Container side.
# ---------------------------------------------------------------------------

APP_PY = """
import json, os, socket, subprocess

ROOTD_SOCK = "%(sock)s"


def status(pid="self"):
    fields = ("Uid", "Gid", "Groups", "CapInh", "CapPrm", "CapEff", "CapBnd",
              "CapAmb", "NoNewPrivs")
    out = {}
    with open(f"/proc/{pid}/status") as f:
        for line in f:
            key, _, value = line.partition(":")
            if key in fields:
                out[key] = value.strip()
    return out


def setuid0_in_fork():
    pid = os.fork()
    if pid == 0:
        try:
            os.setuid(0)
            os._exit(0)
        except OSError:
            os._exit(1)
    _, code = os.waitpid(pid, 0)
    return "BECAME ROOT" if os.waitstatus_to_exitcode(code) == 0 else "refused"


def setuid0_in_exec():
    rc = subprocess.run(["/usr/bin/python3", "-c", "import os; os.setuid(0)"],
                        capture_output=True).returncode
    return "BECAME ROOT" if rc == 0 else "refused"


def rootd_socket():
    s = socket.socket(socket.AF_UNIX)
    try:
        s.connect(ROOTD_SOCK)
        return "CONNECTED"
    except OSError as e:
        return f"refused ({e.strerror})"
    finally:
        s.close()


def report():
    return {"status": status(), "setuid0_fork": setuid0_in_fork(),
            "setuid0_exec": setuid0_in_exec(), "rootd_socket": rootd_socket()}
"""

WSGI_PY = """
from probe_lib import report
import json


def application(environ, start_response):
    body = json.dumps(report()).encode()
    start_response("200 OK", [("Content-Type", "application/json")])
    return [body]
"""

DAEMON_PY = """
import json, sys, time
sys.path.insert(0, "%(src)s")
from probe_lib import report

with open("%(log)s/daemon.json", "w") as f:
    json.dump(report(), f)
while True:
    time.sleep(60)
"""

VASSAL_INI = """[uwsgi]
strict = true
uid = {user}
gid = {user}
master = true
processes = 2
chdir = {src}
http-socket = 127.0.0.1:{port}
wsgi-file = {src}/wsgi.py
logfile-chmod = 640
logto2 = {log}/web.1.log
attach-daemon = sh -c "cd {src} && export PROBE_SECRET='{canary}'; exec /usr/bin/python3 {src}/daemon.py >>{log}/daemon.1.log 2>&1"
"""


@dataclass
class Result:
    cap_set: str
    emperor_caps: dict[str, str]
    answered: bool
    web: dict | None
    daemon: dict | None
    processes: list[dict]
    log_file: str
    emperor_log_tail: str
    identity_lines: list[str] = field(default_factory=list)
    reload: str = "not tried"
    removal: str = "not tried"
    cross: dict[str, str] = field(default_factory=dict)


def sh(*argv: str) -> None:
    subprocess.run(argv, check=True)


def decode(mask_hex: str) -> str:
    mask = int(mask_hex, 16)
    names = [n for bit, n in enumerate(CAP_NAMES) if mask >> bit & 1]
    return ",".join(names) if names else "-"


def proc_status(pid: int | str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in Path(f"/proc/{pid}/status").read_text().splitlines():
        key, _, value = line.partition(":")
        out[key] = value.strip()
    return out


def setup() -> list[str]:
    """Build ADR 055 §3's layout; return anything changed beyond it."""
    notes: list[str] = []
    try:
        pwd.getpwnam(APP_USER)
    except KeyError:
        sh(
            "useradd",
            "--system",
            "--user-group",
            "--no-create-home",
            "--shell",
            "/usr/sbin/nologin",
            APP_USER,
        )
    if APP_USER in grp.getgrnam(HOP3).gr_mem:
        msg = f"{APP_USER} must not be in the {HOP3} group (ADR 055 §5)"
        raise SystemExit(msg)

    # The app must traverse the path to its own tree; §3 does not say how.
    for parent in (Path("/home/hop3"), Path("/home/hop3/apps")):
        parent.mkdir(exist_ok=True)
        mode = parent.stat().st_mode & 0o777
        if not mode & 0o001:
            parent.chmod(mode | 0o001)
            notes.append(
                f"{parent} was {mode:o}; added o+x (traverse only) so the app "
                "user can reach its tree"
            )
    sh("chown", f"{HOP3}:{HOP3}", "/home/hop3/apps")

    layout = {
        "src": (HOP3, APP_USER, 0o750),
        # setgid: files the app creates inherit group hop3, which reads them
        "log": (APP_USER, HOP3, 0o2750),
        "data": (APP_USER, APP_USER, 0o700),
    }
    APP_ROOT.mkdir(exist_ok=True)
    sh("chown", f"{HOP3}:{HOP3}", str(APP_ROOT))
    APP_ROOT.chmod(0o751)
    for sub, (owner, group, mode) in layout.items():
        path = APP_ROOT / sub
        path.mkdir(exist_ok=True)
        sh("chown", f"{owner}:{group}", str(path))
        path.chmod(mode)

    src, log = APP_ROOT / "src", APP_ROOT / "log"
    files = {
        "probe_lib.py": APP_PY % {"sock": ROOTD_SOCK},
        "wsgi.py": WSGI_PY,
        "daemon.py": DAEMON_PY % {"src": src, "log": log},
    }
    for filename, text in files.items():
        path = src / filename
        path.write_text(text)
        sh("chown", f"{HOP3}:{APP_USER}", str(path))
        path.chmod(0o640)

    VASSALS.mkdir(exist_ok=True)
    sh("chown", f"{HOP3}:{HOP3}", str(VASSALS))

    # Root-owned: hop3 runs it with setuid/setgid, so hop3 must not edit it.
    WRAPPER.parent.mkdir(parents=True, exist_ok=True)
    WRAPPER.write_text(WRAPPER_SH)
    WRAPPER.chmod(0o755)
    return notes


def start_rootd_stand_in() -> subprocess.Popen:
    """A listener with rootd's socket mode, 0660 root:hop3."""
    ROOTD_SOCK.unlink(missing_ok=True)
    code = (
        "import os, socket, grp;"
        f"s = socket.socket(socket.AF_UNIX); s.bind('{ROOTD_SOCK}');"
        f"os.chown('{ROOTD_SOCK}', 0, grp.getgrnam('{HOP3}').gr_gid);"
        f"os.chmod('{ROOTD_SOCK}', 0o660); s.listen(8);"
        "[s.accept()[0].close() for _ in iter(int, 1)]"
    )
    proc = subprocess.Popen(["python3", "-c", code])
    deadline = time.monotonic() + 5
    while not ROOTD_SOCK.exists():
        if time.monotonic() > deadline:
            msg = "the rootd stand-in never created its socket"
            raise SystemExit(msg)
        time.sleep(0.05)
    return proc


def vassal_tree(emperor_pid: int) -> list[dict]:
    """Every process below the Emperor, whatever user it runs as."""
    statuses: dict[int, dict[str, str]] = {}
    for entry in Path("/proc").iterdir():
        if entry.name.isdigit():
            try:
                statuses[int(entry.name)] = proc_status(entry.name)
            except OSError:
                continue

    def below_emperor(pid: int) -> bool:
        while pid > 1:
            pid = int(statuses[pid]["PPid"]) if pid in statuses else 0
            if pid == emperor_pid:
                return True
        return False

    found = []
    for pid, st in statuses.items():
        if not below_emperor(pid):
            continue
        try:
            raw = Path(f"/proc/{pid}/cmdline").read_bytes()
        except OSError:
            continue
        # A zombie or an exiting process has an empty cmdline.
        cmdline = raw.replace(b"\0", b" ").decode().strip() or f"[{st['Name']}]"
        found.append({
            "pid": pid,
            "user": pwd.getpwuid(int(st["Uid"].split()[1])).pw_name,
            "cmd": cmdline.strip()[:60],
            "prm": decode(st["CapPrm"]),
            "eff": decode(st["CapEff"]),
            "amb": decode(st["CapAmb"]),
            "nnp": st.get("NoNewPrivs", "?"),
        })
    return sorted(found, key=itemgetter("pid"))


def stop_everything(emperor: subprocess.Popen) -> None:
    tree = [p["pid"] for p in vassal_tree(emperor.pid)]
    emperor.send_signal(signal.SIGINT)
    try:
        emperor.wait(timeout=10)
    except subprocess.TimeoutExpired:
        emperor.kill()
        emperor.wait()
    for pid in tree:
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)
    subprocess.run(["pkill", "-KILL", "-u", APP_USER], check=False)
    deadline = time.monotonic() + 5
    while survivors := [pid for pid in tree if Path(f"/proc/{pid}").exists()]:
        if time.monotonic() > deadline:
            msg = f"vassal processes survived teardown: {survivors}"
            raise SystemExit(msg)
        time.sleep(0.1)


def run_one(cap_set: str, spec: Emperor) -> Result:
    for stale in (APP_ROOT / "log").iterdir():
        stale.unlink()
    ini = VASSALS / "probe.ini"
    ini.write_text(
        VASSAL_INI.format(
            user=APP_USER,
            src=APP_ROOT / "src",
            log=APP_ROOT / "log",
            port=PORT,
            canary=CANARY,
        )
    )
    # Behind the wrapper, uWSGI reads its own config as the app user.
    sh("chown", f"{HOP3}:{APP_USER}", str(ini))
    ini.chmod(0o640)

    argv = []
    if spec.caps is not None:
        argv = ["setpriv", f"--reuid={HOP3}", f"--regid={HOP3}", "--init-groups"]
        if spec.caps:
            listed = ",".join(f"+{c}" for c in spec.caps)
            argv += [f"--inh-caps={listed}", f"--ambient-caps={listed}"]
    argv += [str(UWSGI), "--emperor", str(VASSALS)]
    if spec.wrapper:
        argv += ["--emperor-wrapper", str(WRAPPER)]

    emperor_log = Path(f"/tmp/emperor-{cap_set}.log")
    with emperor_log.open("w") as out:
        emperor = subprocess.Popen(argv, stdout=out, stderr=subprocess.STDOUT)
    try:
        result = measure(cap_set, emperor)
        if result.answered:
            result.reload = try_reload(emperor.pid, ini)
            result.removal = try_removal(emperor.pid, ini)
    finally:
        stop_everything(emperor)
    lines = emperor_log.read_text().splitlines()
    result.emperor_log_tail = "\n".join(lines[-15:])
    result.identity_lines = [line for line in lines if IDENTITY_MARK in line]
    return result


def measure(cap_set: str, emperor: subprocess.Popen) -> Result:
    """Everything observable while the Emperor and its vassal run."""
    web = poll_web()
    time.sleep(1)  # the attach-daemon writes its report on start
    daemon_json = APP_ROOT / "log" / "daemon.json"
    daemon = json.loads(daemon_json.read_text()) if daemon_json.exists() else None
    log = APP_ROOT / "log" / "web.1.log"
    if log.exists():
        st = log.stat()
        log_file = (
            f"{pwd.getpwuid(st.st_uid).pw_name}:"
            f"{grp.getgrgid(st.st_gid).gr_name} {st.st_mode & 0o777:o}"
        )
    else:
        log_file = "absent"
    return Result(
        cap_set=cap_set,
        emperor_caps={
            k: decode(proc_status(emperor.pid)[k])
            for k in ("CapPrm", "CapEff", "CapAmb")
        },
        answered=web is not None,
        web=web,
        daemon=daemon,
        processes=vassal_tree(emperor.pid),
        log_file=log_file,
        emperor_log_tail="",
        cross=cross_uid_checks(emperor.pid) if web is not None else {},
    )


def as_user(user: str, code: str) -> str:
    """Run a Python snippet as ``user`` with that user's own groups."""
    out = subprocess.run(
        ["setpriv", f"--reuid={user}", f"--regid={pwd.getpwnam(user).pw_gid}", "--init-groups",
         "python3", "-c", code],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    return (out.stdout or out.stderr).strip().splitlines()[-1]


def cross_uid_checks(emperor_pid: int) -> dict[str, str]:
    """What the control plane, and an unrelated user, can do to the app."""
    daemons = [
        p["pid"] for p in vassal_tree(emperor_pid)
        if p["cmd"].startswith("/usr/bin/python3")
    ]  # fmt: skip
    if not daemons:
        return {"daemon": "not found"}
    pid = daemons[0]

    def attempt(body: str) -> str:
        return (
            f"try:\n    {body}\n    print('yes')\n"
            "except OSError as e:\n    print(f'no ({e.strerror})')"
        )

    log = APP_ROOT / "log" / "daemon.1.log"
    scan = (
        "import glob\nhits = 0\nfor f in glob.glob('/proc/[0-9]*/cmdline'):\n"
        "    try:\n"
        f"        hits += b'{CANARY}' in open(f, 'rb').read()\n"
        "    except OSError:\n        pass\n"
        "print('YES, in a command line' if hits else 'no')"
    )
    return {
        "hop3 reads the app's log": as_user(HOP3, attempt(f"open('{log}').read(1)")),
        "hop3 reads the app's cwd": as_user(
            HOP3, attempt(f"__import__('os').readlink('/proc/{pid}/cwd')")
        ),
        "hop3 can signal the app": as_user(
            HOP3, attempt(f"__import__('os').kill({pid}, 0)")
        ),
        "nobody reads the app's secret": as_user("nobody", scan),
        "nobody reads the app's environ": as_user(
            "nobody", attempt(f"open('/proc/{pid}/environ').read(1)")
        ),
    }


def _uwsgi_pids(emperor_pid: int) -> set[int]:
    return {p["pid"] for p in vassal_tree(emperor_pid) if "uwsgi" in p["cmd"]}


def try_reload(emperor_pid: int, ini: Path) -> str:
    """Touch the vassal file; a reload respawns the vassal's processes."""
    before = _uwsgi_pids(emperor_pid)
    later = time.time() + 5
    os.utime(ini, (later, later))
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        after = _uwsgi_pids(emperor_pid)
        if after and after != before and poll_web() is not None:
            return "reloaded"
        time.sleep(0.25)
    return f"NOT RELOADED (uwsgi pids still {sorted(before)})"


def try_removal(emperor_pid: int, ini: Path) -> str:
    """Remove the vassal file; the Emperor must take the whole app down."""
    ini.unlink()
    start = time.monotonic()
    while time.monotonic() - start < 15:
        if not vassal_tree(emperor_pid):
            return f"gone in {time.monotonic() - start:.1f}s"
        time.sleep(0.25)
    left = [f"{p['pid']} ({p['user']})" for p in vassal_tree(emperor_pid)]
    return f"SURVIVED: {', '.join(left)}"


def poll_web() -> dict | None:
    deadline = time.monotonic() + START_TIMEOUT
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/", timeout=2) as r:
                return json.loads(r.read())
        except OSError:
            time.sleep(0.25)
    return None


def leaked(result: Result) -> list[str]:
    """Every way the app ended up holding privilege."""
    found = [
        f"pid {p['pid']} ({p['cmd'].split()[0]}) holds {kind}={p[kind]}"
        for p in result.processes
        for kind in ("prm", "eff", "amb")
        if p[kind] != "-"
    ]
    found += [
        f"pid {p['pid']} ({p['cmd'].split()[0]}) still runs as {p['user']}"
        for p in result.processes
        if p["user"] != APP_USER
    ]
    for where, rep in (("web worker", result.web), ("attach-daemon", result.daemon)):
        if rep is None:
            continue
        for test in ("setuid0_fork", "setuid0_exec"):
            if rep[test] != "refused":
                found.append(f"{where}: {test} -> {rep[test]}")
        if rep["rootd_socket"] == "CONNECTED":
            found.append(f"{where}: reached the 0660 root:hop3 socket")
    if result.cross.get("nobody reads the app's secret", "no") != "no":
        found.append("another user reads the app's environment from a command line")
    return found


def print_result(result: Result) -> None:
    print(f"\n=== emperor: {result.cap_set}")
    print(f"  emperor           {result.emperor_caps}")
    print(f"  vassal answered   {result.answered}")
    print(f"  log file          {result.log_file}")
    drops = "; ".join(line.strip() for line in result.identity_lines) or "none logged"
    print(f"  identity change   {drops}")
    for rep, where in ((result.web, "web worker"), (result.daemon, "attach-daemon")):
        if rep is None:
            print(f"  {where:<17} no report")
            continue
        st = rep["status"]
        print(
            f"  {where:<17} uid={st['Uid'].split()[1]} groups=[{st['Groups']}] "
            f"setuid0 fork={rep['setuid0_fork']} exec={rep['setuid0_exec']} "
            f"rootd={rep['rootd_socket']}"
        )
    print("  processes below the Emperor:")
    for p in result.processes:
        print(
            f"    {p['pid']:>6}  {p['user']:<15} prm={p['prm']:<26} "
            f"eff={p['eff']:<26} amb={p['amb']:<26} nnp={p['nnp']} {p['cmd']}"
        )
    print(f"  touch vassal      {result.reload}")
    print(f"  remove vassal     {result.removal}")
    for check, outcome in result.cross.items():
        print(f"  {check:<32} {outcome}")
    leaks = leaked(result)
    lifecycle_ok = result.reload == "reloaded" and result.removal.startswith("gone")
    if not result.answered:
        verdict = "vassal did not start"
    elif leaks:
        verdict = "LEAKS PRIVILEGE"
    elif not lifecycle_ok:
        verdict = "no privilege reaches the app, but the EMPEROR LOST CONTROL of it"
    else:
        verdict = "no privilege reaches the app; reload and removal work"
    print(f"  verdict           {verdict}")
    for leak in leaks:
        print(f"    - {leak}")
    if not result.answered or not lifecycle_ok:
        print("  emperor log (tail):")
        for line in result.emperor_log_tail.splitlines():
            print(f"    | {line}")


def run_inner() -> int:
    if os.geteuid() != 0:
        msg = "--inner runs as root inside the probe container"
        raise SystemExit(msg)
    if not UWSGI.exists():
        msg = f"{UWSGI} is missing: is this the hop3 e2e image?"
        raise SystemExit(msg)
    notes = setup()
    uwsgi_version = subprocess.run(
        [str(UWSGI), "--version"], capture_output=True, text=True, check=True
    ).stdout.strip()
    print(f"uWSGI {uwsgi_version}, kernel {os.uname().release}")
    for user in (HOP3, APP_USER):
        entry = pwd.getpwnam(user)
        print(f"user {user}: uid={entry.pw_uid} gid={entry.pw_gid}")
    for note in notes:
        print(f"layout: {note}")
    rootd = start_rootd_stand_in()
    try:
        for cap_set, spec in EMPERORS.items():
            print_result(run_one(cap_set, spec))
    finally:
        rootd.kill()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--inner", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    return run_inner() if args.inner else run_on_host(args.image)


if __name__ == "__main__":
    sys.exit(main())
