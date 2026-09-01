# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The Docker image the pytest e2e layer runs against, and the gate that keeps it fresh.

Lives here rather than in one package's conftest because more than one package needs
a running server to test against: hop3-server's own e2e layer, and hop3-tui's, which
verifies that the argv its client builds is a command the server actually answers.
Copying the build would mean copying the staleness gate below, and a second copy is
exactly how a cached image starts silently testing code that no longer exists.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import docker
import docker.errors

if TYPE_CHECKING:
    from collections.abc import Iterable

#: Label carrying a content hash of everything the image bakes in. Reuse is gated on
#: it, so the cached image can never silently test stale code.
SRC_HASH_LABEL = "cloud.hop3.e2e-src-hash"

IMAGE_TAG = "hop3-e2e:test"

#: The repo root: .../packages/hop3-testing/src/hop3_testing/e2e_image.py
PROJECT_ROOT = Path(__file__).resolve().parents[4]

#: The Dockerfile bakes hop3-server, so it lives with hop3-server's e2e layer.
DOCKER_DIR = PROJECT_ROOT / "packages/hop3-server/tests/c_e2e/docker"

#: Packages whose full source the image installs with `pip install -e`.
BAKED_PACKAGES = ("hop3-server", "hop3-rootd")


def build_inputs() -> list[Path]:
    """
    Every file whose content the e2e image bakes in (COPY / ``pip install -e``).

    Covers the e2e Dockerfile + entrypoint and the ``pyproject.toml`` / ``README``
    / full ``src`` tree of hop3-server and hop3-rootd — including non-``.py`` data
    files (e.g. the WAF CRS rules the server loads at runtime). ``__pycache__`` is
    excluded (the Dockerfile strips it, and it isn't a build input).
    """
    inputs = [DOCKER_DIR / "Dockerfile", DOCKER_DIR / "entrypoint.sh"]
    for pkg in BAKED_PACKAGES:
        base = PROJECT_ROOT / "packages" / pkg
        inputs.append(base / "pyproject.toml")
        inputs.append(base / "README.md")
        inputs += [
            p
            for p in (base / "src").rglob("*")
            if p.is_file() and "__pycache__" not in p.parts
        ]
    return inputs


def source_hash() -> str:
    """SHA-256 over the build inputs (relative path + bytes), truncated."""
    digest = hashlib.sha256()
    for path in sorted(build_inputs()):
        digest.update(path.relative_to(PROJECT_ROOT).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:16]


def _print_build_log(entries: Iterable[Any]) -> None:
    """Echo the `stream` lines of a docker build log.

    docker-py yields arbitrary JSON here, not only dicts — `"stream" in entry`
    against a str would substring-match and against an int would raise, so the
    shape is checked rather than assumed.
    """
    for entry in entries:
        if isinstance(entry, dict) and "stream" in entry:
            print(str(entry["stream"]).strip())


def ensure_e2e_image(client: docker.DockerClient) -> str:
    """
    Build the hop3 E2E test image, reusing it only when it is up to date.

    The image bakes hop3-server + hop3-rootd source (and the e2e Dockerfile) at
    build time. We stamp the build with a content hash of those inputs
    (``SRC_HASH_LABEL``) and reuse the cached image only when the hash still
    matches — so a ``git pull`` or a source edit can never silently test stale
    code (the class of bug where a WAF deploy went "green" against a server with
    no WAF support). ``HOP3_E2E_FORCE_REBUILD=1`` forces a rebuild regardless.
    """
    src_hash = source_hash()

    if not os.environ.get("HOP3_E2E_FORCE_REBUILD"):
        try:
            existing = client.images.get(IMAGE_TAG)
        except docker.errors.ImageNotFound:
            existing = None
        if existing is not None:
            # docker-py's stubs type `images.get` as `Model`, which has no `labels`;
            # the runtime object is an `Image`, which does.
            labels = cast("dict[str, str]", getattr(existing, "labels", None) or {})
            baked = labels.get(SRC_HASH_LABEL)
            if baked == src_hash:
                print(f"Using existing Docker image: {IMAGE_TAG} (src {src_hash})")
                return IMAGE_TAG
            print(
                f"Rebuilding {IMAGE_TAG}: baked source {baked or '<none>'} != "
                f"current {src_hash} — server/rootd/Dockerfile changed since the "
                f"cached image was built."
            )

    # The Dockerfile copies source and installs with ``pip install -e``, so the
    # build always reflects the current tree.
    print(f"Building Docker image: {IMAGE_TAG} (src {src_hash})")
    print("This may take 5-10 minutes on first run...")

    try:
        # `images.build` returns `(image, log_stream)`; the stubs say `Model`.
        built = cast(
            "tuple[Any, Iterable[Any]]",
            client.images.build(
                path=str(PROJECT_ROOT),
                dockerfile=str(DOCKER_DIR / "Dockerfile"),
                tag=IMAGE_TAG,
                labels={SRC_HASH_LABEL: src_hash},
                rm=True,
                forcerm=True,
            ),
        )
        _print_build_log(built[1])
        print(f"Successfully built image: {IMAGE_TAG}")
        return IMAGE_TAG

    except docker.errors.BuildError as e:
        print(f"Build failed: {e}")
        _print_build_log(e.build_log)
        msg = f"Failed to build Docker image: {e}"
        raise AssertionError(msg) from e
