# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""
Debian/Ubuntu dependency installation.

Handles version-specific package differences:
- Debian 12 (bookworm): Uses backports for newer Go (1.23)
- Debian 13 (trixie): Uses native packages
- Ubuntu 24.04+: Uses native packages
- Older versions: May need PPAs or backports
"""

from __future__ import annotations

from pathlib import Path

from hop3_installer.common import (
    CommandError,
    DistroInfo,
    Spinner,
    detect_distro_info,
    print_detail,
    print_info,
    print_success,
    run_cmd,
)

from .config import ServerInstallerConfig
from .deps_common import (
    APT_LOCK_FLAGS,
    APT_NONINTERACTIVE_ENV,
    PackageSpec,
    install_base_packages,
    install_dotnet_sdk_debian,
    install_node_global_packages,
    install_optional_packages,
)
from .redis import configure_redis

# =============================================================================
# Debian/Ubuntu Package Specification (Declarative)
# =============================================================================

# Base packages common to all Debian/Ubuntu versions
# Note: libpcre3-dev vs libpcre2-dev handled in _create_debian_package_spec
DEBIAN_BASE_PACKAGES = [
    # Core utilities
    "bc",
    "git",
    "sudo",
    "cron",
    "build-essential",
    # libpcre handled separately - Debian 13+ uses libpcre2-dev
    "zlib1g-dev",
    # Web server and database
    "nginx",
    "postgresql",
    "postgresql-contrib",
    # Python toolchain
    "python3-dev",
    "python3-pip",
    "python3-venv",
    "python3-setuptools",
    # Node.js: installed from NodeSource (Node 22 LTS) in
    # _install_node_toolchain(), NOT from apt here -- Debian/Ubuntu ship
    # Node 18 (EOL), which modern JS frameworks reject. NodeSource's
    # `nodejs` package bundles npm, so npm is not installed separately.
    # Ruby toolchain
    "ruby",
    "ruby-dev",
    "ruby-bundler",
    "libyaml-dev",
    "libgmp-dev",
    # Go toolchain - installed separately for backports handling
    # "golang-go" removed from here, handled in _install_go_toolchain()
    # Elixir toolchain
    "elixir",
    "erlang",
    # PHP toolchain (using php-fpm for Nginx, not mod_php for Apache)
    "php",
    "php-fpm",
    "php-cli",
    "php-mbstring",
    "php-xml",
    "php-curl",
    "php-zip",
    "php-pgsql",
    "php-mysql",
    "php-sqlite3",  # SQLite-backed PHP apps (e.g. paheko)
    "php-intl",
    "php-gd",
    "php-ldap",
    "php-bcmath",
    "php-gmp",
    "php-redis",
    "composer",
    # Java toolchain
    "default-jdk",
    "maven",
    # Firewall. rootd opens an app's fixed [[ports]] through the `inet hop3`
    # nftables table, so `nft` is a hard requirement of the platform, not an
    # optional extra. It was in no package list: the installer warned "nft not
    # found on PATH; skipping inet hop3 table creation" and carried on, and
    # every app declaring [[ports]] then died at deploy time with
    # "Deployer can't open the firewall for the app's fixed [[ports]]"
    # — owncast and matrix-synapse, two hours and one install later.
    "nftables",
    # Common utilities
    "curl",
    "wget",
    "rsync",
    "socat",
    "unzip",
    # SSL/TLS certificates
    "certbot",
    # Development libraries
    "libjpeg-dev",
    "libpng-dev",
    "libwebp-dev",
    "libpq-dev",
    "libffi-dev",
    "libssl-dev",
    # pkg-config is how -sys crates locate the libs above (libssl-dev
    # etc.). Without it, `cargo build` fails in the openssl-sys build
    # script even when libssl-dev is installed.
    "pkg-config",
    # libsqlite3-dev: needed by libsqlite3-sys for any Rust app that
    # bundles sqlite (vaultwarden with --features sqlite, etc.).
    # libmariadb-dev: equivalent for mysqlclient-sys.
    "libsqlite3-dev",
    "libmariadb-dev",
]


def _get_debian_docker_packages(distro_info: DistroInfo) -> list[str]:
    """
    Get Docker packages appropriate for the distro version.

    Package availability varies significantly across distributions:

    - Debian 12 (bookworm): docker.io includes everything
    - Debian 13 (trixie)+: docker.io (daemon only), docker-cli, docker-compose, docker-buildx
    - Ubuntu 24.04 (noble)+: docker.io, docker-compose-v2, docker-buildx
    - Ubuntu <24.04: docker.io, docker-compose (v1) only

    Args:
        distro_info: Detected distribution information.

    Returns:
        List of Docker package names for this distro.
    """
    # Base package - always available
    packages = ["docker.io"]

    if distro_info.is_ubuntu:
        if distro_info.version_major >= 24:
            # Ubuntu 24.04+ has docker-compose-v2 and docker-buildx
            packages.extend(["docker-compose-v2", "docker-buildx"])
        else:
            # Older Ubuntu only has docker-compose v1
            packages.append("docker-compose")

    elif distro_info.is_debian:
        # Debian 13+ (trixie): docker.io is daemon only, docker-cli is separate
        is_debian_13_plus = (
            distro_info.codename in {"trixie", "forky", "sid"}
            or distro_info.version_major >= 13
        )
        if is_debian_13_plus:
            packages.extend(["docker-cli", "docker-compose", "docker-buildx"])
        else:
            # Debian 12 (bookworm): docker.io includes CLI, docker-compose v1 only
            # Note: docker-buildx not available in bookworm repos
            packages.append("docker-compose")

    else:
        # Other Debian-based distros (Mint, Pop!_OS, etc.) - use safe defaults
        packages.append("docker-compose")

    return packages


def _create_debian_package_spec(distro_info: DistroInfo) -> PackageSpec:
    """
    Create a PackageSpec appropriate for the detected distro version.

    Args:
        distro_info: Detected distribution information.

    Returns:
        PackageSpec configured for the specific distro/version.
    """
    packages = list(DEBIAN_BASE_PACKAGES)

    # Handle PCRE library transition
    # Debian 13 (trixie)+ moved to PCRE2, older versions use PCRE3
    is_debian_13_plus = distro_info.is_debian and (
        distro_info.codename in {"trixie", "forky", "sid"}
        or distro_info.version_major >= 13
    )
    if is_debian_13_plus:
        packages.append("libpcre2-dev")
    else:
        # Ubuntu and older Debian use libpcre3-dev
        packages.append("libpcre3-dev")

    # Get version-appropriate Docker packages
    docker_packages = _get_debian_docker_packages(distro_info)

    return PackageSpec(
        pkg_manager="apt-get",
        update_cmd=["apt-get", "update", "-q", *APT_LOCK_FLAGS],
        env_vars=dict(APT_NONINTERACTIVE_ENV),
        install_flags=["--no-install-recommends", *APT_LOCK_FLAGS],
        base_packages=packages,
        docker_packages=docker_packages,
        mysql_packages=["mysql-server", "mysql-client", "libmysqlclient-dev"],
        redis_packages=["redis-server"],
        nix_packages=["xz-utils"],
        # npm is not a conditional package: the distro `npm` would drag in
        # the distro's Node 18 as a dependency. NodeSource's `nodejs`
        # (installed in _install_node_toolchain) provides npm.
        conditional_packages={},
    )


def _setup_package_sources(distro_info: DistroInfo) -> None:
    """
    Configure additional package sources based on distro version.

    For older distributions that lack recent package versions, this adds
    appropriate additional repositories (backports, not mixing releases).

    Args:
        distro_info: Detected distribution information.
    """
    # Debian 12 (bookworm): Add backports for newer Go (1.23)
    if distro_info.is_debian and distro_info.codename == "bookworm":
        print_info("Debian 12 detected: adding bookworm-backports for newer Go")
        backports_list = Path("/etc/apt/sources.list.d/bookworm-backports.list")
        backports_content = "deb http://deb.debian.org/debian bookworm-backports main\n"

        if not backports_list.exists():
            backports_list.write_text(backports_content)
            print_detail(f"Created {backports_list}")

    # Ubuntu versions before 24.04 might need PPAs for newer Go
    # (Currently Ubuntu 24.04+ has Go 1.22+ which is sufficient)
    elif distro_info.is_ubuntu and distro_info.version_major < 24:
        print_info(
            f"Ubuntu {distro_info.version} detected: older Go version may be used"
        )
        print_detail("Consider upgrading to Ubuntu 24.04+ for best compatibility")

    # Debian 11 (bullseye): Add backports for newer packages
    elif distro_info.is_debian and distro_info.codename == "bullseye":
        print_info("Debian 11 detected: adding bullseye-backports for newer packages")
        backports_list = Path("/etc/apt/sources.list.d/bullseye-backports.list")
        backports_content = "deb http://deb.debian.org/debian bullseye-backports main\n"

        if not backports_list.exists():
            backports_list.write_text(backports_content)
            print_detail(f"Created {backports_list}")


def _install_go_toolchain(distro_info: DistroInfo) -> None:
    """
    Install Go toolchain from appropriate source.

    On Debian 12 (bookworm), installs from backports to get Go 1.23.
    On other distros, installs from main repos.

    Args:
        distro_info: Detected distribution information.
    """
    # Determine if we need backports
    use_backports = distro_info.is_debian and distro_info.codename in {
        "bookworm",
        "bullseye",
    }

    if use_backports:
        target = f"{distro_info.codename}-backports"
        print_info(f"Installing Go from {target}")
        cmd = ["apt-get", "install", "-y", *APT_LOCK_FLAGS, "-t", target, "golang-go"]
    else:
        print_info("Installing Go from main repository")
        cmd = ["apt-get", "install", "-y", *APT_LOCK_FLAGS, "golang-go"]

    # Installed on every server, like Node: Go apps fail to build without it.
    with Spinner("Installing Go toolchain..."):
        run_cmd(cmd, env=APT_NONINTERACTIVE_ENV)
    print_success("Go toolchain installed")


#: NodeSource's setup script for the Node release the catalogue builds with.
NODESOURCE_SETUP_URL = "https://deb.nodesource.com/setup_22.x"
#: Astro needs >=22.12, Etherpad and pnpm >=22.13.
REQUIRED_NODE_MAJOR = 22


def _install_node_toolchain() -> None:
    """
    Install Node.js 22 LTS from the NodeSource apt repository, or fail.

    Debian/Ubuntu ship Node 18, which is EOL and rejected by modern JS
    frameworks (Astro needs >=22.12, Etherpad/pnpm >=22.13). Installing a
    modern Node system-wide means *every* build step gets a supported
    runtime -- the prebuild hooks (which run before the Node toolchain's
    per-app nodeenv step), the toolchain build, and unpinned apps alike --
    instead of relying on per-app `node-version` pins that only cover the
    toolchain phase.

    There is no fallback to the distribution's Node: a server with Node 18
    looks installed and cannot build the catalogue's Node apps, which fail
    later and elsewhere (blocker #32). An unreachable NodeSource, a failed
    install, or an older Node still first on PATH stops the install here.

    Raises:
        CommandError: Node 22 could not be installed.
    """
    setup_script = Path("/tmp/nodesource_setup.sh")
    apt_env = APT_NONINTERACTIVE_ENV
    with Spinner("Installing Node.js 22 LTS (NodeSource)..."):
        fetched = run_cmd(
            ["curl", "-fsSL", NODESOURCE_SETUP_URL, "-o", str(setup_script)],
            check=False,
        )
        if fetched.returncode != 0:
            raise CommandError(
                ["curl", NODESOURCE_SETUP_URL],
                fetched.returncode,
                f"Can't reach NodeSource ({fetched.stderr.strip()}). The distro's "
                f"Node 18 is EOL and too old for Node apps, so the install stops. "
                f"Make deb.nodesource.com reachable and re-run.",
            )
        run_cmd(["bash", str(setup_script)], env=apt_env)
        run_cmd(["apt-get", "install", "-y", *APT_LOCK_FLAGS, "nodejs"], env=apt_env)

    version = run_cmd(["node", "--version"]).stdout.strip()
    if int(version.lstrip("v").split(".")[0]) < REQUIRED_NODE_MAJOR:
        raise CommandError(
            ["node", "--version"],
            0,
            f"Node {version} is first on PATH after installing Node "
            f"{REQUIRED_NODE_MAJOR} from NodeSource; remove the older Node.",
        )
    print_success(f"Node.js installed: {version}")


# =============================================================================
# Installation Functions
# =============================================================================


def install_debian_deps(config: ServerInstallerConfig) -> None:
    """
    Install all Debian/Ubuntu dependencies.

    Detects the specific distro version and configures package sources
    accordingly before installing packages.

    Args:
        config: Server installer configuration.
    """
    # Detect distro version
    distro_info = detect_distro_info()
    print_info(f"Detected distribution: {distro_info}")

    # Setup additional package sources if needed (e.g., backports for Debian 12)
    _setup_package_sources(distro_info)

    # Create version-appropriate package spec
    spec = _create_debian_package_spec(distro_info)

    # Log Docker packages being installed
    print_detail(f"Docker packages: {', '.join(spec.docker_packages)}")

    # Install packages
    install_base_packages(spec)

    # Install Node separately from NodeSource (distro Node 18 is too old)
    _install_node_toolchain()

    # Install Go separately (may need backports on older Debian)
    _install_go_toolchain(distro_info)

    install_optional_packages(config, spec, configure_redis)
    install_dotnet_sdk_debian()
    install_node_global_packages()
