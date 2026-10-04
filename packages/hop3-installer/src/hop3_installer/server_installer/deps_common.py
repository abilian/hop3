# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Common dependency installation utilities shared across distros."""

from __future__ import annotations

import re
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from hop3_installer.common import (
    CommandError,
    InstallStepError,
    Spinner,
    cmd_exists,
    create_symlink,
    has_systemd,
    print_detail,
    print_error,
    print_failure_output,
    print_info,
    print_success,
    print_warning,
    run_cmd,
)
from hop3_installer.constants import HOME_DIR

from .config import ServerInstallerConfig
from .email import pre_stage_email
from .s3 import configure_s3
from .user import run_as_hop3, run_as_hop3_shell

# =============================================================================
# Non-interactive apt (Debian/Ubuntu)
# =============================================================================

# DEBIAN_FRONTEND=noninteractive alone does NOT suppress needrestart's whiptail
# "which services should be restarted?" dialog on Ubuntu 24.04 (Launchpad
# #1941716) -- that prompt reads the controlling terminal and blocks the whole
# install forever. NEEDRESTART_MODE=a makes needrestart restart services
# automatically, no prompt. Applied to EVERY apt invocation on the Debian family.
APT_NONINTERACTIVE_ENV = {
    "DEBIAN_FRONTEND": "noninteractive",
    "NEEDRESTART_MODE": "a",
}

# A freshly-booted cloud image runs apt-daily / unattended-upgrades on first
# boot, holding /var/lib/dpkg/lock-frontend for minutes. These flags make
# apt-get wait (bounded) for the lock instead of failing instantly or hanging
# unbounded, and are appended to every apt-get command.
APT_LOCK_FLAGS = ["-o", "DPkg::Lock::Timeout=600"]


# =============================================================================
# Declarative Package Specification
# =============================================================================


@dataclass
class PackageSpec:
    """
    Declarative specification for packages to install.

    This enables a more data-driven approach to package installation,
    making it easier to maintain and extend package lists.
    """

    # Package manager configuration
    pkg_manager: str  # "apt-get" or "dnf"
    update_cmd: list[str] | None = None  # Command to update package lists
    env_vars: dict[str, str] = field(default_factory=dict)

    # Extra flags for install command (e.g., ["--no-install-recommends"] for apt)
    # This prevents unwanted packages like Apache from being pulled in as
    # recommended dependencies of PHP packages
    install_flags: list[str] = field(default_factory=list)

    # Package lists
    base_packages: list[str] = field(default_factory=list)
    docker_packages: list[str] = field(default_factory=list)
    mysql_packages: list[str] = field(default_factory=list)
    redis_packages: list[str] = field(default_factory=list)
    # What the official Nix installer needs and a minimal image lacks: `xz`
    # to unpack its tarball (ubuntu:24.04 ships neither xz nor curl).
    nix_packages: list[str] = field(default_factory=list)

    # Commands that need special handling (check before install)
    conditional_packages: dict[str, str] = field(default_factory=dict)
    # Maps command name -> package name, e.g., {"npm": "npm"}


# =============================================================================
# Shared Package Installation Functions
# =============================================================================


def install_base_packages(spec: PackageSpec) -> None:
    """Install base packages using the given spec."""
    # Update package lists if needed
    if spec.update_cmd:
        with Spinner("Updating package lists..."):
            run_cmd(spec.update_cmd)

    # Build install command with optional flags
    install_cmd = [spec.pkg_manager, "install", "-y"]
    if spec.install_flags:
        install_cmd.extend(spec.install_flags)
    install_cmd.extend(spec.base_packages)

    # Install base packages
    with Spinner("Installing base packages (this may take a while)..."):
        result = run_cmd(
            install_cmd,
            env=spec.env_vars or None,
            check=False,
        )

    if result.returncode != 0:
        print_error("Base package installation failed")
        # apt reports *why* on stdout and only the summary on stderr, so
        # printing stderr alone leaves "dpkg returned an error code (1)" and no
        # cause. Show both, stdout last: it holds the failing package.
        print_failure_output("stderr", result.stderr)
        print_failure_output("stdout", result.stdout)
        raise CommandError(
            [spec.pkg_manager, "install"] + spec.base_packages,
            result.returncode,
            "\n".join(filter(None, [result.stdout, result.stderr])),
        )

    print_success(f"Installed {len(spec.base_packages)} base packages")

    # Handle conditional packages (packages that may conflict)
    for cmd_name, pkg_name in spec.conditional_packages.items():
        install_conditional_package(cmd_name, pkg_name, spec)


