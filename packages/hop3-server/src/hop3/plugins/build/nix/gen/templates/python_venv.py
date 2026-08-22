# Copyright (c) 2025-2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

# ruff:file-ignore[raise-vanilla-args, raw-string-in-exception]


"""
python-venv template.

For Python applications that are not in nixpkgs. Builds **hermetically**, in
two phases:

1. A *fixed-output derivation* downloads every wheel/sdist named by a
   hash-pinned lockfile. This is the only step allowed to touch the network,
   and its output is content-addressed, so the set of dependencies is fixed by
   a hash exactly as ``buildGoModule``'s ``vendorHash`` fixes a Go module set.
2. The application build then runs **inside the sandbox with no network**,
   installing from the vendored directory (``--no-index``).

This is what makes the result reproducible: an unpinned ``pip install <name>``
resolves differently from one week to the next, so it can be neither verified
nor rebuilt. The lockfile must carry a hash per requirement (generate with
``uv export --format requirements-txt`` or ``pip-compile --generate-hashes``).

Example apps: Isso, Bugsink.
"""

from __future__ import annotations

from hop3.plugins.build.nix.gen.spec import AppSpec, PythonVenvPayload
from hop3.plugins.build.nix.gen.templates.base import (
    ReproTier,
    format_nix_env_attrs,
    format_paths_json,
    format_runtime_env_json,
    format_wrapper_body,
    pinned_nixpkgs_header,
)

_NO_LOCKFILE = (
    "python-venv requires a hash-pinned lockfile: set `pip-requirements` in "
    '[nix] (e.g. "requirements.txt"). Generate it with '
    "`uv export --format requirements-txt` or `pip-compile --generate-hashes`. "
    "Bare `pip-packages` names are unpinned and unhashed, so the build cannot "
    "be reproduced or run offline."
)

_NO_DEPS_HASH = (
    "python-venv requires `pip-deps-hash` in [nix] — the sha256 of the vendored "
    "dependency set. Build once with "
    '`pip-deps-hash = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="` '
    "and read the `got:` hash Nix reports."
)


