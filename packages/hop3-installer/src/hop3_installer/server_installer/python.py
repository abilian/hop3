# Copyright (c) 2025-2026, Abilian SAS
# SPDX-License-Identifier: Apache-2.0
"""Python virtual environment and package installation."""

from __future__ import annotations

import grp
import json
import os
import pwd
import shutil
import sys
import tempfile
from pathlib import Path

from hop3_installer.common import (
    CommandError,
    Spinner,
    create_symlink,
    make_build_info,
    print_info,
    print_success,
    print_warning,
)
from hop3_installer.constants import (
    BUILD_INFO_PATH,
    CLI_PACKAGE_NAME,
    CLI_PACKAGE_SUBDIR,
    GIT_REPO,
    HOP3_GROUP,
    HOP3_USER,
    ROOTD_PACKAGE_NAME,
    ROOTD_PACKAGE_SUBDIR,
    SERVER_PACKAGE_NAME,
    SERVER_PACKAGE_SUBDIR,
    VENV_DIR,
)

from .config import ServerInstallerConfig
from .user import run_as_hop3

#: Where app build hooks find the download helper (see publish_fetch_helper).
FETCH_HELPER_LINK = Path("/usr/local/bin/hop3-fetch")


def _get_python_executable() -> str:
    """
    Get the Python executable to use for creating the venv.

    Uses the same Python that's running this installer, which ensures
    we use Python 3.10+ even on systems where `python3` is older.
    """
    return sys.executable


def create_virtual_environment(*, force: bool = False) -> None:
    """
    Create Python virtual environment.

    Idempotent by default: if a working venv already exists at VENV_DIR
    (i.e. has a usable ``bin/python``), this is a no-op. Pass ``force=True``
    to wipe and recreate.

    This used to unconditionally rmtree+recreate, which silently destroyed
    any prior install — including the one ``hop3-deploy --local`` had just
    placed there via ``pip install`` in a separate step.
    """
    python_in_venv = VENV_DIR / "bin" / "python"
    if VENV_DIR.exists():
        if not force and python_in_venv.exists():
            print_info(f"Virtual environment already exists at {VENV_DIR}")
            return
        shutil.rmtree(VENV_DIR)

    python_exe = _get_python_executable()
    with Spinner(f"Creating virtual environment (using {python_exe})..."):
        run_as_hop3([python_exe, "-m", "venv", str(VENV_DIR)])

    print_success(f"Virtual environment created at {VENV_DIR}")


def install_package(config: ServerInstallerConfig) -> None:
    """Install the hop3-server package."""
    pip = f"{VENV_DIR}/bin/pip"

    # Upgrade pip
    with Spinner("Upgrading pip..."):
        run_as_hop3([pip, "install", "--upgrade", "pip"])

    # Determine what to install. Values interpolated into package_spec are
    # user-controlled; run_as_hop3 quotes every argv element at the seam.
    pre_flag: list[str] = []
    # Install the WAF engine by default via the hop3-server[waf] extra (ADR 050):
    # LeWAF + uvicorn, marker-gated to py3.12+. Without it, deploying a WAF-enabled
    # app aborts loudly ("'waf' extra not installed"), so WAF must ship out of the box.
    if config.local_path:
        package_spec = f"{config.local_path}[waf]"
        source_desc = f"local path ({config.local_path})"
    elif config.use_git:
        with Spinner("Installing build tools..."):
            run_as_hop3([pip, "install", "uv"])
        package_spec = (
            f"{SERVER_PACKAGE_NAME}[waf] @ "
            f"git+{GIT_REPO}@{config.branch}#subdirectory={SERVER_PACKAGE_SUBDIR}"
        )
        source_desc = f"git ({config.branch} branch)"
    elif config.version:
        package_spec = f"{SERVER_PACKAGE_NAME}[waf]=={config.version}"
        source_desc = f"PyPI (version {config.version})"
    else:
        package_spec = f"{SERVER_PACKAGE_NAME}[waf]"
        if config.pre_release:
            pre_flag = ["--pre"]
            source_desc = "PyPI (latest including pre-releases)"
        else:
            source_desc = "PyPI (latest stable)"

    with Spinner(f"Installing hop3-server from {source_desc}..."):
        run_as_hop3([pip, "install", *pre_flag, package_spec])

    print_success("hop3-server installed successfully")

    publish_fetch_helper()

    install_rootd_package(config)
    install_cli_package(config)

    write_build_info(config)


