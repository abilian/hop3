# Copyright (c) 2025-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

# ruff:file-ignore[raise-vanilla-args, raw-string-in-exception, f-string-in-exception, complex-structure, too-many-branches, too-many-statements]


"""
php-app template.

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

from dataclasses import replace

from hop3.plugins.build.nix.gen.spec import AppSpec, PhpAppPayload
from hop3.plugins.build.nix.gen.templates.base import (
    ReproTier,
    format_nix_env_attrs,
    format_paths_json,
    format_runtime_env_json,
    format_wrapper_body,
    pinned_nixpkgs_header,
)

_NO_COMPOSER_HASH = (
    "{pname}: php-app with needs_composer requires `composer-deps-hash` in "
    "[nix] — the buildComposerProject vendorHash. Build once with a "
    'placeholder (`composer-deps-hash = "sha256-'
    'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="`) and read the `got:` '
    "hash Nix reports, or run `hop3-tools nix vendor-hash <app-dir>`."
)


class PhpAppTemplate:
    name = "php-app"
    tier = ReproTier.SOURCE

    def generate(self, spec: AppSpec) -> str:
        p = spec.payload_as(PhpAppPayload)
        binding = f"{spec.pname}-src"
        source_nix = spec.source.as_nix(binding)

        # PHP let-binding with extensions
        php_binding = _format_php_binding(p)
        composer_binding = ""  # buildComposerProject brings its own composer

        # Native build inputs. Composer apps are built by buildComposerProject
        # (below); the wrapping derivation only copies its output, so it needs
        # neither php nor composer here.
        native_inputs: list[str] = []
        if spec.source.needs_unzip:
            native_inputs.append("pkgs.unzip")
        native_inputs.extend(p.extra_native_build_inputs)

        native_build_inputs = ""
        if native_inputs:
            native_build_inputs = (
                f"    nativeBuildInputs = [ {' '.join(native_inputs)} ];\n"
            )

        # Composer apps are compiled from source by buildComposerProject — the
        # nixpkgs composer builder, the composer analogue of buildGoModule.
        # composer.lock fixes the dependency set (a `dist.shasum` per package)
        # and vendorHash pins the resolved tree, so the build is hermetic. Its
        # output may legitimately reference store paths (bin proxies -> bash),
        # which a fixed-output derivation vendoring the tree by hand may not —
        # that constraint is why the earlier FOD approach could not build.
        no_chroot = ""
        build_phase = ""
        composer_project = ""
        if p.needs_composer:
            if not p.composer_deps_hash:
                raise ValueError(_NO_COMPOSER_HASH.format(pname=spec.pname))
            source_root_attr = (
                f'\n    sourceRoot = "{spec.source_root}";' if spec.source_root else ""
            )
            # composer validate is pedantic; skip it explicitly when a
            # third-party release fails it for benign reasons.
            strict_attr = (
                ""
                if p.composer_strict_validation
                else "\n    composerStrictValidation = false;"
            )
            composer_project = f"""
  # Built from source, offline, inside the sandbox; result at
  # $out/share/php/{spec.pname}/.
  composerProject = pkgs.{p.php_version}.buildComposerProject {{
    pname = "{spec.pname}";
    inherit version;
    src = {binding};{source_root_attr}
    vendorHash = "{p.composer_deps_hash}";
    composerNoDev = true;{strict_attr}
  }};