def install_conditional_package(
    cmd_name: str, pkg_name: str, spec: PackageSpec
) -> None:
    """Install a package only if the command doesn't already exist."""
    if cmd_exists(cmd_name):
        print_success(f"{cmd_name} already available")
        return

    # Build install command with optional flags
    install_cmd = [spec.pkg_manager, "install", "-y"]
    if spec.install_flags:
        install_cmd.extend(spec.install_flags)
    install_cmd.append(pkg_name)

    print_info(f"{cmd_name} not found, installing {pkg_name}...")
    with Spinner(f"Installing {pkg_name}..."):
        result = run_cmd(
            install_cmd,
            env=spec.env_vars or None,
            check=False,
        )
    if result.returncode != 0:
        print_error(f"{pkg_name} installation failed")
        print_failure_output("stderr", result.stderr)
        print_failure_output("stdout", result.stdout)
        raise CommandError(
            cmd=install_cmd,
            returncode=result.returncode,
            stdout=result.stdout or "",
            stderr=result.stderr or "",
        )
    print_success(f"{pkg_name} installed")


def install_optional_packages(
    config: ServerInstallerConfig,
    spec: PackageSpec,
    configure_redis_func: Callable[[], None],
) -> None:
    """Install optional packages based on config."""
    if config.with_docker:
        install_feature_packages("Docker", spec.docker_packages, spec)
        # Start Docker daemon so docker0 interface exists for database binding
        _start_docker_daemon()

    if config.with_mysql:
        if not cmd_exists("mysql"):
            install_feature_packages("MySQL", spec.mysql_packages, spec)
        else:
            print_success("MySQL already installed")

    if config.with_redis:
        if not cmd_exists("redis-server"):
            install_feature_packages("Redis", spec.redis_packages, spec)
        else:
            print_success("Redis already installed")
        configure_redis_func()

    if config.with_nix and not cmd_exists("xz"):
        install_feature_packages("Nix prerequisite", spec.nix_packages, spec)
    if config.with_s3:
        # S3 (MinIO) is downloaded as a standalone binary, not from apt.
        # Delegate to the distro-agnostic configure_s3 function.
        configure_s3()

    if config.with_email:
        # Pre-stage Postfix inert; the loopback relay is configured later by
        # the rootd postfix.configure op on email-backend selection (ADR 054).
        pre_stage_email()


def _start_docker_daemon() -> None:
    """
    Start the Docker daemon and wait for its docker0 bridge.

    The databases are then configured to listen on the bridge, so a daemon
    that is not running leaves Docker-built apps unable to build and to reach
    them. Docker was requested (`--with docker`), so either outcome aborts.
    """
    if not has_systemd():
        msg = (
            "Docker was requested (--with docker), but this host has no "
            "systemd to run dockerd: on a container target, deploy without "
            "`docker` in --with"
        )
        raise InstallStepError(msg)

    run_cmd(["systemctl", "enable", "docker"])
    run_cmd(["systemctl", "start", "docker"])

    # docker0 typically appears within 1-3 seconds of the daemon starting.
    for _i in range(10):
        if run_cmd(["ip", "addr", "show", "docker0"], check=False).returncode == 0:
            print_success("Docker daemon started")
            return
        time.sleep(1)
    msg = "Docker started, but its docker0 bridge did not appear within 10 seconds"
    raise InstallStepError(msg)


def install_feature_packages(name: str, packages: list[str], spec: PackageSpec) -> None:
    """Install a set of feature packages."""
    # Build install command with optional flags
    install_cmd = [spec.pkg_manager, "install", "-y"]
    if spec.install_flags:
        install_cmd.extend(spec.install_flags)
    install_cmd.extend(packages)

    with Spinner(f"Installing {name} packages..."):
        result = run_cmd(
            install_cmd,
            env=spec.env_vars or None,
            check=False,
        )
    if result.returncode == 0:
        print_success(f"{name} packages installed")
        return

    # Every caller is guarded by `config.with_<feature>`, so reaching here means
    # the operator asked for this feature by name and did not get it. A warning
    # let the install continue and report success: `--with mysql` printed one
    # line, then apps needing MySQL deployed against a database that was never
    # configured. Abort, like the catalogue baseline below.
    #
    # Both streams: the failure that hid behind this was mysql-server's postinst
    # reporting "Unable to shut down server with process id ..." on *stdout*,
    # while the five stderr lines shown said only that apt-utils was missing —
    # which is a warning, and not the reason for anything.
    print_error(f"{name} installation failed")
    for stream in (result.stdout, result.stderr):
        for line in (stream or "").strip().split("\n")[-8:]:
            if line:
                print_detail(line)
    raise CommandError(
        cmd=install_cmd,
        returncode=result.returncode,
        stderr=(result.stderr or "").strip(),
        stdout=(result.stdout or "").strip(),
    )


