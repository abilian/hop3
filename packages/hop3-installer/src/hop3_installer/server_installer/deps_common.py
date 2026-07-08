# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Common dependency installation utilities shared across distros."""

from __future__ import annotations

import re
import subprocess  # noqa: TC003
import time
from collections.abc import Callable  # noqa: TC003
from dataclasses import dataclass, field
from pathlib import Path

from hop3_installer.common import (
    CommandError,
    Spinner,
    cmd_exists,
    create_symlink,
    print_detail,
    print_error,
    print_info,
    print_success,
    print_warning,
    run_cmd,
)
from hop3_installer.constants import HOME_DIR

from .config import ServerInstallerConfig
from .email import pre_stage_email
from .s3 import configure_s3
from .user import run_as_hop3

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
    """Declarative specification for packages to install.

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
        if result.stderr:
            for line in result.stderr.strip().split("\n")[-10:]:
                print_detail(line)
        raise CommandError(
            [spec.pkg_manager, "install"] + spec.base_packages,
            result.returncode,
            result.stderr or "",
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
    if result.returncode == 0:
        print_success(f"{pkg_name} installed")
    else:
        print_warning(
            f"{pkg_name} installation failed (may conflict with other packages)"
        )


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

    if config.with_s3:
        # S3 (MinIO) is downloaded as a standalone binary, not from apt.
        # Delegate to the distro-agnostic configure_s3 function.
        configure_s3()

    if config.with_email:
        # Pre-stage Postfix inert; the loopback relay is configured later by
        # the rootd postfix.configure op on email-backend selection (ADR 054).
        pre_stage_email()


def _start_docker_daemon() -> None:
    """Start Docker daemon and wait for it to be ready.

    This ensures the docker0 bridge interface exists before configuring
    databases to listen on it.
    """
    # Enable and start Docker
    run_cmd(["systemctl", "enable", "docker"], check=False)
    result = run_cmd(["systemctl", "start", "docker"], check=False)

    if result.returncode != 0:
        print_warning("Failed to start Docker daemon")
        return

    # Wait for Docker to be ready (docker0 interface to appear)
    # This typically takes 1-3 seconds
    for _i in range(10):
        result = run_cmd(["ip", "addr", "show", "docker0"], check=False)
        if result.returncode == 0:
            print_success("Docker daemon started")
            return
        time.sleep(1)

    print_warning("Docker started but docker0 interface not found")


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
    else:
        print_warning(f"{name} installation failed")
        if result.stderr:
            for line in result.stderr.strip().split("\n")[-5:]:
                print_detail(line)


# =============================================================================
# Node.js Global Packages
# =============================================================================


def install_node_global_packages() -> None:
    """Install global npm packages needed for various apps.

    pnpm is a fast, disk space efficient package manager that is required
    by some apps (Etherpad, HedgeDoc, etc.) that use pnpm workspaces.
    """
    # Check if npm is available
    if not cmd_exists("npm"):
        print_warning("npm not found, skipping global npm packages")
        return

    # Install pnpm if not already installed
    if cmd_exists("pnpm"):
        print_info("pnpm already installed")
    else:
        print_info("Installing pnpm...")
        with Spinner("Installing pnpm globally..."):
            result = run_cmd(["npm", "install", "-g", "pnpm"], check=False)
        if result.returncode == 0:
            print_success("pnpm installed")
        else:
            print_warning("pnpm installation failed")
            if result.stderr:
                print_detail(result.stderr.strip().split("\n")[-1])

    # nodeenv (for per-app [build].node-version pins) is installed separately:
    # it is a PyPI tool, not an npm package — see _install_nodeenv.
    _install_nodeenv()


# nodeenv lives in its own venv, symlinked onto the build PATH (mirrors Rust).
# /opt is root-owned and exists before the hop3 user/venv are created (this runs
# at step 1, the venv at step 3).
_NODEENV_VENV = Path("/opt/hop3/nodeenv-venv")
_NODEENV_BIN = Path("/usr/local/bin/nodeenv")


def _install_nodeenv() -> None:
    """Install ekalinin's nodeenv (PyPI) so [build].node-version pins work.

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
        venv_res = run_cmd(["python3", "-m", "venv", str(_NODEENV_VENV)], check=False)
    if venv_res.returncode != 0:
        print_error("nodeenv installation failed: could not create its venv")
        if venv_res.stderr:
            print_detail(venv_res.stderr.strip().split("\n")[-1])
        return

    with Spinner("Installing nodeenv into venv..."):
        pip_res = run_cmd(
            [str(_NODEENV_VENV / "bin" / "pip"), "install", "--upgrade", "nodeenv"],
            check=False,
        )
    if pip_res.returncode != 0:
        print_error("nodeenv installation failed: pip could not install it")
        if pip_res.stderr:
            print_detail(pip_res.stderr.strip().split("\n")[-1])
        return

    if create_symlink(_NODEENV_VENV / "bin" / "nodeenv", _NODEENV_BIN):
        print_success(f"nodeenv installed: {_NODEENV_BIN}")
    else:
        print_error(
            f"Installed nodeenv but could not symlink it to {_NODEENV_BIN} "
            "(it won't be on the build PATH)"
        )


