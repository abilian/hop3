# Copyright (c) 2025-2026, Abilian SAS
#
# SPDX-License-Identifier: AGPL-3.0-only

# ruff: noqa: TRY003, EM101, EM102, TC001, C901, PLR0912, PLR0915

"""php-app template.

For PHP applications served via PHP's built-in web server (``php -S``) or
Laravel's artisan serve. Uses ``pkgs.php82.withExtensions`` to build a
PHP interpreter with the required extensions, then copies the app source
to ``$out/app`` and wraps it with a startup script.

Supports three variations:
    - Tarball source (wordpress, nextcloud, bookstack) — default
    - Single PHP file (adminer) — set ``single_file = True``
    - Composer build (bookstack, dolibarr) — set ``needs_composer = True``

Example apps: WordPress, Nextcloud, BookStack, Adminer, Kanboard.
"""

from __future__ import annotations

from hop3.plugins.build.nix.gen.spec import AppSpec
from hop3.plugins.build.nix.gen.templates.base import (
    PINNED_NIXPKGS_HEADER,
    format_nix_env_attrs,
    format_paths_json,
    format_runtime_env_json,
    format_wrapper_body,
)


class PhpAppTemplate:
    name = "php-app"

    def generate(self, spec: AppSpec) -> str:
        binding = f"{spec.pname}-src"
        source_nix = spec.source.as_nix(binding)

        # PHP let-binding with extensions
        php_binding = _format_php_binding(spec)
        composer_binding = ""
        if spec.needs_composer:
            composer_binding = (
                f"\n  composer = pkgs.{spec.php_version}Packages.composer;\n"
            )

        # Native build inputs: always php and (if needed) composer + extras
        native_inputs: list[str] = []
        if spec.needs_composer:
            native_inputs.extend(["php", "composer"])
        elif spec.source.needs_unzip:
            # At minimum, we need unzip if the archive is a zip
            pass
        if spec.source.needs_unzip:
            native_inputs.append("pkgs.unzip")
        native_inputs.extend(spec.extra_native_build_inputs)

        native_build_inputs = ""
        if native_inputs:
            native_build_inputs = (
                f"    nativeBuildInputs = [ {' '.join(native_inputs)} ];\n"
            )

        # Build phase (composer install) — uses __noChroot for network access
        no_chroot = ""
        build_phase = ""
        if spec.needs_composer:
            no_chroot = "    # Allow network access during build (composer install)\n    __noChroot = true;\n"
            extra_flags = (
                " " + " ".join(spec.composer_extra_flags)
                if spec.composer_extra_flags
                else ""
            )
            build_phase = f"""    buildPhase = ''
      export COMPOSER_HOME=$(mktemp -d)
      composer install --no-dev --optimize-autoloader --no-interaction{extra_flags} || true
    '';
"""

        # Unpack phase
        if spec.single_file:
            unpack_phase = "    dontUnpack = true;\n    dontBuild = true;\n"
        elif spec.source.archive is None:
            raise ValueError(
                f"{spec.pname}: php-app with non-single-file source requires "
                f"an archive type (e.g., archive='tar-gz')"
            )
        else:
            unpack_cmd = spec.source.unpack_command(spec.strip_components)
            unpack_phase = f"""    unpackPhase = ''
      {unpack_cmd}
    '';
"""
            if not spec.needs_composer:
                unpack_phase += "    dontBuild = true;\n"

        # Install phase body
        install_lines: list[str] = [
            "      mkdir -p $out/app $out/bin $out/hop3",
            "",
        ]

        if spec.single_file:
            # For single-file PHP apps like adminer: the file is $src itself
            install_lines.append("      cp $src $out/app/index.php")
        elif not spec.skip_source_copy:
            # If source_root is set, copy from that subdir (e.g., limesurvey's
            # zip contains a wrapper directory).
            copy_src = f"{spec.source_root}/." if spec.source_root else "."
            install_lines.append(f"      cp -r {copy_src} $out/app/")

        if spec.post_install_dirs:
            dirs = " ".join(f"$out/app/{d}" for d in spec.post_install_dirs)
            install_lines.append(f"      mkdir -p {dirs}")

        install_lines.append("")

        # When needs_writable_dir is set, inject symlink-from-store commands
        # into pre_exec so the app can generate config files at runtime.
        # The Nix store is read-only, so apps that need .env, config.php,
        # or writable storage/ must operate from a cwd-based copy.
        extra_pre_exec: list[str] = []
        if spec.needs_writable_dir:
            # Copy ALL files from the Nix store to the writable cwd.
            # We use cp -a (not symlinks) because PHP's __DIR__ resolves
            # symlinks, and when it resolves to the read-only Nix store,
            # Laravel/PHP can't find .env, write to storage/, etc.
            # The disk cost is acceptable (~50-200 MB per app).
            extra_pre_exec.append(
                "# Copy app from read-only Nix store to writable cwd\n"
                "cp -a APPDIR/. .\n"
                "chmod -R u+w ."
            )
            if spec.post_install_dirs:
                dirs = " ".join(spec.post_install_dirs)
                extra_pre_exec.append(f"mkdir -p {dirs}")

        # Build a modified spec with extra pre_exec commands if needed
        if extra_pre_exec:
            merged_pre_exec = list(extra_pre_exec) + list(spec.pre_exec_commands)
            # Create a new spec-like object with merged pre_exec (can't modify frozen)
            from dataclasses import replace  # noqa: PLC0415

            spec = replace(spec, pre_exec_commands=merged_pre_exec)

        # Wrapper script. Uses APPDIR and PHPBIN placeholders which are
        # sed-replaced during the install phase — APPDIR → $out/app,
        # PHPBIN → ${{php}}/bin (the latter is Nix-interpolated to the
        # actual php store path before sed runs).
        exec_line = _php_exec_line(spec)
        wrapper_body = format_wrapper_body(spec, exec_line)
        wrapper_section = f"""      cat > $out/bin/{spec.pname} << 'WRAPPER'
{wrapper_body}
WRAPPER
      sed -i "s|APPDIR|$out/app|g" $out/bin/{spec.pname}
      sed -i "s|PHPBIN|${{php}}/bin|g" $out/bin/{spec.pname}
      chmod +x $out/bin/{spec.pname}"""
        install_lines.append(wrapper_section)
        install_lines.append("")

        # runtime.json — extra_paths can include "${php}/bin" etc., which Nix
        # interpolates at build time (they're inside the installPhase string).
        runtime_env_json = format_runtime_env_json(spec.runtime_env)
        paths_json = format_paths_json(spec.extra_paths)
        runtime_json_section = f"""      cat > $out/hop3/runtime.json << EOF
{{
  "workers": {{
    "web": "$out/bin/{spec.pname}"
  }},
  "env": {{
{runtime_env_json}
  }},
  "path": [
    {paths_json}
  ]
}}
EOF"""
        install_lines.append(runtime_json_section)
        install_body = "\n".join(install_lines)

        nix_env_attrs = format_nix_env_attrs(spec.runtime_env)

        return f"""# hop3.nix - Nix expression for {spec.pname}
#
# GENERATED from template 'php-app' by hop3-nix-gen.
# Run 'hop3 nix eject {spec.pname}' to materialize for customization.

{PINNED_NIXPKGS_HEADER}

let
  version = "{spec.version}";

{php_binding}{composer_binding}
{source_nix}

  app = pkgs.stdenv.mkDerivation {{
{no_chroot}    pname = "{spec.pname}";
    inherit version;
    meta = {{
      description = "{spec.description}";
    }};

    src = {binding};
{native_build_inputs}{unpack_phase}{build_phase}
    installPhase = ''
{install_body}
    '';
  }};

in
{{
  package = app;

  env = {{{nix_env_attrs}}};
}}
"""