# =============================================================================
# Node.js Global Packages
# =============================================================================


#: The pnpm every Hop3 server runs. Pinned, and reconciled on every install.
#:
#: This was `npm install -g pnpm`, skipped whenever any pnpm was already there.
#: So the version an app built with was whatever npm's `latest` tag pointed at
#: on the day that server was installed, and it moved under the app afterwards
#: with no change to the app, the recipe, or Hop3. Two servers of the same Hop3
#: version built the same app differently, which is the reproducibility the
#: blank-slate rebuild exists to protect everywhere else.
#:
#: Etherpad absorbed three breaking pnpm changes this way, two of them patched
#: into its own download.sh. The third could not be: pnpm 12 removed
#: `pnpm list --no-production`, which Etherpad's plugin migration runs at every
#: boot, so the build succeeded and the app died four seconds into startup.
#: 9, 10 and 11 accept the flag; 12 does not.
#:
#: Bump this deliberately, and re-run the catalog's Node apps when you do —
#: that is the whole point of it being a decision rather than a date.
PNPM_VERSION = "11.27.0"


def install_node_global_packages() -> None:
    """
    Install global npm packages needed for various apps.

    pnpm is a fast, disk space efficient package manager that is required
    by some apps (Etherpad, HedgeDoc, etc.) that use pnpm workspaces.
    """
    # Check if npm is available
    # Node is part of every server, so its package tooling is too: without
    # the pinned pnpm and nodeenv, pnpm apps and [build].node-version pins
    # fail at build time on a server that reported a good install.
    if not cmd_exists("npm"):
        msg = "npm is not on PATH after the Node install, so pnpm and nodeenv cannot be installed"
        raise InstallStepError(msg)

    _install_pnpm()

    # nodeenv (for per-app [build].node-version pins) is installed separately:
    # it is a PyPI tool, not an npm package — see _install_nodeenv.
    _install_nodeenv()


def _install_pnpm() -> None:
    """Install :data:`PNPM_VERSION`, replacing whatever version is present."""
    installed = _pnpm_version()
    if installed == PNPM_VERSION:
        print_info(f"pnpm {PNPM_VERSION} already installed")
        return

    if installed:
        print_info(f"Replacing pnpm {installed} with the pinned {PNPM_VERSION}...")
    else:
        print_info(f"Installing pnpm {PNPM_VERSION}...")
    with Spinner(f"Installing pnpm {PNPM_VERSION} globally..."):
        run_cmd(["npm", "install", "-g", f"pnpm@{PNPM_VERSION}"])

    # Say so when the pin did not take. A pnpm installed by some other route
    # (corepack, the standalone script) shadows npm's global bin on PATH, and
    # the silent outcome would be the drift this pin exists to end — with the
    # installer reporting the version it meant to install.
    effective = _pnpm_version()
    if not effective:
        msg = f"installed pnpm {PNPM_VERSION} with npm, but no pnpm is on PATH"
        raise InstallStepError(msg)
    if effective != PNPM_VERSION:
        msg = (
            f"installed pnpm {PNPM_VERSION}, but `pnpm --version` reports "
            f"{effective}: another pnpm is ahead of it on PATH, and apps would "
            f"build with that one"
        )
        raise InstallStepError(msg)
    print_success(f"pnpm {PNPM_VERSION} installed")


def _pnpm_version() -> str:
    """The version `pnpm` on PATH reports, or "" when there is none."""
    if not cmd_exists("pnpm"):
        return ""
    result = run_cmd(["pnpm", "--version"], check=False)
    return result.stdout.strip() if result.returncode == 0 else ""


# nodeenv lives in its own venv, symlinked onto the build PATH (mirrors Rust).
# /opt is root-owned and exists before the hop3 user/venv are created (this runs
# at step 1, the venv at step 3).
_NODEENV_VENV = Path("/opt/hop3/nodeenv-venv")
_NODEENV_BIN = Path("/usr/local/bin/nodeenv")


