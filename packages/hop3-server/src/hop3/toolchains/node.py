# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Language toolchain for Node projects."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hop3 import config as c
from hop3.core.env import Env
from hop3.core.events import InstallingVirtualEnv, emit
from hop3.lib import Abort, chdir, check_binaries, log, prepend_to_path

from ._base import LanguageToolchain

if TYPE_CHECKING:
    from hop3.core.protocols import BuildArtifact


class NodeToolchain(LanguageToolchain):
    """Language toolchain for Node projects."""

    name = "Node"
    requirements = ["node", "npm"]  # noqa: RUF012

    # FIXME: should be more complex
    # check_requirements(["nodejs", "npm"])
    # or check_requirements(["node", "npm"])
    # or check_requirements(["nodeenv"])

    def accept(self) -> bool:
        """Check if the package.json file exists in the specified app path."""
        return self.check_exists("package.json")

    def _get_declared_node_version(self) -> str | None:
        """Return `[build].node-version` from hop3.toml if set.

        Lets apps pin a Node version per-app (blocker #8) without
        relying on the host's `apt install nodejs`. The existing
        `install_node()` path takes over once NODE_VERSION is present
        in the env (uses `nodeenv --prebuilt --node=<version>` against
        the app's virtualenv).
        """
        if self.context is None:
            return None
        app_config = self.context.app_config
        hop3_config = app_config.get("hop3_config", {})
        if not isinstance(hop3_config, dict):
            return None
        build_section = hop3_config.get("build", {})
        if not isinstance(build_section, dict):
            return None
        value = build_section.get("node-version")
        return str(value) if value else None

    def build(self) -> BuildArtifact:
        """Build the project environment.

        This creates the necessary directories and installs the required
        dependencies for the project.
        """
        self.virtual_env.mkdir(parents=True, exist_ok=True)

        with chdir(self.src_path):
            env = self.get_env()
            # `[build].node-version` in hop3.toml surfaces as NODE_VERSION
            # so install_node()'s existing nodeenv path picks it up.
            # Declared structurally (typed, discoverable) instead of via
            # [env] as a raw env var. Explicit [env] NODE_VERSION wins
            # if both are set.
            if "NODE_VERSION" not in env:
                pinned = self._get_declared_node_version()
                if pinned:
                    env["NODE_VERSION"] = pinned
                    log(
                        f"Using [build].node-version = {pinned!r} from hop3.toml",
                        level=2,
                        fg="cyan",
                    )
            self.install_node(env)
            self.install_modules(env)

        # Compute environment variables for runtime
        node_modules = self.src_path / "node_modules"
        npm_prefix = node_modules.parent.absolute()

        env_vars = {
            "NODE_PATH": str(node_modules),
            "NPM_CONFIG_PREFIX": str(npm_prefix),
        }

        # Paths to prepend to PATH
        path_prepend = [
            str(self.virtual_env / "bin"),
            str(node_modules / ".bin"),
        ]

        # Create runtime configuration
        runtime = self._make_runtime_config(
            env_vars=env_vars,
            path_prepend=path_prepend,
        )

        # Return complete BuildArtifact with runtime config
        return self._make_build_artifact(
            kind="node",
            runtime=runtime,
            metadata={
                "node_modules": str(node_modules),
            },
        )

    def get_env(self) -> Env:
        """Get the environment variables for the application.

        Returns
        -------
            Env: An environment object containing the necessary variables for the application.
        """
        node_modules = self.src_path / "node_modules"
        # npm_prefix = os.path.abspath(os.path.join(node_modules, ".."))
        npm_prefix = node_modules.parent.absolute()
        path = prepend_to_path(
            [
                self.virtual_env / "bin",
                node_modules / ".bin",
            ],
        )
        env = Env(
            {
                "VIRTUAL_ENV": self.virtual_env,
                "NODE_PATH": node_modules,
                "NPM_CONFIG_PREFIX": npm_prefix,
                "PATH": path,
            },
        )
        env.parse_settings(self.env_file)
        return env

    def install_node(self, env: Env) -> None:
        """Provision the pinned Node.js version into the app venv via nodeenv.

        When no version is pinned, the build uses the system Node (a modern
        NodeSource LTS, provisioned by the installer) and there's nothing to
        do here. When `[build].node-version` is pinned, install exactly that
        version into the app venv with `nodeenv --prebuilt`.

        A pin that can't be honored fails loudly: previously, if `nodeenv`
        was absent the pin was silently ignored and the build ran on the
        system Node, dying deep in `npm`/`pnpm` with an opaque version error.

        Args:
        ----
            env (Env): Environment variables, including the optional
            'NODE_VERSION' specifying the Node.js version to install.

        Raises:
        ------
            Abort: If `nodeenv` is unavailable for a pinned version, or if
            trying to update Node.js while the application is running.
        """
        version = env.get("NODE_VERSION")
        if not version:
            # No per-app pin: use the system Node (NodeSource LTS).
            return

        if not check_binaries(["nodeenv"]):
            msg = (
                f"App pins [build].node-version = {version!r} but `nodeenv` is "
                f"not available on the server, so that version can't be "
                f"installed. Install it (`npm install -g nodeenv`) or remove "
                f"the pin to use the system Node."
            )
            raise Abort(msg)

        node_binary = self.virtual_env / "bin" / "node"
        if node_binary.exists():
            completed_process = self.shell(f"{node_binary} -v", env=env)
            installed = completed_process.stdout.decode("utf8").rstrip("\n")
        else:
            installed = ""

        if installed.endswith(version):
            log(f"Node is installed at {version}.", level=3, fg="green")
            return

        started = list(c.UWSGI_ENABLED.glob(f"{self.app_name}*.ini"))
        if installed and started:
            # Raise an error if the app is running
            msg = "Warning: Can't update node with app running. Stop the app & retry."
            raise Abort(msg)

        log(
            f"Installing node version '{version}' using nodeenv",
            level=3,
            fg="green",
        )
        cmd = f"nodeenv --prebuilt --node={version} --clean-src --force {self.virtual_env}"
        self.shell(cmd, cwd=self.virtual_env, env=env)

    def install_modules(self, env: Env) -> None:
        """Install necessary modules for the application.

        If a custom build command is specified in hop3.toml [build] section,
        that command is run instead of the default npm install. This allows
        projects using pnpm, yarn workspaces, or custom build scripts to work.

        Otherwise, this uses npm to install the dependencies listed in the
        'package.json' file located at the specified source path.
        """
        emit(InstallingVirtualEnv(self.app_name))

        # Check if custom build command is specified in hop3.toml
        custom_build = self._get_custom_build_command()
        if custom_build:
            log(f"Running custom build command: {custom_build}", level=2, fg="cyan")
            self.shell(custom_build, env=env)
            return

        # If a prebuild step already populated node_modules (e.g. before-build
        # ran `npm install && npm run build`), don't run a second npm install
        # over it. The toolchain's `--package-lock=false` re-resolve diverges
        # from the freshly-built tree and corrupts it — npm fails with ENOENT on
        # platform optional deps (@tailwindcss/oxide-*, nextjs) or ENOTEMPTY
        # during cleanup (nuxtjs). The build output (.next/.output/dist) is
        # already in place; reinstalling buys nothing.
        node_modules = self.src_path / "node_modules"
        if node_modules.is_dir() and any(node_modules.iterdir()):
            log(
                "node_modules already present (prebuild installed it); "
                "skipping toolchain npm install",
                level=2,
                fg="cyan",
            )
            return

        # Default: install exactly what the lockfile pins.
        npm_prefix = self.src_path
        package_json = self.src_path / "package.json"

        assert package_json.exists()
        assert check_binaries(["npm"])

        # `npm ci` installs the dependency tree recorded in the lockfile and
        # nothing else. The alternative, `npm install --package-lock=false`,
        # re-resolves every semver range against the registry on each build, so
        # two deploys of the same commit can ship different dependency trees —
        # the build is then neither reproducible nor auditable.
        lockfile = next(
            (
                self.src_path / name
                for name in ("npm-shrinkwrap.json", "package-lock.json")
                if (self.src_path / name).exists()
            ),
            None,
        )
        if lockfile is None:
            msg = (
                f"{self.app_name} has no package-lock.json (or npm-shrinkwrap.json), "
                f"so its dependencies are not pinned and the build cannot be "
                f"reproduced. Commit the lockfile generated by `npm install`."
            )
            raise Abort(msg)

        # --legacy-peer-deps keeps projects with peer-dependency conflicts
        # installable (HedgeDoc, Umami); the tree still comes from the lockfile.
        cmd = f"npm ci --prefix {npm_prefix} --legacy-peer-deps"
        self.shell(cmd, env=env)
