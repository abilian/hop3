# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
The ADR 035 runtime contract, exercised end to end for a Nix artifact.

This is the M2.2 (Nix runtime beta) gate at the unit level: a nix build writes a
`runtime.json` (a `RuntimeConfig`), the deployer persists it as `BUILD_ARTIFACT.json`,
and the run phase must load it and drive the process *without re-detecting anything*.
Existing spawn tests cover env precedence and the worker filter in isolation; this
one covers the whole chain — JSON round-trip → `AppLauncher._load_artifact` →
`make_env` (env vars + PATH prepend) + `workers` — as one flow, with store paths.
"""

from __future__ import annotations

from types import SimpleNamespace

from hop3.core.artifacts import BuildArtifact, RuntimeConfig
from hop3.core.env import Env
from hop3.run.spawn import AppLauncher

_STORE = "/nix/store/abc123def456-forgejo-11.0.1"


def _nix_runtime() -> RuntimeConfig:
    """A nix app's runtime as the builder computes it — absolute store paths."""
    return RuntimeConfig(
        env_vars={
            "GITEA_WORK_DIR": "/home/hop3/apps/forge/data",
            "SSL_CERT_FILE": f"{_STORE}/etc/ssl/certs/ca-bundle.crt",
        },
        path_prepend=[f"{_STORE}/bin"],
        working_dir=_STORE,
        workers={"web": f"{_STORE}/bin/forgejo web", "prebuild": "echo build-step"},
    )


def test_nix_runtime_contract_applied_end_to_end(tmp_path) -> None:
    # Persist as the deployer does, then load as the run phase does.
    artifact = BuildArtifact(
        kind="nix",
        builder="nix",
        app_name="forge",
        location=_STORE,
        runtime=_nix_runtime(),
    )
    artifact.save(tmp_path / "BUILD_ARTIFACT.json")

    launcher = AppLauncher.__new__(AppLauncher)
    launcher.app_name = "forge"
    launcher.app_path = tmp_path
    launcher.virtualenv_path = tmp_path / "venv"
    launcher.artifact = launcher._load_artifact()  # from disk — the load path
    launcher.app = SimpleNamespace(
        name="forge",
        port=12345,  # set so make_env doesn't reach for a free port
        get_runtime_env=lambda: Env({"DATABASE_URL": "postgres://localhost/forge"}),
    )

    # The contract survived the JSON round-trip.
    assert launcher.artifact is not None
    assert launcher.artifact.kind == "nix"
    assert launcher.artifact.runtime.working_dir == _STORE

    env = launcher.make_env()

    # Artifact env_vars applied; the store bin is prepended to PATH.
    assert env["GITEA_WORK_DIR"] == "/home/hop3/apps/forge/data"
    assert env["SSL_CERT_FILE"] == f"{_STORE}/etc/ssl/certs/ca-bundle.crt"
    assert env["PATH"].startswith(f"{_STORE}/bin:")
    # A non-toolchain [env] key still applies.
    assert env["DATABASE_URL"] == "postgres://localhost/forge"

    # Workers come from the artifact; the build-step hook is NOT handed to uWSGI.
    assert launcher.workers == {"web": f"{_STORE}/bin/forgejo web"}
    assert "prebuild" not in launcher.workers


def test_runtime_json_roundtrip_preserves_all_fields(tmp_path) -> None:
    # Full RuntimeConfig (incl. before_run / static / healthcheck) must survive
    # save → load byte-for-value; the run phase relies on every field.
    runtime = RuntimeConfig(
        env_vars={"K": "v"},
        path_prepend=[f"{_STORE}/bin"],
        working_dir=_STORE,
        workers={"web": f"{_STORE}/bin/app"},
        before_run=["mkdir -p var"],
        static_paths={"/static": "static"},
        healthcheck_path="/health",
        healthcheck_timeout=45,
    )
    src = BuildArtifact(kind="nix", app_name="a", location=_STORE, runtime=runtime)
    src.save(tmp_path / "BUILD_ARTIFACT.json")

    loaded = BuildArtifact.load(tmp_path / "BUILD_ARTIFACT.json")

    assert loaded is not None
    assert loaded.kind == "nix"
    assert loaded.runtime == runtime  # dataclass equality over every field


def test_missing_artifact_falls_back_to_legacy_detection(tmp_path) -> None:
    # No BUILD_ARTIFACT.json → load returns None → run phase uses legacy detection
    # (asserted here as: no artifact, so no runtime contract to apply).
    launcher = AppLauncher.__new__(AppLauncher)
    launcher.app_name = "forge"
    launcher.app_path = tmp_path  # empty dir, no BUILD_ARTIFACT.json
    launcher.artifact = launcher._load_artifact()

    assert launcher.artifact is None
    assert launcher._apply_artifact_runtime(Env({})) is False
