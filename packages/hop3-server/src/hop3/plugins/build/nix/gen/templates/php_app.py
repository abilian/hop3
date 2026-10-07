# Copyright (c) 2025-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0


"""
php-app template.

For PHP applications, served by a php-fpm pool behind the reverse proxy, as
a native PHP app is. Uses ``pkgs.php82.withExtensions`` to build a PHP
interpreter with the required extensions, copies the app source to
``$out/app``, and asks Hop3 for the pool in runtime.json. PHP's built-in
server and Laravel's artisan serve stay available as serve modes.

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
    eject_hint,
    format_nix_env_attrs,
    format_runtime_json,
    format_wrapper_body,
    generated_line,
    local_source_expr,
    pinned_nixpkgs_header,
)
from hop3.run.spawn import PHP_BUILTIN_SERVER_WORKERS

_NO_COMPOSER_HASH = (
    "{pname}: php-app with needs_composer requires `composer-deps-hash` in "
    "[nix] — the buildComposerProject vendorHash. Build once with a "
    'placeholder (`composer-deps-hash = "sha256-'
    'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="`) and read the `got:` '
    "hash Nix reports, or run `hop3-tools nix vendor-hash <app-dir>`."
)


#: Serve modes that run PHP's own web server, which is single-threaded.
#: `artisan serve` is the same server behind a Laravel wrapper.
_CONCURRENT_SERVE_MODES = frozenset({"builtin", "artisan"})


class PhpAppTemplate:
    name = "php-app"
    tier = ReproTier.SOURCE

    def generate(self, spec: AppSpec) -> str:
        """Render hop3.nix for a PHP app.

        Each `_`-prefixed helper below owns one section of the expression; this
        stays an orchestrator so the whole file no longer needs a file-scope
        ruff suppression for complexity/branches/statements.
        """
        p = spec.payload_as(PhpAppPayload)

        # No `url` means the application IS the recipe directory — a user's own
        # code pushed to Hop3, rather than third-party software fetched from a
        # release. Without this the Nix path is reachable only for software
        # someone else publishes, which is not the case a PaaS exists for.
        local_source = not spec.source.url
        if local_source:
            _refuse_unsupported_local_combinations(spec, p)
            binding = local_source_expr()
            source_binding = ""
        else:
            binding = f"{spec.pname}-src"
            source_binding = spec.source.as_nix(binding)

        composer_project = _composer_project(spec, p, binding)
        unpack_phase = _unpack_phase(spec, p, local_source=local_source)

        # Must precede the wrapper: the writable-tree copy belongs in the
        # runtime prelude (before the generated config files), not pre_exec.
        spec = _with_writable_prelude(spec, p)

        install_lines = [
            *_source_install_lines(spec, p),
            "",
            _wrapper_section(spec, p),
            "",
            _runtime_json_section(spec, p),
        ]

        runtime_env = _runtime_env(spec, p)

        return f"""# hop3.nix - Nix expression for {spec.pname}
#
{generated_line("php-app")}
{eject_hint()}

{pinned_nixpkgs_header(spec.nixpkgs_rev, spec.nixpkgs_sha256)}

let
  version = "{spec.version}";

{_format_php_binding(p)}
{source_binding}
{composer_project}

  app = pkgs.stdenv.mkDerivation {{
    pname = "{spec.pname}";
    inherit version;
    meta = {{
      description = "{spec.description}";
    }};

    src = {binding};
{_native_build_inputs(spec, p)}{unpack_phase}
    installPhase = \'\'
{chr(10).join(install_lines)}
    \'\';
  }};