# =============================================================================
# Rust Toolchain
# =============================================================================


def _fail_rust_install(
    msg: str,
    result: subprocess.CompletedProcess | None,
    *,
    required: bool,
) -> None:
    """Report a Rust install failure; raise if it was required."""
    (print_error if required else print_warning)(msg)
    if result is not None and result.stderr:
        print_detail(result.stderr[:400])
    if required:
        returncode = result.returncode if result is not None else 1
        stdout = result.stdout or "" if result is not None else ""
        stderr = result.stderr or msg if result is not None else msg
        raise CommandError(
            cmd=["rust-install"],
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )


def _verify_or_repair_cargo(
    cargo_path: Path, rustup_path: Path
) -> subprocess.CompletedProcess:
    """Return `cargo --version`; on failure, force-reinstall stable once first.

    A flaky component download (or a stale ~/.rustup) can leave the cargo PROXY
    present while the stable toolchain has no cargo ("cargo ... is not applicable
    to the 'stable-...' toolchain"). One forced toolchain reinstall self-heals
    that; the caller still fails loud when the returned result is non-zero.
    """
    verify = run_as_hop3(f"{cargo_path} --version")
    if verify.returncode == 0:
        return verify
    print_detail("cargo not usable; reinstalling the stable toolchain...")
    with Spinner("Repairing the Rust stable toolchain..."):
        run_as_hop3(
            f"{rustup_path} toolchain install stable --profile minimal --force",
            timeout=600,
        )
    return run_as_hop3(f"{cargo_path} --version")


