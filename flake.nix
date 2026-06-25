{
  description = "Hop3 - Simple PaaS for single-server deployments";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs {
          inherit system;
          overlays = [ self.overlays.default ];
        };

        python = pkgs.python312;

        # Common packages for development
        devPackages = [
          (python.withPackages (ps: with ps; [
            pip
            setuptools
            wheel
            build
            hatchling
          ]))
          pkgs.uv

          # Development tools
          pkgs.git
          pkgs.gnumake

          # Database clients
          pkgs.postgresql
          pkgs.sqlite

          # Build tools
          pkgs.gcc
          pkgs.openssl
          pkgs.pcre2
          pkgs.libxcrypt
        ];

        # FHS environment for running uv with dynamically linked binaries
        fhsEnv = pkgs.buildFHSEnv {
          name = "hop3-fhs";
          targetPkgs = pkgs: devPackages ++ [
            pkgs.stdenv.cc.cc.lib
            pkgs.zlib
          ];
          runScript = "bash";
        };

      in
      {
        # Development shell (requires nix-ld on NixOS)
        devShells.default = pkgs.mkShell {
          name = "hop3-dev";

          buildInputs = devPackages ++ [
            pkgs.stdenv.cc.cc.lib
            pkgs.zlib
          ];

          # Set up environment for uv to work with dynamically linked binaries
          # Requires: programs.nix-ld.enable = true; in NixOS config
          NIX_LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [
            pkgs.stdenv.cc.cc.lib
            pkgs.zlib
            pkgs.openssl
          ];
          NIX_LD = pkgs.lib.fileContents "${pkgs.stdenv.cc}/nix-support/dynamic-linker";

          shellHook = ''
            echo "Hop3 development shell"
            echo "Python: $(python --version)"
            echo "uv: $(uv --version)"
            echo ""
            echo "Run 'uv sync' to install dependencies"
            echo ""
            echo "If uv fails with 'dynamically linked executable' errors, either:"
            echo "  1. Enable nix-ld: programs.nix-ld.enable = true;"
            echo "  2. Use FHS shell: nix develop .#fhs"
          '';
        };

        # FHS-compatible shell (works without nix-ld)
        devShells.fhs = fhsEnv.env;

        # Packages
        packages = {
          hop3-cli = python.pkgs.hop3-cli;
          hop3-server = python.pkgs.hop3-server;
          default = python.pkgs.hop3-cli;
        };

        # Apps
        apps = {
          hop3 = flake-utils.lib.mkApp {
            drv = python.pkgs.hop3-cli;
            name = "hop3";
          };
          hop3-server = flake-utils.lib.mkApp {
            drv = python.pkgs.hop3-server;
            name = "hop3-server";
          };
          default = self.apps.${system}.hop3;
        };
      }
    ) // {
      # Overlay with missing Python packages
      overlays.default = final: prev: {
        python312 = prev.python312.override {
          packageOverrides = python-final: python-prev: {
            # jsonrpcclient - Required by hop3-cli (wheel only, no sdist on PyPI)
            jsonrpcclient = python-final.buildPythonPackage rec {
              pname = "jsonrpcclient";
              version = "4.0.3";
              format = "wheel";

              src = prev.fetchurl {
                url = "https://files.pythonhosted.org/packages/py3/j/jsonrpcclient/jsonrpcclient-4.0.3-py3-none-any.whl";
                hash = "sha256-PLueJ+G+KYIb7PE16hgxRKg2IVQicn4f/lBWpJpnDw0=";
              };

              doCheck = false;

              meta = {
                description = "Send JSON-RPC requests in Python";
                homepage = "https://github.com/explodinglabs/jsonrpcclient";
              };
            };

            # dishka - Required by hop3-server
            dishka = python-final.buildPythonPackage rec {
              pname = "dishka";
              version = "1.4.2";
              format = "pyproject";

              src = python-prev.fetchPypi {
                inherit pname version;
                hash = "sha256-/h57LQ30MGs5ZQz0wFSFqnnOH8MVB9H3MwDew8ZLI5c=";
              };

              nativeBuildInputs = [
                python-prev.setuptools
                python-prev.wheel
              ];

              propagatedBuildInputs = [ python-prev.typing-extensions ];

              doCheck = false;

              meta = {
                description = "Dependency injection container for Python";
                homepage = "https://github.com/reagento/dishka";
              };
            };

            # advanced-alchemy - Required by hop3-server
            advanced-alchemy = python-final.buildPythonPackage rec {
              pname = "advanced_alchemy";
              version = "0.22.1";
              format = "pyproject";

              src = python-prev.fetchPypi {
                inherit pname version;
                hash = "sha256-IPZT79QnHjQIxBkJRemS06Rzni4D0FFvpGRAIusidgI=";
              };

              nativeBuildInputs = [ python-prev.hatchling ];

              propagatedBuildInputs = [
                python-prev.sqlalchemy
                python-prev.alembic
                python-prev.typing-extensions
              ];

              doCheck = false;

              meta = {
                description = "Ready-to-go SQLAlchemy concoctions";
                homepage = "https://github.com/litestar-org/advanced-alchemy";
              };
            };

            # hop3-cli package
            hop3-cli = python-final.buildPythonPackage {
              pname = "hop3-cli";
              version = "0.6.1";
              format = "pyproject";

              src = ./packages/hop3-cli;

              nativeBuildInputs = [
                python-prev.hatchling
                python-prev.hatch-vcs
              ];

              # Patch pyproject.toml to use hatchling instead of uv_build
              # Also relax paramiko version constraint (nixpkgs has 4.x)
              postPatch = ''
                substituteInPlace pyproject.toml \
                  --replace-fail 'requires = ["uv-build>=0.8.4,<0.9.0"]' 'requires = ["hatchling"]' \
                  --replace-fail 'build-backend = "uv_build"' 'build-backend = "hatchling.build"' \
                  --replace-fail '"paramiko>=2.11.0,<3.0.0"' '"paramiko>=2.11.0"'
                echo '[tool.hatch.build.targets.wheel]' >> pyproject.toml
                echo 'packages = ["src/hop3_cli"]' >> pyproject.toml
              '';

              propagatedBuildInputs = [
                python-prev.toml
                python-prev.tomlkit  # comment-preserving TOML round-trip for hop3.toml/context edits
                python-final.jsonrpcclient
                python-prev.requests
                python-prev.tabulate
                python-prev.rich
                python-prev.sshtunnel
                python-prev.paramiko
                python-prev.loguru
                python-prev.pathspec
                python-prev.platformdirs
              ];

              doCheck = false;

              meta = {
                description = "CLI client for Hop3 PaaS";
                homepage = "https://hop3.cloud";
              };
            };

            # hop3-server package
            hop3-server = python-final.buildPythonPackage {
              pname = "hop3-server";
              version = "0.6.1";
              format = "pyproject";

              src = ./packages/hop3-server;

              nativeBuildInputs = [
                python-prev.hatchling
                python-prev.hatch-vcs
              ];

              # Patch pyproject.toml to use hatchling instead of uv_build
              # Also replace/remove deps not available in nixpkgs
              postPatch = ''
                substituteInPlace pyproject.toml \
                  --replace-fail 'requires = ["uv-build>=0.8.4,<0.9.0"]' 'requires = ["hatchling"]' \
                  --replace-fail 'build-backend = "uv_build"' 'build-backend = "hatchling.build"' \
                  --replace-fail '"granian[reload]>=2.2.0"' '"uvicorn>=0.30.0"' \
                  --replace-fail '"psycopg2-binary>=2.9.10"' '"psycopg2>=2.9.10"' \
                  --replace-fail '"pydantic>=2.12.5"' '"pydantic>=2.12.0"' \
                  --replace-fail '"litestar[standard]>=2.22.0"' '"litestar[standard]>=2.21.0"'

                # Remove deps not in nixpkgs (these are optional at runtime anyway)
                sed -i '/"cyclonedx-bom/d' pyproject.toml
                sed -i '/"mysql-connector-python/d' pyproject.toml
                sed -i '/"uwsgi/d' pyproject.toml

                # Replace uv-specific build backend config with hatchling config
                sed -i '/\[tool.uv.build-backend\]/,/^$/d' pyproject.toml
                echo '[tool.hatch.build.targets.wheel]' >> pyproject.toml
                echo 'packages = ["src/hop3"]' >> pyproject.toml
              '';

              propagatedBuildInputs = [
                # Web framework
                python-prev.litestar
                python-prev.attrs
                python-prev.jinja2
                python-prev.itsdangerous
                # Plugins and DI
                python-prev.pluggy
                python-final.dishka
                # Database
                python-prev.sqlalchemy
                python-final.advanced-alchemy
                python-prev.alembic
                # Misc
                python-prev.termcolor
                python-prev.markdown
                python-prev.nh3  # HTML sanitizer for untrusted catalog readme (ADR 049)
                python-prev.toml
                python-prev.devtools
                # Security
                python-prev.pyjwt
                python-prev.bcrypt
                python-prev.cryptography
                # ASGI server (use uvicorn instead of granian to avoid OOM during build)
                python-prev.uvicorn
                # PostgreSQL
                python-prev.psycopg2
                # Redis
                python-prev.redis
                # Validation
                python-prev.pydantic
                # Config
                python-prev.pyyaml
                python-prev.python-multipart
                # Domain health monitoring (WHOIS registration expiry)
                python-prev.python-whois
                python-prev.anyio
                python-prev.sniffio
              ];

              doCheck = false;

              meta = {
                description = "Hop3 PaaS server";
                homepage = "https://hop3.cloud";
              };
            };
          };
        };
      };

      # NixOS module for Hop3 server deployment
      nixosModules.default = { config, lib, pkgs, ... }: {
        imports = [ ./nix/modules/hop3.nix ];

        # Apply overlay so hop3 packages are available
        nixpkgs.overlays = [ self.overlays.default ];
      };

      # Also export the module directly for use without overlay injection
      nixosModules.hop3 = ./nix/modules/hop3.nix;
    };
}
