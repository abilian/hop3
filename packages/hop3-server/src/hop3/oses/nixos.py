# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Setup script for NixOS.

Note: NixOS uses a completely different package management paradigm
based on declarative configuration. This module provides a basic
structure but a full implementation would require a NixOS
configuration.nix file instead of imperative package installation.
"""

from __future__ import annotations

from hop3.oses.helpers import Platform

# Package list for NixOS (as they would appear in configuration.nix)
# These are Nix package names, not Debian/Ubuntu package names
PACKAGES = [
    "bc",
    "git",
    "sudo",
    "cron",
    "gcc",
    "gnumake",
    "pcre",
    "zlib",
    # Python
    "python3",
    "python3Packages.pip",
    "python3Packages.click",
    "python3Packages.virtualenv",
    "python3Packages.setuptools",
    # Nginx
    "nginx",
    # uwsgi
    "uwsgi",
    # Let's Encrypt
    "certbot",
    # For builders
    # - Ruby
    "ruby",
    "bundler",
    # - Nodejs
    "nodejs",
    "yarn",
    # - Go
    "go",
    # - Clojure
    "clojure",
    "leiningen",
    # Addons
    "postgresql",
    # Extra libs
    "cairo",
    "pango",
]

HOP3_USER = "hop3"
SSH_USER = "root"
HOME_DIR = f"/home/{HOP3_USER}"
VENV = f"{HOME_DIR}/venv"
HOP_SCRIPT = f"{VENV}/bin/hop-server"


class NixOS(Platform):
    """NixOS platform implementation.

    Note: This is a stub implementation. A proper NixOS setup would
    require generating a configuration.nix file with appropriate
    services and packages declared.
    """

    def ensure_packages(self, name, packages, *, update=True) -> None:
        """Ensure packages are installed via Nix.

        Note: In a real NixOS implementation, this would need to:
        1. Generate a configuration.nix with the packages
        2. Run nixos-rebuild switch

        This stub is provided for interface compatibility only.
        """
        msg = "NixOS package installation requires configuration.nix modification"
        raise NotImplementedError(msg)


platform = NixOS()


def setup_server() -> None:
    """Configures the server for NixOS.

    Note: This is a placeholder. A real implementation would require
    generating a NixOS configuration.nix file with appropriate settings.

    For NixOS, you should use a declarative configuration like:

    ```nix
    { config, pkgs, ... }:
    {
      users.users.hop3 = {
        isNormalUser = true;
        home = "/home/hop3";
        shell = pkgs.bash;
        extraGroups = [ "nginx" ];
      };

      environment.systemPackages = with pkgs; [
        # ... packages from PACKAGES list above
      ];

      services.nginx.enable = true;
      services.postgresql.enable = true;
    }
    ```
    """
    msg = (
        "NixOS requires declarative configuration via configuration.nix. "
        "See module documentation for an example configuration."
    )
    raise NotImplementedError(msg)