def _install_nodeenv() -> None:
    """
    Install ekalinin's nodeenv (PyPI) so [build].node-version pins work.

    Critically NOT `npm install -g nodeenv`: the npm package of that name is an
    unrelated test utility ("control Node.js environment variables") that ships
    no `nodeenv` executable, so the Node toolchain's `nodeenv --prebuilt
    --node=<v>` call could never find it. The real tool is on PyPI. It is
    installed into a dedicated venv and symlinked into /usr/local/bin (on the
    server's build PATH), the same way the Rust tools are exposed.

    Don't swallow a failure silently: a missing nodeenv makes every pinned
    [build].node-version abort at deploy time, so surface why it didn't install.
    """
    if _NODEENV_BIN.exists():
        print_info("nodeenv already installed")
        return

    print_info("Installing nodeenv (PyPI)...")
    with Spinner("Creating nodeenv venv..."):
        run_cmd(["python3", "-m", "venv", str(_NODEENV_VENV)])
    with Spinner("Installing nodeenv into venv..."):
        run_cmd([str(_NODEENV_VENV / "bin" / "pip"), "install", "--upgrade", "nodeenv"])
    if not create_symlink(_NODEENV_VENV / "bin" / "nodeenv", _NODEENV_BIN):
        msg = (
            f"installed nodeenv but could not symlink it to {_NODEENV_BIN}, "
            f"so it is not on the build PATH"
        )
        raise InstallStepError(msg)
    print_success(f"nodeenv installed: {_NODEENV_BIN}")


# =============================================================================
# Rust Toolchain
# =============================================================================


def _toolchain_failed(
    msg: str,
    result: subprocess.CompletedProcess | None,
    *,
    required: bool,
) -> None:
    """
    Report an optional toolchain's failure; raise if it was requested.

    Rust, Leiningen and Elixir are installed on every server, best-effort:
    an app that needs one fails at its build, saying so. Requested by name
    (`--with rust|clojure|elixir`), the toolchain is a promise, and its
    failure stops the install.
    """
    (print_error if required else print_warning)(msg)
    if result is not None:
        print_failure_output("stderr", result.stderr, lines=8)
    if required:
        raise CommandError(
            cmd=[msg],
            returncode=result.returncode if result is not None else 1,
            stdout=(result.stdout or "") if result is not None else "",
            stderr=(result.stderr or msg) if result is not None else msg,
        )


def _verify_or_repair_cargo(
    cargo_path: Path, rustup_path: Path
) -> subprocess.CompletedProcess:
    """
    Return `cargo --version`; on failure, force-reinstall stable once first.

    A flaky component download (or a stale ~/.rustup) can leave the cargo PROXY
    present while the stable toolchain has no cargo ("cargo ... is not applicable
    to the 'stable-...' toolchain"). One forced toolchain reinstall self-heals
    that; the caller still fails loud when the returned result is non-zero.
    """
    verify = run_as_hop3([str(cargo_path), "--version"])
    if verify.returncode == 0:
        return verify
    print_detail("cargo not usable; reinstalling the stable toolchain...")
    with Spinner("Repairing the Rust stable toolchain..."):
        run_as_hop3(
            [
                str(rustup_path),
                "toolchain",
                "install",
                "stable",
                "--profile",
                "minimal",
                "--force",
            ],
            timeout=600,
        )
    return run_as_hop3([str(cargo_path), "--version"])