in
{{
  package = app;

  env = {{{format_nix_env_attrs(runtime_env)}}};
}}
"""


def _native_build_inputs(spec: AppSpec, p: PhpAppPayload) -> str:
    """`nativeBuildInputs` for the wrapping derivation, or "".

    Composer apps are built by buildComposerProject; the wrapping derivation
    only copies its output, so it needs neither php nor composer here.
    """
    native_inputs: list[str] = []
    if spec.source.needs_unzip:
        native_inputs.append("pkgs.unzip")
    native_inputs.extend(p.extra_native_build_inputs)
    if not native_inputs:
        return ""
    return f"    nativeBuildInputs = [ {' '.join(native_inputs)} ];\n"


def _refuse_unsupported_local_combinations(spec: AppSpec, p: PhpAppPayload) -> None:
    """
    Say plainly what local-source php-app does not do yet.

    Refused rather than half-supported: each of these would generate an
    expression that builds and then behaves wrongly, which is the failure mode
    that is expensive to diagnose.

    - **composer.** With `src = ./.` the app's own tree becomes an input to
      `buildComposerProject`, a hash-pinned build — so `composer-deps-hash`
      would pin the *user's* `composer.lock`. A recipe author records that hash
      by reading it off a failed build; someone pushing their own code has no
      such loop, and a hash that must be re-recorded on every `composer
      require` is not a deploy path.
    - **needs-writable-dir.** It makes the build emit `writable_tree =
      "$out/app"`, and the runtime materialisation copies that store tree back
      over the app's source directory — which in local mode is the directory
      the build just read. The app would overwrite its own source with a copy
      of itself.
    """
    if p.needs_composer:
        msg = (
            f"{spec.pname}: php-app cannot yet build from the recipe directory "
            f"AND run composer. `composer-deps-hash` would pin your own "
            f"composer.lock, and it has to be re-recorded from a failed build "
            f"every time a dependency changes. Commit `vendor/` and drop "
            f"`composer` from [nix], or package a released archive with a `url`."
        )
        raise ValueError(msg)
    if p.needs_writable_dir:
        msg = (
            f"{spec.pname}: php-app cannot build from the recipe directory with "
            f"`needs-writable-dir`. The writable tree is copied from the store "
            f"back over the app's source directory, which in this mode is the "
            f"directory the build read — the app would overwrite its own source."
        )
        raise ValueError(msg)


def _composer_project(spec: AppSpec, p: PhpAppPayload, binding: str) -> str:
    """The `composerProject` let-binding, or "" for non-composer apps.

    buildComposerProject is the composer analogue of buildGoModule:
    composer.lock fixes the dependency set (a `dist.shasum` per package) and
    vendorHash pins the resolved tree, so the build is hermetic. Its output may
    legitimately reference store paths (bin proxies -> bash), which a
    fixed-output derivation vendoring the tree by hand may not — that
    constraint is why the earlier FOD approach could not build.
    """
    if not p.needs_composer:
        return ""
    if not p.composer_deps_hash:
        msg = _NO_COMPOSER_HASH.format(pname=spec.pname)
        raise ValueError(msg)

    source_root_attr = (
        f'\n    sourceRoot = "{spec.source_root}";' if spec.source_root else ""
    )
    # buildComposerProject does its OWN unpack, so unzip must be in ITS inputs.
    # On the wrapping derivation alone (which sets dontUnpack) nix answered
    # `do not know how to unpack source archive` for any composer app shipped
    # as a .zip — and a release zip is exactly what you want to package when
    # the git tag lacks built assets.
    composer_unzip = (
        "\n    nativeBuildInputs = [ pkgs.unzip ];" if spec.source.needs_unzip else ""
    )
    # composer validate is pedantic; skip it explicitly when a third-party
    # release fails it for benign reasons.
    strict_attr = (
        ""
        if p.composer_strict_validation
        else "\n    composerStrictValidation = false;"
    )
    return f"""
  # Built from source, offline, inside the sandbox; result at
  # $out/share/php/{spec.pname}/.
  composerProject = pkgs.{p.php_version}.buildComposerProject {{
    pname = "{spec.pname}";
    inherit version;
    src = {binding};{source_root_attr}{composer_unzip}
    vendorHash = "{p.composer_deps_hash}";
    composerNoDev = true;{strict_attr}
  }};