def _format_php_binding(spec: AppSpec) -> str:
    """Emit the `php = pkgs.phpXX.withExtensions (...)` let-binding."""
    exts = "\n".join(f"    all.{ext}" for ext in spec.php_extensions)
    if exts:
        return f"""  php = pkgs.{spec.php_version}.withExtensions ({{ enabled, all }}: enabled ++ [
{exts}
  ]);"""
    return f"  php = pkgs.{spec.php_version};"


def _php_exec_line(spec: AppSpec) -> str:
    """Generate the exec line for the wrapper based on serve_mode.

    Placeholders (sed-replaced in install phase):
        APPDIR → $out/app
        PHPBIN → ${php}/bin (the actual php store path)

    Shell variables like ${PORT:-8080} are Nix-escaped by the base
    formatter, so they reach the wrapper as ${PORT:-8080} and are
    expanded by the shell at startup.
    """
    # When needs_writable_dir, serve from cwd (.) instead of APPDIR (Nix store).
    # The wrapper's pre_exec commands symlink app files to cwd first.
    if spec.needs_writable_dir:
        doc_root = f"./{spec.web_root}" if spec.web_root else "."
    elif spec.web_root:
        doc_root = f"APPDIR/{spec.web_root}"
    else:
        doc_root = "APPDIR"

    if spec.serve_mode == "builtin":
        return f"PHPBIN/php -S 0.0.0.0:${{PORT:-8080}} -t {doc_root}"
    if spec.serve_mode == "artisan":
        artisan = "./artisan" if spec.needs_writable_dir else "APPDIR/artisan"
        return f"PHPBIN/php {artisan} serve --host=0.0.0.0 --port=${{PORT:-8080}}"
    if spec.serve_mode == "custom":
        if spec.exec_target is None:
            raise ValueError("serve_mode='custom' requires exec_target")
        return spec.exec_target
    raise ValueError(f"Unknown serve_mode: {spec.serve_mode}")