def install_catalogue_baseline(os_family: str) -> None:
    """
    Install the catalogue-derived package baseline.

    Reads the list from `baselines.py` (generated from
    apps/*/hop3.toml via `python -m ...baseline`), translates to the
    local OS family, and apt/dnf-installs. Idempotent: reruns on an
    already-baselined host are cheap.

    Runs AFTER the static base packages in deps_{debian,fedora}.py —
    those provide the common stack (python, node, ruby, php, libssl-dev,
    ...); this step adds whatever else the catalogue declares on top.
    """
    from .baselines import BASELINE_PACKAGES  # ruff:ignore[import-outside-top-level]

    packages = BASELINE_PACKAGES.get(os_family)
    # Callers pass only the supported families, so an empty list means the
    # generated baselines.py is broken, and native-profile apps would not build.
    if not packages:
        msg = f"baselines.py has no catalogue baseline for OS family {os_family!r}"
        raise InstallStepError(msg)

    # Defence in depth against a stale baselines.py: never apt/dnf-install Node's
    # distro packages — Node comes from NodeSource (see _NODESOURCE_PROVIDED).
    # Installing the distro nodejs/libnode-dev alongside NodeSource is an
    # unsatisfiable conflict that aborts the whole baseline.
    skipped = [p for p in packages if _is_nodesource_provided(p)]
    packages = [p for p in packages if not _is_nodesource_provided(p)]
    if skipped:
        print_detail(f"Skipping NodeSource-provided package(s): {', '.join(skipped)}")

    # `apt-get install` if already-installed is a near-noop.
    pkg_manager = "apt-get" if os_family == "debian" else "dnf"
    is_apt = pkg_manager == "apt-get"
    lock_flags = APT_LOCK_FLAGS if is_apt else []
    apt_env = APT_NONINTERACTIVE_ENV if is_apt else None
    # --no-install-recommends, as every other apt call in the provisioning path
    # already does. The baseline is a list of packages the catalogue *declared*;
    # recommends are by definition not declared, and on a server they are mostly
    # wrong. Concretely: `imagemagick` alone pulled ~50 extra packages including
    # systemd-resolved, an icon theme and a font cache rebuild. A wider graph is
    # also a wider surface for an unsatisfiable conflict to abort the whole step
    # — which is exactly how a 25-package baseline started failing where an
    # 8-package one did not.
    recommends_flags = ["--no-install-recommends"] if is_apt else []
    install_cmd = [
        pkg_manager,
        "install",
        "-y",
        *recommends_flags,
        *lock_flags,
        *packages,
    ]
    with Spinner(f"Installing catalogue baseline ({len(packages)} package(s))..."):
        result = run_cmd(install_cmd, env=apt_env, check=False)

    if result.returncode == 0:
        print_success(f"Catalogue baseline installed ({len(packages)} packages)")
        return

    # Never swallow this: a failed baseline leaves native-profile apps unable to
    # build, and a warning here is how a real conflict (e.g. NodeSource vs the
    # distro nodejs) stayed hidden while every Node app failed downstream. Abort
    # loudly so the operator fixes provisioning instead of chasing per-app errors.
    print_error("Catalogue baseline install failed")
    # Same reasoning as install_base_packages above, and the same helper: apt
    # reports *why* on stdout and only the one-line verdict on stderr, so the
    # stderr tail alone gave "E: Error, pkgProblemResolver::Resolve generated
    # breaks" with no way to tell which package. Echo both, stdout last.
    print_failure_output("stderr", result.stderr)
    print_failure_output("stdout", result.stdout)
    raise CommandError(
        cmd=install_cmd,
        returncode=result.returncode,
        stderr="\n".join(filter(None, [result.stdout, result.stderr])),
        stdout=result.stdout or "",
    )


# NodeSource owns the Node toolchain (node, npm, node-gyp, headers). These
# distro package names must never reach apt/dnf or they conflict with it. Kept in
# sync with hop3_installer.server_installer.baseline.NODESOURCE_PROVIDED (the
# generator drops them from baselines.py; this is the install-time backstop).
_NODESOURCE_PROVIDED: frozenset[str] = frozenset({
    "nodejs",
    "npm",
    "node-gyp",
    "libnode-dev",
    "nodejs-devel",
})


def _is_nodesource_provided(package: str) -> bool:
    """True if ``package`` is a distro Node package NodeSource already provides."""
    return package in _NODESOURCE_PROVIDED


def install_rust_toolchain(*, required: bool = False) -> None:
    """
    Install Rust toolchain via rustup.

    Rust is installed using rustup for the hop3 user so Rust-native
    apps (vaultwarden, etc.) can build. Symlinks are created in
    /usr/local/bin for system-wide access.

    Args:
        required: If True, raise CommandError on failure (for
            `--with=rust`). If False, log warnings and continue (keeps
            backwards-compatible optional-install behaviour).
    """
    cargo_path = HOME_DIR / ".cargo" / "bin" / "cargo"
    rustc_path = HOME_DIR / ".cargo" / "bin" / "rustc"
    rustup_path = HOME_DIR / ".cargo" / "bin" / "rustup"

    # Check if cargo actually works for the hop3 user
    if cargo_path.exists():
        result = run_as_hop3([str(cargo_path), "--version"])
        if result.returncode == 0:
            print_info(f"Rust toolchain already installed: {result.stdout.strip()}")
            _create_rust_symlinks(
                cargo_path, rustc_path, rustup_path, required=required
            )
            return

    print_info("Installing Rust toolchain via rustup...")

    # Remove any broken symlinks first
    for symlink in [
        "/usr/local/bin/cargo",
        "/usr/local/bin/rustc",
        "/usr/local/bin/rustup",
    ]:
        symlink_path = Path(symlink)
        if symlink_path.is_symlink() and not symlink_path.exists():
            print_detail(f"Removing broken symlink: {symlink}")
            symlink_path.unlink()

    # rustup-init fetched via curl, piped into sh with -y (non-interactive).
    # --default-toolchain stable pins the channel; rustup would ask
    # otherwise.
    with Spinner("Downloading and installing rustup..."):
        result = run_as_hop3_shell(
            'curl --proto "=https" --tlsv1.2 -sSf https://sh.rustup.rs '
            "| sh -s -- -y --default-toolchain stable --profile minimal",
            timeout=600,
        )

    if result.returncode != 0:
        _toolchain_failed(
            "Rust installation via rustup failed", result, required=required
        )
        return

    if not cargo_path.exists():
        _toolchain_failed(
            "Rust installation reported success but cargo binary not found",
            None,
            required=required,
        )
        return

    # Verify cargo runs (path-exists alone was insufficient on at least
    # one host where rustup dropped a stub that couldn't exec).
    verify = _verify_or_repair_cargo(cargo_path, rustup_path)
    if verify.returncode != 0:
        _toolchain_failed(
            "Rust installed but `cargo --version` exits non-zero",
            verify,
            required=required,
        )
        return

    print_success("Rust toolchain installed")
    print_detail(f"Version: {verify.stdout.strip()}")
    _create_rust_symlinks(cargo_path, rustc_path, rustup_path, required=required)