def publish_fetch_helper() -> None:
    """
    Put ``hop3-fetch`` on PATH for app build hooks.

    Recipes call it from ``[build].before-build`` to fetch their upstream
    source through Hop3's shared download cache. Build hooks run with the
    server process's PATH, which does not include the server venv — and it
    must not: prepending that venv would shadow ``python3`` inside every app
    build. So the helper is symlinked into /usr/local/bin, the same way the
    installer publishes cargo, elixir and hop3-rootd.

    A server that does not ship the helper is not an error: this installer
    installs whatever version it is asked for, and older ones predate it. A
    helper that is present but cannot be published *is* an error, because
    every recipe needing it would then fail with nothing pointing here.
    """
    source = VENV_DIR / "bin" / "hop3-fetch"

    if not source.exists():
        # Not a failure. The helper arrived with a particular hop3-server
        # version, and this installer is expected to install any version — from
        # git, from a --version pin, from PyPI. An older server legitimately has
        # no helper to publish, so aborting the install here would break
        # installing anything that predates it (it did: the from-git e2e test).
        #
        # The mismatch that actually matters is a *current catalog* against an
        # *older server*, and that surfaces at deploy time as "hop3-fetch:
        # command not found" from the recipe that needs it — the right place,
        # because only then is it known whether anything needs the helper.
        print_info(
            f"hop3-server in {VENV_DIR} ships no hop3-fetch; not publishing it. "
            "Catalog recipes that download their sources through it require a "
            "newer hop3-server."
        )
        return

    if not create_symlink(source, FETCH_HELPER_LINK):
        # Present but unlinkable — that IS a failure, and a silent one would
        # leave every such recipe failing later for no visible reason.
        msg = (
            f"hop3-fetch exists at {source} but could not be linked to "
            f"{FETCH_HELPER_LINK}. Catalog recipes call it to download their "
            "sources and would fail at deploy time with 'command not found'. "
            "Check that /usr/local/bin is writable."
        )
        raise OSError(msg)

    print_success(f"hop3-fetch published to {FETCH_HELPER_LINK}")


def write_build_info(config: ServerInstallerConfig) -> None:
    """
    Record deploy provenance to ``BUILD_INFO_PATH`` (read by `system info`).

    Best-effort: a failure here must never abort an otherwise-good install.
    For git installs the commit comes from pip's ``direct_url.json`` (PEP 610);
    local/PyPI installs record only the method and version (the developer-side
    ``hop3-deploy`` fills in the commit for ``--local`` deploys).
    """
    try:
        if config.local_path:
            method = "local"
        elif config.use_git:
            method = "git"
        elif config.version:
            method = "pypi"
        else:
            method = "pypi-latest"

        info = make_build_info(
            deploy_method=method,
            version=_installed_version(),
            deployed_by="hop3-install",
            git_commit=_git_commit_from_direct_url() if config.use_git else None,
            git_branch=config.branch if config.use_git else None,
        )
        BUILD_INFO_PATH.write_text(json.dumps(info, indent=2) + "\n")
        _chown_hop3(BUILD_INFO_PATH)
        print_info(f"Recorded build info to {BUILD_INFO_PATH}")
    except Exception as e:
        # Provenance is non-critical: never fail an otherwise-good install.
        print_warning(f"Could not write build info: {e}")


def _installed_version() -> str | None:
    """Return the hop3-server version as installed in the venv."""
    code = "import importlib.metadata as m; print(m.version('hop3_server'))"
    result = run_as_hop3([f"{VENV_DIR}/bin/python", "-c", code])
    version = (result.stdout or "").strip()
    return version or None


def _git_commit_from_direct_url() -> str | None:
    """Read the git commit pip recorded for a ``git+...`` install (PEP 610)."""
    for site in (VENV_DIR / "lib").glob("python*/site-packages"):
        for path in site.glob("hop3_server-*.dist-info/direct_url.json"):
            try:
                data = json.loads(path.read_text())
            except (OSError, ValueError):
                continue
            commit = data.get("vcs_info", {}).get("commit_id")
            if commit:
                return commit
    return None


def _chown_hop3(path: Path) -> None:
    """Give a file to the hop3 user/group so the server can read it."""
    uid = pwd.getpwnam(HOP3_USER).pw_uid
    gid = grp.getgrnam(HOP3_GROUP).gr_gid
    os.chown(path, uid, gid)


