# Copyright (c) 2024-2025 Abilian SAS
# SPDX-License-Identifier: Apache-2.0

"""NixBuilder - Build applications using user-provided hop3.nix."""

from __future__ import annotations

import json
import os
import pwd
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from hop3.config import APP_ROOT
from hop3.core.protocols import BuildArtifact, BuildContext, RuntimeConfig
from hop3.lib import Abort, log

# See docker/builder.py for the rationale — single generous timeout + a
# silent-time watchdog, no per-app tier declarations.
NIX_BUILD_TIMEOUT_SECONDS = 30 * 60
NIX_BUILD_MAX_SILENT_SECONDS = 300

# Nix profile scripts to try (single-user and multi-user modes)
# Note: Single-user path is evaluated at runtime via _get_nix_profile_paths()
# to ensure we use the correct HOME for the current process
NIX_DAEMON_PROFILE = Path("/nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh")


class NixBuilder:
    """Build applications using Nix.

    Supports two modes:
    - **Explicit**: Application provides a hand-crafted ``hop3.nix`` file.
    - **Generated**: Application provides a ``[nix]`` section in ``hop3.toml``
      with a template name; the builder generates ``hop3.nix`` on the fly
      using the template-based generator (ADR 008).

    In both modes, the built package must contain ``$out/hop3/runtime.json``
    with resolved Nix store paths for workers, env vars, and PATH entries.
    """

    name: str = "nix"

    def __init__(self, context: BuildContext) -> None:
        """Initialize NixBuilder with build context.

        Args:
            context: Build context containing app info and source path.
        """
        self.context = context
        self.rejection_reason: str = ""
        self._mode: str = ""  # "explicit" or "generated"

    def _has_nix_template(self) -> bool:
        """Check if hop3.toml declares a [nix].template."""
        app_config = self.context.app_config or {}
        hop3_config = app_config.get("hop3_config", {})
        nix_section = hop3_config.get("nix", {})
        return bool(nix_section.get("template"))

    def _check_no_contradiction(self) -> None:
        """Refuse to build if both hop3.nix AND [nix].template are present.

        Silently picking one is dangerous: the user almost certainly
        intends one of them to take effect, and the other being ignored
        is a footgun. Force the user to delete one or eject deliberately.

        Raises:
            Abort: If both an explicit hop3.nix and a [nix].template
                section in hop3.toml are present.
        """
        source = self.context.source_path
        if (source / "hop3.nix").exists() and self._has_nix_template():
            msg = (
                f"Both hop3.nix and a [nix].template section in hop3.toml "
                f"are present in {source}. Pick one:\n"
                f"  - Delete hop3.nix to use the template, OR\n"
                f"  - Remove the [nix].template section to keep your "
                f"hand-crafted hop3.nix.\n"
                f"To convert a template to a hand-crafted file, "
                f"run: hop3 nix eject {self.context.app_name}"
            )
            raise Abort(msg)

    def accept(self) -> bool:
        """Check if this builder can handle the application.

        Returns True if either:
        - A hop3.nix file exists in the source directory (explicit mode), or
        - The hop3.toml has a [nix] section with a template name (generated mode)

        In both cases, the nix command must be available on the system.
        Raises Abort if both modes are configured simultaneously.

        Returns:
            True if builder can handle this application.
        """
        source = self.context.source_path

        # Refuse silently picking one if both are present.
        self._check_no_contradiction()

        # Mode 1: explicit hop3.nix file (mutually exclusive with
        # [nix].template, enforced above by _check_no_contradiction)
        if (source / "hop3.nix").exists():
            if not self._nix_available():
                self.rejection_reason = "nix command not found"
                return False
            self._mode = "explicit"
            return True

        # Mode 2: [nix].template section in hop3.toml
        if self._has_nix_template():
            if not self._nix_available():
                self.rejection_reason = "nix command not found"
                return False
            self._mode = "generated"
            return True

        self.rejection_reason = "no hop3.nix and no [nix].template in hop3.toml"
        return False

    def build(self) -> BuildArtifact:
        """Build the application with nix-build.

        In explicit mode, uses the existing hop3.nix file.
        In generated mode, generates hop3.nix from the [nix] template spec
        and writes it to a temporary file before building.

        Runs nix-build on the nix file, then reads the runtime configuration
        from $out/hop3/runtime.json in the built package.

        Returns:
            BuildArtifact containing build metadata and RuntimeConfig.

        Raises:
            RuntimeError: If nix-build fails or runtime.json is missing.
        """
        source = self.context.source_path

        # Defensive: refuse silently picking one if both are present.
        # accept() also checks this, but build() may be reached when
        # the builder is force-selected via [build].builder = "nix".
        self._check_no_contradiction()

        # 0. Resolve the nix file (explicit or generated).
        # Determine mode here (not only in accept()) because the builder
        # may be force-selected via [build].builder = "nix" without
        # accept() being called.
        nix_file = source / "hop3.nix"
        if nix_file.exists():
            self._mode = "explicit"
        else:
            # No hop3.nix — try to generate from [nix] template
            nix_file = self._generate_nix_file()

        # 1. Kill any stale nix-build for this app (e.g., from a previous killed deploy)
        self._kill_stale_nix_builds(nix_file)

        # 2. Build the package
        store_path = self._nix_build(nix_file)

        # 3. Read runtime config from built package
        runtime_json = Path(store_path) / "hop3" / "runtime.json"
        if not runtime_json.exists():
            msg = (
                f"hop3.nix must create $out/hop3/runtime.json, "
                f"but {runtime_json} not found"
            )
            raise RuntimeError(msg)

        runtime_data = json.loads(runtime_json.read_text())

        # 4. Build RuntimeConfig
        workers = runtime_data.get("workers", {})
        runtime = RuntimeConfig(
            env_vars=runtime_data.get("env", {}),
            path_prepend=runtime_data.get("path", []),
            working_dir=store_path,
            workers=workers,
        )

        # 4. Determine artifact kind based on workers
        # Static sites have only a "static" worker pointing to a directory
        if list(workers.keys()) == ["static"]:
            artifact_kind = "static"
        else:
            artifact_kind = "nix"

        # 5. Return BuildArtifact
        return BuildArtifact(
            kind=artifact_kind,
            builder="nix",
            app_name=self.context.app_name,
            built_at=datetime.now(timezone.utc).isoformat(),
            build_id=self._get_build_id(store_path),
            location=store_path,
            runtime=runtime,
            metadata={
                "nix_file": str(nix_file),
                "store_path": store_path,
            },
        )

    def _generate_nix_file(self) -> Path:
        """Generate a hop3.nix from the [nix] section in hop3.toml.

        Creates a temporary file containing the generated Nix expression
        and returns its path. The file is written alongside the source
        (in a temp dir, not inside the source tree which may be read-only).

        Returns:
            Path to the generated hop3.nix file.

        Raises:
            RuntimeError: If the [nix] section is missing or invalid.
        """
        from hop3.lib import log  # noqa: PLC0415
        from hop3.plugins.build.nix.gen import generate  # noqa: PLC0415
        from hop3.plugins.build.nix.gen.toml_adapter import (  # noqa: PLC0415
            app_spec_from_config,
        )

        app_config = self.context.app_config or {}
        hop3_config = app_config.get("hop3_config", {})
        nix_config = hop3_config.get("nix", {})
        metadata = hop3_config.get("metadata", {})

        if not nix_config.get("template"):
            msg = (
                "No hop3.nix file found and no [nix].template in hop3.toml. "
                "Either provide a hop3.nix file or add a [nix] section with "
                'template = "prebuilt-binary" (or another template name).'
            )
            raise RuntimeError(msg)

        spec = app_spec_from_config(
            nix_config=nix_config,
            metadata=metadata,
            app_name=self.context.app_name,
        )
        nix_text = generate(spec)

        # Write into the source directory so that relative Nix paths
        # (e.g., bundlerEnv { gemdir = ./.; }) resolve correctly against
        # the app's source tree. Always writable during deployment.
        nix_file = self.context.source_path / "hop3.nix"
        nix_file.write_text(nix_text)

        log(
            f"  [nix] Generated hop3.nix from template '{spec.template}' "
            f"({len(nix_text)} chars)",
            level=1,
            fg="blue",
        )
        return nix_file

    def _nix_available(self) -> bool:
        """Check if nix command is available on the system."""
        result = self._run_nix_command("nix --version")
        return result.returncode == 0

    def _kill_stale_nix_builds(self, nix_file: Path) -> None:
        """Kill any stale nix-build processes for the same nix file.

        When a previous deploy is killed mid-build, nix-build may leave
        a lock on the store path. A new nix-build for the same derivation
        will silently wait for the lock forever. Kill stale processes first.
        """
        from hop3.lib import log  # noqa: PLC0415

        try:
            result = subprocess.run(
                ["pgrep", "-f", f"nix-build.*{nix_file.name}"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                pids = result.stdout.strip().split("\n")
                log(
                    f"  Killing {len(pids)} stale nix-build process(es)",
                    level=1,
                    fg="yellow",
                )
                for pid in pids:
                    if pid.strip():
                        subprocess.run(["kill", "-9", pid.strip()], check=False)
                # Brief wait for locks to release
                import time  # noqa: PLC0415

                time.sleep(2)
        except Exception:
            pass  # Best effort — don't fail the build if cleanup fails

    def _nix_build(self, nix_file: Path) -> str:
        """Run nix-build and return the store path.

        Args:
            nix_file: Path to the hop3.nix file.

        Returns:
            The Nix store path of the built package.

        Raises:
            RuntimeError: If nix-build fails.
        """
        # Register a per-app GC root for the build output. With --no-out-link
        # nothing roots the closure, so a later nix garbage-collect (manual, or
        # auto-GC under disk pressure on a busy host) can delete a *running*
        # app's binary — e.g. forgejo's wrapper execs the hardcoded
        # ${forgejo}/bin/forgejo and the daemon dies with "No such file or
        # directory". The out-link lives in the app directory (NOT src/, which
        # the deployer now `git clean`s) and is removed when the app is
        # destroyed (robust_rmtree of app_path), so teardown also lets nix
        # reclaim the closure. nix-build still prints the store path to stdout.
        gcroot = self.context.source_path.parent / ".nix-result"
        prev_gcroot = self.context.source_path.parent / ".nix-result-prev"
        # Keep the IMMEDIATELY-PRIOR closure rooted THROUGHOUT this rebuild. A
        # still-running old worker may exec a store path baked into the previous
        # closure (forgejo's wrapper execs ${forgejo}/bin/forgejo); a GC firing
        # mid-rebuild would reclaim it and the old daemon dies "No such file or
        # directory". Two things this has to get right, both of which the old
        # `gcroot.rename(prev_gcroot)` got wrong:
        #   * Register a REAL indirect GC root. `Path.rename` cannot carry a nix
        #     root: nix keeps gcroots/auto/<hash> pointing at the *old name*
        #     (.nix-result), so the renamed .nix-result-prev is a plain dangling
        #     symlink, NOT a root — the previous closure was never actually held.
        #   * Register it BEFORE nix-build, not after. Rotating first left the old
        #     closure unrooted for the build's whole multi-minute duration.
        # `nix-store --realise <old> --add-root prev --indirect` roots the EXISTING
        # old path independently of .nix-result. Both roots live in the app dir, so
        # destroy() (rmtree of app_path) frees them and lets nix reclaim the closure.
        if gcroot.is_symlink():
            old_store = os.path.realpath(gcroot)
            if os.path.exists(old_store):
                if prev_gcroot.is_symlink() or prev_gcroot.exists():
                    prev_gcroot.unlink()
                prev_result = self._run_nix_command(
                    f"nix-store --realise {shlex.quote(old_store)}"
                    f" --add-root {shlex.quote(str(prev_gcroot))} --indirect",
                    cwd=nix_file.parent,
                )
                if prev_result.returncode != 0:
                    # Non-fatal to THIS deploy (the new closure still gets rooted
                    # below), but surface it: a GC during the rebuild could now
                    # disrupt the still-running old worker.
                    log(
                        "Warning: could not retain previous nix closure root: "
                        f"{prev_result.stderr.strip()}",
                        level=1,
                        fg="yellow",
                    )
        # --option build-timeout: 30-minute wall clock.
        # --option build-max-silent-time: 5-minute no-output watchdog (the
        #   real guard against lock waits and stalled downloads).
        cmd = (
            f"nix-build {nix_file} -A package --out-link {shlex.quote(str(gcroot))}"
            f" --option build-timeout {NIX_BUILD_TIMEOUT_SECONDS}"
            f" --option build-max-silent-time {NIX_BUILD_MAX_SILENT_SECONDS}"
        )
        result = self._run_nix_command(cmd, cwd=nix_file.parent)

        # Persist the full nix-build output (success OR failure) so a failed nix
        # build (e.g. a dangling store reference) is retrievable via `hop3 app
        # logs --build` and the test diagnostic bundle, instead of vanishing with
        # the deploy stream. NixBuilder previously wrote no build.log at all.
        self._save_build_log(
            f"{result.stdout}\n{result.stderr}".strip(),
            success=result.returncode == 0,
        )

        if result.returncode != 0:
            msg = f"nix-build failed: {result.stderr}"
            raise RuntimeError(msg)

        return result.stdout.strip()

    def _save_build_log(self, output: str, *, success: bool) -> None:
        """Write the nix-build output to APP_ROOT/<app>/log/build.log.

        Same sink every reader uses (`hop3 app logs --build`, the diagnostic
        bundle); best-effort, never fatal.
        """
        try:
            app_log_dir = APP_ROOT / self.context.app_name / "log"
            app_log_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            status = "SUCCESS" if success else "FAILED"
            content = (
                "=== Nix Build Log ===\n"
                f"Timestamp: {timestamp}\n"
                f"App: {self.context.app_name}\n"
                f"Status: {status}\n"
                "Builder: nix\n\n"
                f"=== BUILD OUTPUT ===\n{output}\n"
            )
            (app_log_dir / "build.log").write_text(content)
            log(f"Build log saved to: {app_log_dir / 'build.log'}", level=2)
        except Exception as e:  # logging must never break a build
            log(f"Could not save nix build log: {e}", level=1, fg="yellow")

    def _run_nix_command(
        self,
        cmd: str,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess:
        """Run a Nix command with the Nix profile sourced.

        Nix commands require the profile to be sourced to set PATH correctly.
        This handles both single-user (~/.nix-profile) and multi-user
        (/nix/var/nix/profiles/default) installations.

        Args:
            cmd: The Nix command to run.
            cwd: Working directory for the command.

        Returns:
            CompletedProcess with stdout, stderr, and returncode.
        """
        # Find available Nix profile script
        profile_script = self._find_nix_profile()

        if profile_script:
            # Source the profile and run the command
            shell_cmd = f'. "{profile_script}" && {cmd}'
        else:
            # No profile found, try running directly (might work if in PATH)
            shell_cmd = cmd

        # Stream stderr for real-time build progress while capturing stdout
        proc = subprocess.Popen(
            ["bash", "-c", shell_cmd],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd,
            env=self._get_nix_env(),
        )
        assert proc.stderr is not None
        assert proc.stdout is not None

        stderr_lines: list[str] = []
        for line in proc.stderr:
            stripped = line.rstrip()
            stderr_lines.append(line)
            if stripped:
                log(f"  [nix] {stripped}", level=1)

        proc.wait()
        stdout = proc.stdout.read()

        return subprocess.CompletedProcess(
            ["bash", "-c", shell_cmd],
            proc.returncode,
            stdout,
            "".join(stderr_lines),
        )

    def _get_nix_profile_paths(self) -> list[Path]:
        """Get potential Nix profile script paths.

        Evaluates paths at runtime to ensure HOME is correct for the
        current process context (important when running as hop3 user).

        Returns:
            List of profile script paths to try.
        """
        return [
            Path.home() / ".nix-profile/etc/profile.d/nix.sh",
            NIX_DAEMON_PROFILE,
        ]

    def _find_nix_profile(self) -> Path | None:
        """Find the Nix profile script.

        Returns:
            Path to the profile script, or None if not found.
        """
        for script in self._get_nix_profile_paths():
            if script.exists():
                return script
        return None

    def _get_nix_env(self) -> dict[str, str]:
        """Get environment variables for Nix commands.

        The Nix profile script requires HOME and USER to be set.
        Supervisor may not set PATH, so we provide a minimal one.

        Returns:
            Environment dict with HOME, USER, and PATH set correctly.
        """
        env = os.environ.copy()

        # Ensure HOME is set for profile sourcing
        if "HOME" not in env:
            env["HOME"] = str(Path.home())

        # Ensure USER is set - required by Nix profile script
        if "USER" not in env:
            try:
                env["USER"] = pwd.getpwuid(os.getuid()).pw_name
            except (KeyError, OSError):
                env["USER"] = "hop3"  # Fallback

        # Ensure PATH includes essential directories
        # Supervisor may not set PATH, so we need to provide a minimal one
        if "PATH" not in env:
            env["PATH"] = "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

        return env

    def _get_build_id(self, store_path: str) -> str:
        """Extract Nix hash from store path.

        Args:
            store_path: Full Nix store path like /nix/store/abc123-myapp

        Returns:
            The hash portion (abc123) of the store path.
        """
        # /nix/store/abc123-myapp -> abc123
        name = Path(store_path).name
        return name.split("-")[0] if "-" in name else name