def _create_rust_symlinks(
    cargo_path: Path, rustc_path: Path, rustup_path: Path, *, required: bool = False
) -> None:
    """
    Create symlinks in /usr/local/bin for Rust tools.

    This makes cargo, rustc, and rustup accessible system-wide,
    which is needed when subprocess runs commands without the hop3 user's PATH.
    """
    symlinks = [
        (cargo_path, Path("/usr/local/bin/cargo")),
        (rustc_path, Path("/usr/local/bin/rustc")),
        (rustup_path, Path("/usr/local/bin/rustup")),
    ]

    for source, target in symlinks:
        if create_symlink(source, target):
            print_detail(f"Created symlink: {target} -> {source}")
        elif source.exists():
            # Builds run without the hop3 user's PATH, so without the link
            # Rust is installed and unusable.
            _toolchain_failed(
                f"Could not create symlink {target}", None, required=required
            )


# =============================================================================
# Clojure/Leiningen
# =============================================================================


def install_leiningen(*, required: bool = False) -> None:
    """
    Install Leiningen (Clojure build tool).

    Leiningen is installed system-wide in /usr/local/bin.
    The actual JAR is downloaded on first run by the hop3 user.

    Args:
        required: Raise on failure (`--with clojure`) instead of warning.
    """
    lein_path = Path("/usr/local/bin/lein")

    # Check if lein is already installed and working
    if lein_path.exists():
        result = run_cmd(["lein", "version"], check=False)
        if result.returncode == 0:
            print_info(f"Leiningen already installed: {result.stdout.strip()}")
            return

    print_info("Installing Leiningen (Clojure build tool)...")

    # Download lein script
    lein_url = "https://raw.githubusercontent.com/technomancy/leiningen/stable/bin/lein"
    with Spinner("Downloading Leiningen..."):
        result = run_cmd(
            ["curl", "-fsSL", "-o", str(lein_path), lein_url],
            check=False,
        )

    if result.returncode != 0:
        _toolchain_failed("Failed to download Leiningen", result, required=required)
        return

    # Make executable
    lein_path.chmod(0o755)

    # Run lein once as hop3 user to download the JAR
    # This sets up ~/.lein for the hop3 user
    with Spinner("Initializing Leiningen (downloading JAR)..."):
        result = run_as_hop3(["lein", "version"])

    if result.returncode == 0:
        print_success(f"Leiningen installed: {result.stdout.strip()}")
    else:
        _toolchain_failed(
            "Leiningen script installed but initialization failed",
            result,
            required=required,
        )


# =============================================================================
# Elixir
# =============================================================================

# Pinned, recent Elixir. Phoenix's `phx_new` requires ~> 1.15; Debian/Ubuntu's
# apt `elixir` is 1.14, so we install a precompiled release instead. v1.17.x
# ships builds for OTP 25/26/27 (the OTP versions on current distros).
ELIXIR_VERSION = "1.17.3"
_ELIXIR_DIR = Path("/opt/elixir")
_ELIXIR_BINS = ("elixir", "elixirc", "mix", "iex")