def install_rootd_package(config: ServerInstallerConfig) -> None:
    """
    Install the hop3-rootd daemon into the server venv.

    hop3-rootd (ADR 041) is a separate package the deploy path depends on for
    privileged operations (nginx reload). hop3-server does not declare it as a
    dependency, so we install it explicitly alongside, from the same source as
    the server: a sibling local dir, the git subdirectory, or PyPI.
    """
    pip = f"{VENV_DIR}/bin/pip"

    if config.local_path:
        # Sibling of the server source (the demo uploads /tmp/hop3-rootd
        # next to /tmp/hop3-server).
        rootd_path = Path(config.local_path).parent / "hop3-rootd"
        if not rootd_path.exists():
            # Don't soft-skip into a confusing later failure: setup_rootd
            # (step 9b) hard-aborts when the binary is absent. Say so plainly.
            print_warning(
                f"hop3-rootd source not found at {rootd_path}. The install will "
                "abort at the hop3-rootd step — the daemon is required for "
                "deploys (nginx reloads). Upload it next to the server source "
                "and re-run."
            )
            return
        package_spec = str(rootd_path)
        source_desc = f"local path ({rootd_path})"
    elif config.use_git:
        package_spec = (
            f"git+{GIT_REPO}@{config.branch}#subdirectory={ROOTD_PACKAGE_SUBDIR}"
        )
        source_desc = f"git ({config.branch} branch)"
    elif config.version:
        package_spec = f"{ROOTD_PACKAGE_NAME}=={config.version}"
        source_desc = f"PyPI (version {config.version})"
    else:
        package_spec = ROOTD_PACKAGE_NAME
        source_desc = "PyPI (latest stable)"

    with Spinner(f"Installing hop3-rootd from {source_desc}..."):
        run_as_hop3([pip, "install", package_spec])

    print_success("hop3-rootd installed successfully")


def install_cli_package(config: ServerInstallerConfig) -> None:
    """
    Install the hop3-cli (``hop3``) client into the server venv.

    The client isn't needed to *run* the server, but tutorial tests execute on
    the server and call ``hop3 deploy`` against localhost, so the ``hop3`` binary
    must be present. Installed from the same source as the server: a sibling
    local dir (``/tmp/hop3-cli`` next to ``/tmp/hop3-server``), the git
    subdirectory, or PyPI. A missing local source is non-fatal (the server still
    runs) but loud — on-server tutorials would have no client.
    """
    pip = f"{VENV_DIR}/bin/pip"

    if config.local_path:
        cli_path = Path(config.local_path).parent / "hop3-cli"
        if not cli_path.exists():
            print_warning(
                f"hop3-cli source not found at {cli_path}. The server won't have "
                "the `hop3` client; on-server tutorial tests can't deploy. Upload "
                "it next to the server source and re-run."
            )
            return
        package_spec = str(cli_path)
        source_desc = f"local path ({cli_path})"
    elif config.use_git:
        package_spec = (
            f"git+{GIT_REPO}@{config.branch}#subdirectory={CLI_PACKAGE_SUBDIR}"
        )
        source_desc = f"git ({config.branch} branch)"
    elif config.version:
        package_spec = f"{CLI_PACKAGE_NAME}=={config.version}"
        source_desc = f"PyPI (version {config.version})"
    else:
        package_spec = CLI_PACKAGE_NAME
        source_desc = "PyPI (latest stable)"

    with Spinner(f"Installing hop3-cli from {source_desc}..."):
        run_as_hop3([pip, "install", package_spec])

    print_success("hop3-cli installed successfully")


def run_hop3_setup() -> None:
    """Run hop3 setup command."""
    hop_server = f"{VENV_DIR}/bin/hop3-server"

    with Spinner("Running initial setup..."):
        run_as_hop3([hop_server, "setup"])

    print_success("Hop3 initial setup complete")


def setup_ssh_keys() -> None:
    """Copy root SSH keys to hop3 user if available."""
    root_keys = Path("/root/.ssh/authorized_keys")

    if not root_keys.exists():
        print_info("No root SSH keys found, skipping")
        return

    content = root_keys.read_text().strip()
    if not content:
        print_info("Root SSH keys file is empty, skipping")
        return

    hop_server = f"{VENV_DIR}/bin/hop3-server"

    # Use secure temp file instead of predictable path
    fd, temp_path = tempfile.mkstemp(prefix="hop3_ssh_keys_", suffix=".txt")
    temp_keys = Path(temp_path)

    try:
        # Write keys to secure temp file
        os.close(fd)  # Close the file descriptor, we'll write via shutil
        shutil.copy2(root_keys, temp_keys)

        # Set ownership so hop3 user can read it
        hop3_uid = pwd.getpwnam(HOP3_USER).pw_uid
        hop3_gid = grp.getgrnam(HOP3_GROUP).gr_gid
        os.chown(temp_keys, hop3_uid, hop3_gid)
        Path(temp_keys).chmod(0o600)  # Restrict permissions

        # Run setup:ssh - quote the path for safety
        run_as_hop3([hop_server, "setup:ssh", str(temp_keys)])
        print_success("SSH keys configured")
    except CommandError:
        print_warning("Could not configure SSH keys (invalid format?)")
    finally:
        if temp_keys.exists():
            temp_keys.unlink()