class PythonVenvTemplate:
    name = "python-venv"
    tier = ReproTier.SOURCE

    def generate(self, spec: AppSpec) -> str:
        p = spec.payload_as(PythonVenvPayload)
        if not p.requirements:
            raise ValueError(_NO_LOCKFILE)
        if not p.deps_hash:
            raise ValueError(_NO_DEPS_HASH)
        if spec.exec_target is None:
            raise ValueError("python-venv requires exec_target (e.g., 'isso')")
        runtime_package = spec.runtime_package or "python3"

        # `pip download` picks a wheel matching the build machine, so any
        # package shipping per-architecture wheels makes the vendored set — and
        # therefore `deps_hash` — machine-specific. Naming those packages here
        # fetches their sdist instead, which is the same bytes everywhere, so
        # one recorded hash is correct on every architecture rather than on the
        # one that happened to record it.
        no_binary = ",".join(p.source_packages) if p.source_packages else ""
        no_binary_flag = f" --no-binary {no_binary}" if no_binary else ""
        # Libraries go in buildInputs, not nativeBuildInputs: the split is what
        # a cross-build keys off, and reaching a new architecture is the whole
        # point of vendoring source. pkg-config is a build-time tool, and any
        # extension linking a system library wants it, so it comes along
        # whenever there is source to compile.
        build_inputs = (
            f"\n    buildInputs = [{''.join(f' pkgs.{name}' for name in p.build_inputs)} ];"
            if p.build_inputs
            else ""
        )
        native_extra = " pkgs.pkg-config" if p.source_packages else ""
        # A Rust extension's sdist build fetches its crates from crates.io, which
        # the offline app build cannot do. cargo vendors them in the fetch step
        # instead, so they arrive with the wheels under one hash.
        cargo_tools = " pkgs.cargo pkgs.rustc" if p.source_packages else ""
        build_requires = " ".join(f'"{req}"' for req in p.build_requires)
        # Each committed lockfile enters the derivation as a store path, paired
        # with where it belongs inside the extracted sources.
        cargo_locks = "".join(
            f' "${{./{src}}}" "{dest}"' for src, dest in p.cargo_locks
        )
        build_requires_step = (
            f"""
      # PEP 517 backends for the sources vendored above. Pinned and --no-deps:
      # resolving them would let a new release of a build tool change these
      # bytes, and the recorded hash with them.
      pip download --no-deps{no_binary_flag} --dest $out {build_requires}"""
            if p.build_requires
            else ""
        )

        exec_args = " " + " ".join(spec.exec_args) if spec.exec_args else ""
        exec_line = f"VENVBIN/{spec.exec_target}{exec_args}"
        wrapper_body = format_wrapper_body(spec, exec_line)

        runtime_env_json = format_runtime_env_json(spec.runtime_env)
        nix_env_attrs = format_nix_env_attrs(spec.runtime_env)
        paths_json = format_paths_json(spec.extra_paths)

        return f"""# hop3.nix - Nix expression for {spec.pname}
#
# GENERATED from template 'python-venv' by hop3-nix-gen.
# Run 'hop3 nix eject {spec.pname}' to materialize for customization.

{pinned_nixpkgs_header(spec.nixpkgs_rev, spec.nixpkgs_sha256)}

let
  version = "{spec.version}";
  python = pkgs.{runtime_package};
  requirementsFile = ./{p.requirements};

  # Phase 1: vendor the dependency set. This fixed-output derivation is the
  # ONLY step with network access; its content hash pins exactly which wheels
  # may enter the build.
  pythonDeps = pkgs.stdenv.mkDerivation {{
    pname = "{spec.pname}-python-deps";
    inherit version;

    dontUnpack = true;
    dontBuild = true;

    # The same toolchain as the app build below. Vendoring a source
    # distribution makes this derivation compile too: pip builds each sdist's
    # metadata, and a PEP 517 backend dependency gets built to do it (misaka's
    # pulls in cffi, which needs libffi). Without these the download fails on
    # `fatal error: ffi.h: No such file or directory` — in the *download* step,
    # which reads as the last place a compiler error could come from.
    nativeBuildInputs = [ python python.pkgs.pip{native_extra}{cargo_tools} ];{build_inputs}

    installPhase = ''
      # cargo needs a writable CARGO_HOME, and the sandbox points HOME at
      # /homeless-shelter, so the default is unwritable. Set before the fetch,
      # not just before the vendor step below: a source distribution whose PEP
      # 517 backend is itself written in Rust (maturin) compiles during
      # `pip download`, and hits this first — reported as a permission error on
      # a path no recipe mentions, from inside a pip subprocess.
      export CARGO_HOME=$TMPDIR/cargo-fetch
      mkdir -p $CARGO_HOME

      mkdir -p $out
      # --no-deps: the lockfile is already the full resolved closure, so this
      # is a fetch of exactly what was pinned rather than a re-resolution.
      pip download --require-hashes --no-deps{no_binary_flag} \\
        --dest $out --requirement ${{requirementsFile}}{build_requires_step}

      # Vendor the Rust crates of any source distribution that carries a
      # Cargo.lock. Done here because this is the step allowed to use the
      # network; the app build below is sandboxed and offline, and a Rust
      # extension would otherwise die trying to reach crates.io.
      #
      # A set with no Rust in it produces no directory and therefore no change
      # to this derivation's hash, so recipes without one are unaffected.
      ${{python}}/bin/python - "$out"{cargo_locks} << 'CARGOVENDOR'
import shutil, subprocess, sys, tarfile, tempfile, zipfile
from pathlib import Path

out = Path(sys.argv[1])
work = Path(tempfile.mkdtemp())
for sdist in sorted(out.glob("*.tar.gz")):
    with tarfile.open(sdist) as archive:
        archive.extractall(work, filter="data")
for sdist in sorted(out.glob("*.zip")):
    with zipfile.ZipFile(sdist) as archive:
        archive.extractall(work)

# Some sdists bury their Rust sources in a nested archive rather than shipping
# them as files: symbolic ships rustsrc.zip, the milksnake convention. Unpack
# one level so those manifests are visible to the scan below.
for nested in sorted(work.glob("*/*.zip")):
    with zipfile.ZipFile(nested) as archive:
        archive.extractall(nested.parent)

# Drop in the lockfiles upstream does not provide, so resolution is pinned.
locks = sys.argv[2:]
for store_path, destination in zip(locks[::2], locks[1::2]):
    target = work / destination
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(store_path, target)

# Sorted, so the vendored tree does not depend on filesystem order.
manifests = sorted(lock.parent / "Cargo.toml" for lock in work.rglob("Cargo.lock"))
if manifests:
    cmd = ["cargo", "vendor", "--manifest-path", str(manifests[0])]
    for extra in manifests[1:]:
        cmd += ["--sync", str(extra)]
    cmd.append(str(out / "cargo-vendor"))
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
CARGOVENDOR
    '';

    # Nothing in a downloaded dependency set should be "fixed up". stdenv's
    # fixupPhase rewrites `#!/bin/bash` to a store path, and it reaches inside
    # vendored crates — autocfg's test script, wasi's CI scripts. That breaks
    # this derivation three ways: a fixed-output derivation may not reference
    # store paths at all; the reference is machine-specific, which is precisely
    # the non-determinism being removed here; and editing a crate's files
    # invalidates the .cargo-checksum.json cargo verifies at build time.
    dontFixup = true;

    outputHashMode = "recursive";
    outputHashAlgo = "sha256";
    outputHash = "{p.deps_hash}";
  }};

  app = pkgs.stdenv.mkDerivation {{
    # No __noChroot: dependencies are vendored above, so this build runs
    # sandboxed and offline.
    pname = "{spec.pname}";
    inherit version;
    meta.description = "{spec.description}";

    dontUnpack = true;
    dontBuild = true;

    nativeBuildInputs = [ python python.pkgs.pip{native_extra}{cargo_tools} ];{build_inputs}

    installPhase = ''
      mkdir -p $out/app $out/bin $out/venv $out/hop3

      # Point cargo at the crates vendored above and forbid it the network, so
      # a Rust extension compiles from source inside the sandbox. Only written
      # when there are crates: `cargo vendor` produced nothing otherwise.
      if [ -d ${{pythonDeps}}/cargo-vendor ]; then
        export CARGO_HOME=$TMPDIR/cargo-home
        export CARGO_NET_OFFLINE=true
        mkdir -p $CARGO_HOME
        # Quoted delimiter: the body is literal TOML. Unquoted, the shell
        # expands it, and the backticks in the comment below became a command
        # substitution the build tried to run.
        cat > $CARGO_HOME/config.toml << 'CARGOCFG'
[source.crates-io]
replace-with = "vendored-sources"

[source.vendored-sources]
directory = "${{pythonDeps}}/cargo-vendor"

# cargo caps lints for crates it pulls from a registry, on the principle that
# third-party code must not fail your build over a lint you cannot fix. Every
# crate here is third-party too — it just arrives as a workspace path inside a
# Python sdist, which is the one case cargo's rule misses. Without this, a
# newer rustc turning a lint deny-by-default breaks an app whose sources
# nobody touched: symbolic 8.7.2 stops compiling at rustc 1.87 over
# `dangerous_implicit_autorefs`.
[build]
rustflags = ["--cap-lints", "allow"]
CARGOCFG
      fi

      # Create the virtualenv and install offline from the vendored wheels.
      ${{python}}/bin/python -m venv $out/venv
      $out/venv/bin/pip install \\
        --no-index --find-links ${{pythonDeps}} \\
        --require-hashes --requirement ${{requirementsFile}}

      # Reproducibility: a C extension built from an sdist embeds pip's random
      # build directory (/build/pip-install-XXXX/...) as the DWARF comp_dir in
      # its .debug_* sections, so two builds of the same source differ byte-for-
      # byte. Strip debug info from ONLY those .so — the ones that actually carry
      # the build path — then rewrite the wheel RECORD hashes to match (else
      # RECORD keeps the pre-strip hash and reintroduces the non-determinism).
      # Prebuilt-wheel extensions are already reproducible and must be left
      # byte-for-byte untouched: re-stripping foreign native libs (Rust cdylibs,
      # mypyc modules) is needless risk, so we skip any .so without the marker.
      find $out/venv -name '*.so' -type f | while read -r so; do
        if grep -qa '/build/pip-' "$so"; then
          ${{pkgs.binutils}}/bin/strip --strip-debug "$so"
        fi
      done
      $out/venv/bin/python - "$out/venv" << 'RECORDFIX'
import base64, hashlib, sys
from pathlib import Path
venv = Path(sys.argv[1])
for record in venv.rglob("RECORD"):
    site = record.parent.parent
    out, changed = [], False
    for line in record.read_text().splitlines():
        cols = line.rsplit(",", 2)
        target = site / cols[0] if len(cols) == 3 else None
        if target and target.suffix == ".so" and target.is_file():
            data = target.read_bytes()
            digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest())
            new = f"{{cols[0]}},sha256={{digest.rstrip(b'=').decode()}},{{len(data)}}"
            changed = changed or new != line
            line = new
        out.append(line)
    if changed:
        record.write_text("\\n".join(out) + "\\n")
RECORDFIX

      cat > $out/bin/{spec.pname} << 'WRAPPER'
{wrapper_body}
WRAPPER
      sed -i "s|VENVBIN|$out/venv/bin|g" $out/bin/{spec.pname}
      chmod +x $out/bin/{spec.pname}

      cat > $out/hop3/runtime.json << EOF
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
EOF
    '';
  }};

in
{{
  package = app;

  env = {{{nix_env_attrs}}};
}}
"""