def install_elixir(*, required: bool = False) -> None:
    """
    Install a modern Elixir (>= 1.15) for Phoenix and other Elixir apps.

    Debian/Ubuntu ship Elixir 1.14, which recent Phoenix rejects. We keep the
    distribution's Erlang/OTP, installed with the base packages, and drop in a
    precompiled Elixir matching its OTP major version, symlinked into
    /usr/local/bin so it takes precedence over the distribution's `elixir`.

    A failure leaves Elixir apps unbuildable, which their deploy reports; it
    stops the install when Elixir was requested (`--with elixir`).

    Args:
        required: Raise on failure instead of warning.
    """
    if _elixir_is_recent_enough():
        print_info("Elixir >= 1.15 already installed")
        return

    # Erlang comes from the distribution's base packages (step 1, which
    # aborts on failure), so no `erl` means this distribution ships none: a
    # fact about the platform, said once, unless Elixir was asked for.
    if not cmd_exists("erl"):
        reason = "this distribution's packages provide no Erlang/OTP"
        if required:
            msg = f"--with elixir: {reason}"
            raise InstallStepError(msg)
        print_info(f"Elixir not installed: {reason}")
        return

    otp_major = _detect_otp_major()
    if not otp_major:
        _toolchain_failed(
            "Elixir install failed: could not detect the Erlang/OTP version",
            None,
            required=required,
        )
        return

    url = (
        "https://github.com/elixir-lang/elixir/releases/download/"
        f"v{ELIXIR_VERSION}/elixir-otp-{otp_major}.zip"
    )
    zip_path = Path("/tmp/elixir.zip")
    print_info(f"Installing Elixir {ELIXIR_VERSION} (OTP {otp_major})...")
    with Spinner("Downloading Elixir..."):
        result = run_cmd(["curl", "-fsSL", "-o", str(zip_path), url], check=False)
    if result.returncode != 0:
        _toolchain_failed(
            f"Elixir install failed: download error. No prebuilt Elixir "
            f"{ELIXIR_VERSION} for OTP {otp_major}? ({url})",
            result,
            required=required,
        )
        return

    # Fresh extract so a prior install leaves no stale files.
    run_cmd(["rm", "-rf", str(_ELIXIR_DIR)], check=False)
    _ELIXIR_DIR.mkdir(parents=True, exist_ok=True)
    with Spinner("Extracting Elixir..."):
        result = run_cmd(
            ["python3", "-m", "zipfile", "-e", str(zip_path), str(_ELIXIR_DIR)],
            check=False,
        )
    if result.returncode != 0:
        _toolchain_failed(
            "Elixir install failed: could not extract the release archive",
            result,
            required=required,
        )
        return

    for name in _ELIXIR_BINS:
        bin_path = _ELIXIR_DIR / "bin" / name
        if bin_path.exists():
            bin_path.chmod(0o755)
            create_symlink(bin_path, Path("/usr/local/bin") / name)

    result = run_cmd(["elixir", "--version"], check=False)
    if result.returncode == 0:
        print_success(f"Elixir installed: {_elixir_version_line(result.stdout)}")
    else:
        _toolchain_failed(
            "Elixir install failed: `elixir --version` did not run after install",
            result,
            required=required,
        )


def _elixir_is_recent_enough() -> bool:
    """True if a usable Elixir >= 1.15 is already on PATH."""
    if not cmd_exists("elixir"):
        return False
    result = run_cmd(["elixir", "--version"], check=False)
    return result.returncode == 0 and _elixir_at_least(result.stdout, (1, 15))


def _detect_otp_major() -> str | None:
    """Return the installed Erlang/OTP major version (e.g. "25"), or None."""
    result = run_cmd(
        [
            "erl",
            "-noshell",
            "-eval",
            'io:format("~s", [erlang:system_info(otp_release)]), halt().',
        ],
        check=False,
    )
    if result.returncode != 0:
        return None
    major = result.stdout.strip().split(".")[0].strip()
    return major if major.isdigit() else None


def _elixir_at_least(version_output: str, minimum: tuple[int, int]) -> bool:
    match = re.search(r"Elixir (\d+)\.(\d+)", version_output)
    if not match:
        return False
    return (int(match.group(1)), int(match.group(2))) >= minimum


def _elixir_version_line(version_output: str) -> str:
    for line in version_output.splitlines():
        if line.strip().startswith("Elixir "):
            return line.strip()
    stripped = version_output.strip()
    return stripped.split("\n")[-1] if stripped else "(unknown)"


# =============================================================================
# .NET SDK
# =============================================================================


def _detect_debian_version() -> tuple[str, str]:
    """
    Detect Debian/Ubuntu version for Microsoft repo URL.

    Returns:
        Tuple of (distro, version) e.g., ("ubuntu", "24.04") or ("debian", "12")
    """
    # Try /etc/os-release first (works on most modern systems)
    os_release = Path("/etc/os-release")
    if os_release.exists():
        content = os_release.read_text()
        distro = ""
        version = ""
        for line in content.split("\n"):
            if line.startswith("ID="):
                distro = line.split("=")[1].strip().strip('"').lower()
            elif line.startswith("VERSION_ID="):
                version = line.split("=")[1].strip().strip('"')
        if distro and version:
            return (distro, version)

    # Fallback to Ubuntu 24.04 as default
    return ("ubuntu", "24.04")