def install_catalogue_baseline(os_family: str) -> None:
    """Install the catalogue-derived package baseline.

    Reads the list from `baselines.py` (generated from
    apps/*/hop3.toml via `python -m ...baseline`), translates to the
    local OS family, and apt/dnf-installs. Idempotent: reruns on an
    already-baselined host are cheap.

    Runs AFTER the static base packages in deps_{debian,fedora}.py —
    those provide the common stack (python, node, ruby, php, libssl-dev,
    ...); this step adds whatever else the catalogue declares on top.
    Skipped with a warning when the OS family is unsupported.
    """
    from .baselines import BASELINE_PACKAGES  # noqa: PLC0415

    packages = BASELINE_PACKAGES.get(os_family)
    if not packages:
        print_warning(
            f"No catalogue baseline available for OS family '{os_family}'; "
            "skipping. Native-profile apps may fail to build."
        )
        return

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
    install_cmd = [pkg_manager, "install", "-y", *lock_flags, *packages]
    with Spinner(f"Installing catalogue baseline ({len(packages)} package(s))..."):
        result = run_cmd(install_cmd, env=apt_env, check=False)

    if result.returncode == 0:
        print_success(f"Catalogue baseline installed ({len(packages)} packages)")
        return

    # Never swallow this: a failed baseline leaves native-profile apps unable to
    # build, and a warning here is how a real conflict (e.g. NodeSource vs the
    # distro nodejs) stayed hidden while every Node app failed downstream. Abort
    # loudly so the operator fixes provisioning instead of chasing per-app errors.
    tail = "\n".join((result.stderr or "").strip().split("\n")[-5:])
    print_error("Catalogue baseline install failed")
    raise CommandError(
        cmd=install_cmd,
        returncode=result.returncode,
        stderr=tail,
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
    """Install Rust toolchain via rustup.

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
        result = run_as_hop3(f"{cargo_path} --version")
        if result.returncode == 0:
            print_info(f"Rust toolchain already installed: {result.stdout.strip()}")
            _create_rust_symlinks(cargo_path, rustc_path, rustup_path)
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
        result = run_as_hop3(
            'curl --proto "=https" --tlsv1.2 -sSf https://sh.rustup.rs '
            "| sh -s -- -y --default-toolchain stable --profile minimal",
            timeout=600,
        )

    if result.returncode != 0:
        _fail_rust_install(
            "Rust installation via rustup failed", result, required=required
        )
        return

    if not cargo_path.exists():
        _fail_rust_install(
            "Rust installation reported success but cargo binary not found",
            None,
            required=required,
        )
        return

    # Verify cargo runs (path-exists alone was insufficient on at least
    # one host where rustup dropped a stub that couldn't exec).
    verify = _verify_or_repair_cargo(cargo_path, rustup_path)
    if verify.returncode != 0:
        _fail_rust_install(
            "Rust installed but `cargo --version` exits non-zero",
            verify,
            required=required,
        )
        return

    print_success("Rust toolchain installed")
    print_detail(f"Version: {verify.stdout.strip()}")
    _create_rust_symlinks(cargo_path, rustc_path, rustup_path)


def _create_rust_symlinks(
    cargo_path: Path, rustc_path: Path, rustup_path: Path
) -> None:
    """Create symlinks in /usr/local/bin for Rust tools.

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
            print_warning(f"Could not create symlink {target}")


# =============================================================================
# Clojure/Leiningen
# =============================================================================


def install_leiningen() -> None:
    """Install Leiningen (Clojure build tool).

    Leiningen is installed system-wide in /usr/local/bin.
    The actual JAR is downloaded on first run by the hop3 user.
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
        print_warning("Failed to download Leiningen")
        return

    # Make executable
    lein_path.chmod(0o755)

    # Run lein once as hop3 user to download the JAR
    # This sets up ~/.lein for the hop3 user
    with Spinner("Initializing Leiningen (downloading JAR)..."):
        result = run_as_hop3("lein version")

    if result.returncode == 0:
        print_success(f"Leiningen installed: {result.stdout.strip()}")
    else:
        print_warning("Leiningen script installed but initialization failed")
        if result.stderr:
            print_detail(result.stderr[:200])


# =============================================================================
# Elixir
# =============================================================================

# Pinned, recent Elixir. Phoenix's `phx_new` requires ~> 1.15; Debian/Ubuntu's
# apt `elixir` is 1.14, so we install a precompiled release instead. v1.17.x
# ships builds for OTP 25/26/27 (the OTP versions on current distros).
ELIXIR_VERSION = "1.17.3"
_ELIXIR_DIR = Path("/opt/elixir")
_ELIXIR_BINS = ("elixir", "elixirc", "mix", "iex")


def install_elixir() -> None:
    """Install a modern Elixir (>= 1.15) for Phoenix and other Elixir apps.

    Debian/Ubuntu ship Elixir 1.14, which recent Phoenix rejects. We keep the
    distro's Erlang/OTP (new enough on current releases) and drop in a
    precompiled Elixir matching the installed OTP major version, symlinked into
    /usr/local/bin so it takes precedence over any apt `elixir`.

    Non-fatal but loud: a failure leaves Elixir apps unbuildable, which the
    deploy then reports clearly, rather than silently shipping 1.14.
    """
    if _elixir_is_recent_enough():
        print_info("Elixir >= 1.15 already installed")
        return

    if not cmd_exists("erl"):
        print_info("Installing Erlang/OTP (for Elixir)...")
        with Spinner("Installing erlang-nox..."):
            result = run_cmd(
                ["apt-get", "install", "-y", *APT_LOCK_FLAGS, "erlang-nox"],
                env=APT_NONINTERACTIVE_ENV,
                check=False,
            )
        if result.returncode != 0 or not cmd_exists("erl"):
            print_error("Elixir install failed: could not install Erlang/OTP")
            if result.stderr:
                print_detail(result.stderr.strip().split("\n")[-1])
            return

    otp_major = _detect_otp_major()
    if not otp_major:
        print_error("Elixir install failed: could not detect the Erlang/OTP version")
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
        print_error(
            f"Elixir install failed: download error. No prebuilt Elixir "
            f"{ELIXIR_VERSION} for OTP {otp_major}? ({url})"
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
        print_error("Elixir install failed: could not extract the release archive")
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
        print_error(
            "Elixir install failed: `elixir --version` did not run after install"
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
    """Detect Debian/Ubuntu version for Microsoft repo URL.

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


def install_dotnet_sdk_debian() -> None:
    """Install .NET SDK on Debian/Ubuntu from Microsoft repository."""
    if cmd_exists("dotnet"):
        print_info(".NET SDK already installed")
        return

    # Detect the actual OS version
    distro, version = _detect_debian_version()
    print_detail(f"Detected {distro} {version}")

    # Microsoft provides packages for specific distro/version combinations
    # See: https://learn.microsoft.com/en-us/dotnet/core/install/linux
    repo_url = (
        f"https://packages.microsoft.com/config/{distro}/{version}/"
        "packages-microsoft-prod.deb"
    )

    # Add Microsoft package repository for Debian/Ubuntu
    with Spinner("Adding Microsoft package repository..."):
        # Download and install the Microsoft package signing key
        result = run_cmd(
            ["wget", "-q", repo_url, "-O", "/tmp/packages-microsoft-prod.deb"],
            check=False,
        )
        if result.returncode != 0:
            print_warning(
                f"Failed to download Microsoft repo package for {distro} {version}"
            )
            print_detail("Trying Ubuntu 24.04 as fallback...")
            result = run_cmd(
                [
                    "wget",
                    "-q",
                    "https://packages.microsoft.com/config/ubuntu/24.04/packages-microsoft-prod.deb",
                    "-O",
                    "/tmp/packages-microsoft-prod.deb",
                ],
                check=False,
            )
            if result.returncode != 0:
                print_warning("Failed to download Microsoft repository package")
                return

        result = run_cmd(
            ["dpkg", "-i", "/tmp/packages-microsoft-prod.deb"],
            check=False,
        )
        run_cmd(["rm", "-f", "/tmp/packages-microsoft-prod.deb"], check=False)

        if result.returncode != 0:
            print_warning("Failed to add Microsoft repository")
            return

    # Update package lists
    with Spinner("Updating package lists..."):
        run_cmd(["apt-get", "update", "-q", *APT_LOCK_FLAGS], check=False)

    # Install .NET SDKs
    with Spinner("Installing .NET SDK 8 (LTS)..."):
        result = run_cmd(
            ["apt-get", "install", "-y", *APT_LOCK_FLAGS, "dotnet-sdk-8.0"],
            env=APT_NONINTERACTIVE_ENV,
            check=False,
        )
        if result.returncode == 0:
            print_success(".NET SDK 8 installed")
        else:
            print_warning(".NET SDK 8 installation failed")

    with Spinner("Installing .NET SDK 9..."):
        result = run_cmd(
            ["apt-get", "install", "-y", *APT_LOCK_FLAGS, "dotnet-sdk-9.0"],
            env=APT_NONINTERACTIVE_ENV,
            check=False,
        )
        if result.returncode == 0:
            print_success(".NET SDK 9 installed")
        else:
            print_warning(".NET SDK 9 installation failed")


def install_dotnet_sdk_fedora() -> None:
    """Install .NET SDK on Fedora from repos."""
    if cmd_exists("dotnet"):
        print_info(".NET SDK already installed")
        return

    # Fedora has .NET in its repos
    with Spinner("Installing .NET SDK..."):
        result = run_cmd(
            ["dnf", "install", "-y", "dotnet-sdk-8.0", "dotnet-sdk-9.0"],
            check=False,
        )
        if result.returncode == 0:
            print_success(".NET SDK installed")
        else:
            print_warning(".NET SDK installation failed")