"""


def _unpack_phase(
    spec: AppSpec, p: PhpAppPayload, *, local_source: bool = False
) -> str:
    """The unpack/build phase attributes."""
    if local_source:
        # `src` is a directory, so stdenv's default unpackPhase copies it into
        # the build tree — the same thing ruby-bundler's local mode relies on.
        # Emitting an unpackPhase here (or demanding an archive type below)
        # would be describing an archive that does not exist.
        return "    dontBuild = true;\n"
    if p.single_file or p.needs_composer:
        # single-file: $src is the file itself. composer: buildComposerProject
        # already unpacked + built the source, so the wrapping derivation only
        # copies its output.
        return "    dontUnpack = true;\n    dontBuild = true;\n"
    if spec.source.archive is None:
        msg = (
            f"{spec.pname}: php-app with non-single-file source requires "
            f"an archive type (e.g., archive='tar-gz')"
        )
        raise ValueError(msg)
    unpack_cmd = spec.source.unpack_command(spec.strip_components)
    return f"""    unpackPhase = \'\'
      {unpack_cmd}
    \'\';
    dontBuild = true;
"""


def _with_writable_prelude(spec: AppSpec, p: PhpAppPayload) -> AppSpec:
    """Fold the writable-dir setup into the runtime prelude.

    This MUST land in the runtime prelude, not pre_exec: the wrapper emits
    prelude -> config-files -> pre-exec, so a copy sitting in pre_exec runs
    AFTER the generated config files and copies the upstream tree straight over
    them. Today that is harmless only by luck — these apps ship
    `config-sample.php` / `.env.example`, never the real filename — but any app
    shipping a default `config.php` would have Hop3's rendered config silently
    replaced by the upstream default, and serve unconfigured.

    Note there is no `cp -a APPDIR/. .` here. Hop3 materialises the tree at
    deploy time from the `writable_tree` key in runtime.json, so it is in place
    before `[run] before-run` rather than after; copying here as well would
    overwrite a tree the bootstrap had just configured.
    """
    if not p.needs_writable_dir:
        return spec
    prelude_parts = []
    if p.post_install_dirs:
        prelude_parts.append(f"mkdir -p {' '.join(p.post_install_dirs)}")
    if spec.runtime_prelude:
        prelude_parts.append(spec.runtime_prelude)
    return replace(spec, runtime_prelude="\n\n".join(prelude_parts))


def _source_install_lines(spec: AppSpec, p: PhpAppPayload) -> list[str]:
    """installPhase lines that put the application tree into $out/app."""
    lines = ["      mkdir -p $out/app $out/bin $out/hop3", ""]

    if p.single_file:
        # For single-file PHP apps like adminer: the file is $src itself.
        lines.append("      cp $src $out/app/index.php")
    elif p.needs_composer:
        # The composer-built tree (source + vendor/ + optimized autoloader).
        lines.append(
            f"      cp -r ${{composerProject}}/share/php/{spec.pname}/. $out/app/"
        )
        lines.append("      chmod -R u+w $out/app")
    elif not p.skip_source_copy:
        # If source_root is set, copy from that subdir (e.g. limesurvey's zip
        # contains a wrapper directory).
        copy_src = f"{spec.source_root}/." if spec.source_root else "."
        lines.append(f"      cp -r {copy_src} $out/app/")

    if p.post_install_dirs:
        dirs = " ".join(f"$out/app/{d}" for d in p.post_install_dirs)
        lines.append(f"      mkdir -p {dirs}")

    # Ship recipe-local install/aux files into $out/app, so a pre-exec install
    # step can run the app's own installer script (e.g. WordPress's
    # wp-install.php, which is NOT in the upstream tarball). `${./<f>}` resolves
    # against the generated hop3.nix's own directory (the recipe dir), so Nix
    # imports each file from there; `install -D` recreates any parent dirs.
    # Copied AFTER the source so an aux file overrides a same-named upstream
    # file (intended), and lands in the writable cwd via the prelude above.
    lines.extend(f"      install -D ${{./{f}}} $out/app/{f}" for f in p.install_files)
    return lines


def _wrapper_section(spec: AppSpec, p: PhpAppPayload) -> str:
    """The heredoc that writes $out/bin/<pname>.

    Uses APPDIR and PHPBIN placeholders which are sed-replaced during the
    install phase — APPDIR -> $out/app, PHPBIN -> ${php}/bin (the latter is
    Nix-interpolated to the actual php store path before sed runs).
    """
    wrapper_body = format_wrapper_body(spec, _php_exec_line(spec, p))
    return f"""      cat > $out/bin/{spec.pname} << 'WRAPPER'
{wrapper_body}
WRAPPER
      sed -i "s|APPDIR|$out/app|g" $out/bin/{spec.pname}
      sed -i "s|PHPBIN|${{php}}/bin|g" $out/bin/{spec.pname}
      chmod +x $out/bin/{spec.pname}"""


def _runtime_env(spec: AppSpec, p: PhpAppPayload) -> dict[str, str]:
    """Runtime env, with the built-in server's worker count filled in.

    PHP's built-in server handles one request at a time, so an app that fetches
    its own URL deadlocks against its only worker. The platform sets this for
    Procfile apps by matching `php -S` in the worker command, which a Nix app
    never looks like: its command is an opaque wrapper path in the store. The
    template that *chose* the built-in server is what knows it needs workers.
    """
    runtime_env = dict(spec.runtime_env)
    if p.serve_mode in _CONCURRENT_SERVE_MODES:
        runtime_env.setdefault("PHP_CLI_SERVER_WORKERS", PHP_BUILTIN_SERVER_WORKERS)
    return runtime_env


def _runtime_json_section(spec: AppSpec, p: PhpAppPayload) -> str:
    """The heredoc that writes $out/hop3/runtime.json.

    `writable_tree` names the store path Hop3 must copy into the app's own
    directory BEFORE anything runs there. It is declared here rather than done
    in the wrapper because the wrapper runs when the app starts, which is after
    `[run] before-run` — so a bootstrap script found a directory holding the
    recipe and none of the application. Matomo's installer died on `Failed
    opening required core/bootstrap.php` for exactly that reason, on a build
    that was otherwise fine.

    `$out/app`, not `$out`: the application lives in that subdirectory, while
    `$out` also holds the generated wrapper and hop3/runtime.json. Copying
    `$out` puts the app one level down from where it expects to be, and drops
    build metadata into the app's directory where the next deploy trips over it.
    """
    return format_runtime_json(
        spec,
        f"$out/bin/{spec.pname}",
        runtime_env=_runtime_env(spec, p),
        writable_tree="$out/app" if p.needs_writable_dir else "",
        php_fpm=_php_fpm_entry(p),
    )


def _php_fpm_entry(p: PhpAppPayload) -> dict[str, str] | None:
    """
    runtime.json's request for a php-fpm pool, or None for another serve mode.

    The pool, its port and the proxy's FastCGI location are Hop3's, as for a
    native PHP app; the expression names only what it built. Without a
    `web-root`, Hop3 detects the front-controller directory (`public/`,
    `htdocs/`...) the way the PHP toolchain does.
    """
    if p.serve_mode != "fpm":
        return None
    entry = {"binary": "${php}/bin/php-fpm", "tree": "$out/app"}
    if p.web_root:
        entry["document_root"] = p.web_root
    return entry


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
    if p.serve_mode == "fpm":
        # php-fpm is the web worker, so the wrapper serves nothing: it runs
        # the before-run phase, and otherwise is the app's own PHP CLI.
        return 'PHPBIN/php "$@"'
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
    if spec.exec_target is None:
        msg = "serve_mode='custom' requires exec_target"
        raise ValueError(msg)
    return spec.exec_target