#: The long-term-support SDKs. 9 was a short-term release, out of support in
#: November 2026, and no feed carries it for Ubuntu 24.04, where its install
#: failed on every server and was reported as a warning.
DOTNET_SDK_VERSIONS = ("8.0", "10.0")


def install_dotnet_sdk_debian() -> None:
    """Install .NET SDKs on Debian/Ubuntu, Microsoft's repository added.

    Ubuntu ships its own .NET packages; Debian has none, so the repository is
    what makes an SDK available there at all.
    """
    _add_microsoft_repository()
    with Spinner("Updating package lists..."):
        run_cmd(["apt-get", "update", "-q", *APT_LOCK_FLAGS], check=False)
    _install_dotnet_sdks(
        is_offered=_apt_offers,
        install_cmd=lambda pkg: ["apt-get", "install", "-y", *APT_LOCK_FLAGS, pkg],
        env=APT_NONINTERACTIVE_ENV,
    )


def install_dotnet_sdk_fedora() -> None:
    """Install .NET SDKs on Fedora, which has them in its own repositories."""
    _install_dotnet_sdks(
        is_offered=lambda pkg: (
            run_cmd(["dnf", "-q", "list", "--available", pkg], check=False).returncode
            == 0
        ),
        install_cmd=lambda pkg: ["dnf", "install", "-y", pkg],
    )


def _install_dotnet_sdks(
    *,
    is_offered: Callable[[str], bool],
    install_cmd: Callable[[str], list[str]],
    env: dict[str, str] | None = None,
) -> None:
    """
    Install every long-term SDK the platform publishes, and abort on failure.

    No feed publishes both for every platform: Debian 12 on arm64 has no SDK
    8, Ubuntu 22.04 on arm64 no SDK 10. One that is not published is named, so
    a build targeting it fails with an explanation already on record; one that
    is published and fails to install, or a platform with neither, aborts.
    Installing is idempotent, so a redeploy reconciles an existing server.
    """
    packages = [f"dotnet-sdk-{version}" for version in DOTNET_SDK_VERSIONS]
    offered = [pkg for pkg in packages if is_offered(pkg)]
    for pkg in packages:
        if pkg not in offered:
            print_info(f"{pkg} is not published for this platform; not installed")
    if not offered:
        msg = (
            f"no .NET SDK ({', '.join(packages)}) is published for this "
            f"platform, so .NET apps cannot be built on it"
        )
        print_error(msg)
        raise CommandError(cmd=["dotnet-sdk"], returncode=1, stderr=msg)
    for pkg in offered:
        with Spinner(f"Installing {pkg}..."):
            result = run_cmd(install_cmd(pkg), env=env, check=False)
        if result.returncode != 0:
            print_error(f"{pkg} installation failed")
            print_failure_output("stderr", result.stderr)
            print_failure_output("stdout", result.stdout)
            raise CommandError(
                cmd=install_cmd(pkg),
                returncode=result.returncode,
                stdout=result.stdout or "",
                stderr=result.stderr or "",
            )
        print_success(f"{pkg} installed")


def _apt_offers(pkg: str) -> bool:
    """Whether apt has an install candidate for ``pkg``."""
    result = run_cmd(["apt-cache", "policy", pkg], check=False)
    candidate = re.search(r"Candidate:\s*(\S+)", result.stdout or "")
    return candidate is not None and candidate.group(1) != "(none)"


def _add_microsoft_repository() -> None:
    """
    Add Microsoft's package repository for this distribution version.

    A failure is reported and not fatal by itself: what matters is whether
    an SDK is then offered, which ``_install_dotnet_sdks`` checks and aborts
    on. On Ubuntu the distribution's own packages are enough.
    """
    distro, version = _detect_debian_version()
    print_detail(f"Detected {distro} {version}")
    repo_url = (
        f"https://packages.microsoft.com/config/{distro}/{version}/"
        "packages-microsoft-prod.deb"
    )
    deb = "/tmp/packages-microsoft-prod.deb"
    with Spinner("Adding Microsoft package repository..."):
        result = run_cmd(["wget", "-q", repo_url, "-O", deb], check=False)
        if result.returncode == 0:
            result = run_cmd(["dpkg", "-i", deb], check=False)
        run_cmd(["rm", "-f", deb], check=False)
    if result.returncode != 0:
        print_warning(f"Could not add Microsoft's repository from {repo_url}")