"""

        # Unpack phase
        if p.single_file or p.needs_composer:
            # single-file: $src is the file itself. composer: buildComposerProject
            # already unpacked + built the source, so the wrapping derivation
            # only copies its output.
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
    dontBuild = true;
"""

        # Install phase body
        install_lines: list[str] = [
            "      mkdir -p $out/app $out/bin $out/hop3",
            "",
        ]

        if p.single_file:
            # For single-file PHP apps like adminer: the file is $src itself
            install_lines.append("      cp $src $out/app/index.php")
        elif p.needs_composer:
            # The composer-built tree (source + vendor/ + optimized autoloader).
            install_lines.append(
                f"      cp -r ${{composerProject}}/share/php/{spec.pname}/. $out/app/"
            )
            install_lines.append("      chmod -R u+w $out/app")
        elif not p.skip_source_copy:
            # If source_root is set, copy from that subdir (e.g., limesurvey's
            # zip contains a wrapper directory).
            copy_src = f"{spec.source_root}/." if spec.source_root else "."
            install_lines.append(f"      cp -r {copy_src} $out/app/")

        if p.post_install_dirs:
            dirs = " ".join(f"$out/app/{d}" for d in p.post_install_dirs)
            install_lines.append(f"      mkdir -p {dirs}")

        install_lines.append("")

        # When needs_writable_dir is set, materialize the store tree into the
        # writable cwd. The Nix store is read-only, so apps that need .env,
        # config.php, or writable storage/ must operate from a cwd-based copy.
        #
        # This MUST land in the runtime prelude, not pre_exec: the wrapper emits
        # prelude -> config-files -> pre-exec, so a copy sitting in pre_exec runs
        # AFTER the generated config files and copies the upstream tree straight
        # over them. Today that is harmless only by luck — these apps ship
        # `config-sample.php` / `.env.example`, never the real filename — but any
        # app shipping a default `config.php` would have Hop3's rendered config
        # silently replaced by the upstream default, and serve unconfigured.
        # Ordering now: copy tree -> render config -> pre-exec (install commands,
        # which legitimately depend on the config) -> exec.
        if p.needs_writable_dir:
            # cp -a (not symlinks) because PHP's __DIR__ resolves symlinks, and
            # when it resolves back into the read-only Nix store, Laravel/PHP
            # can't find .env, write to storage/, etc. Disk cost ~50-200 MB/app.
            prelude_parts = [
                (
                    "# Copy app from read-only Nix store to writable cwd\n"
                    "cp -a APPDIR/. .\n"
                    "chmod -R u+w ."
                )
            ]
            if p.post_install_dirs:
                dirs = " ".join(p.post_install_dirs)
                prelude_parts.append(f"mkdir -p {dirs}")
            if spec.runtime_prelude:
                prelude_parts.append(spec.runtime_prelude)

            spec = replace(spec, runtime_prelude="\n\n".join(prelude_parts))

        # Wrapper script. Uses APPDIR and PHPBIN placeholders which are
        # sed-replaced during the install phase — APPDIR → $out/app,
        # PHPBIN → ${{php}}/bin (the latter is Nix-interpolated to the
        # actual php store path before sed runs).
        exec_line = _php_exec_line(spec, p)
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

{pinned_nixpkgs_header(spec.nixpkgs_rev, spec.nixpkgs_sha256)}

let
  version = "{spec.version}";

{php_binding}{composer_binding}
{source_nix}
{composer_project}

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


def _format_php_binding(p: PhpAppPayload) -> str:
    """Emit the `php = pkgs.phpXX.withExtensions (...)` let-binding."""
    exts = "\n".join(f"    all.{ext}" for ext in p.php_extensions)
    if exts:
        return f"""  php = pkgs.{p.php_version}.withExtensions ({{ enabled, all }}: enabled ++ [
{exts}
  ]);"""
    return f"  php = pkgs.{p.php_version};"


def _php_exec_line(spec: AppSpec, p: PhpAppPayload) -> str:
    """
    Generate the exec line for the wrapper based on serve_mode.

    Placeholders (sed-replaced in install phase):
        APPDIR → $out/app
        PHPBIN → ${php}/bin (the actual php store path)

    Shell variables like ${PORT:-8080} are Nix-escaped by the base
    formatter, so they reach the wrapper as ${PORT:-8080} and are
    expanded by the shell at startup.
    """
    # When needs_writable_dir, serve from cwd (.) instead of APPDIR (Nix store).
    # The wrapper's pre_exec commands symlink app files to cwd first.
    if p.needs_writable_dir:
        doc_root = f"./{p.web_root}" if p.web_root else "."
    elif p.web_root:
        doc_root = f"APPDIR/{p.web_root}"
    else:
        doc_root = "APPDIR"

    if p.serve_mode == "builtin":
        return f"PHPBIN/php -S 0.0.0.0:${{PORT:-8080}} -t {doc_root}"
    if p.serve_mode == "artisan":
        artisan = "./artisan" if p.needs_writable_dir else "APPDIR/artisan"
        return f"PHPBIN/php {artisan} serve --host=0.0.0.0 --port=${{PORT:-8080}}"
    if p.serve_mode == "custom":
        if spec.exec_target is None:
            raise ValueError("serve_mode='custom' requires exec_target")
        return spec.exec_target
    raise ValueError(f"Unknown serve_mode: {p.serve_mode}")
