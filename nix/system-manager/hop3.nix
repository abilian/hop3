# System-manager configuration for Hop3 on Ubuntu
# See: https://github.com/numtide/system-manager
#
# Usage:
#   1. Install system-manager: nix profile install github:numtide/system-manager
#   2. Initialize: system-manager init
#   3. Copy this file to ~/.config/system-manager/
#   4. Apply: sudo system-manager switch
#
{ lib, pkgs, config, ... }:

let
  # Import hop3 flake for packages
  hop3Flake = builtins.getFlake (toString ../..);
  hop3Pkgs = hop3Flake.packages.${pkgs.system};

  # Configuration
  cfg = {
    user = "hop3";
    group = "hop3";
    homeDir = "/home/hop3";
    host = "127.0.0.1";
    port = 8000;
  };
in
{
  config = {
    nixpkgs.hostPlatform = pkgs.system;

    # Create hop3 directories
    systemd.tmpfiles.rules = [
      "d ${cfg.homeDir} 0750 ${cfg.user} ${cfg.group} -"
      "d ${cfg.homeDir}/apps 0750 ${cfg.user} ${cfg.group} -"
      "d ${cfg.homeDir}/nginx 0750 ${cfg.user} ${cfg.group} -"
      "d ${cfg.homeDir}/uwsgi-available 0750 ${cfg.user} ${cfg.group} -"
      "d ${cfg.homeDir}/uwsgi-enabled 0750 ${cfg.user} ${cfg.group} -"
      "d ${cfg.homeDir}/logs 0750 ${cfg.user} ${cfg.group} -"
    ];

    # Hop3 server systemd service
    systemd.services.hop3-server = {
      description = "Hop3 PaaS Server";
      after = [ "network.target" ];
      wantedBy = [ "multi-user.target" ];

      serviceConfig = {
        Type = "simple";
        User = cfg.user;
        Group = cfg.group;
        WorkingDirectory = cfg.homeDir;

        ExecStart = "${hop3Pkgs.hop3-server}/bin/hop3-server serve --host ${cfg.host} --port ${toString cfg.port}";

        Restart = "on-failure";
        RestartSec = "5";

        # Environment
        Environment = [
          "HOP3_HOME=${cfg.homeDir}"
          "HOP3_DATABASE_URL=sqlite:///${cfg.homeDir}/hop3.db"
        ];

        # Security hardening
        NoNewPrivileges = "true";
        ProtectSystem = "strict";
        ProtectHome = "read-only";
        ReadWritePaths = cfg.homeDir;
        PrivateTmp = "true";
        PrivateDevices = "true";
        ProtectKernelTunables = "true";
        ProtectKernelModules = "true";
        ProtectControlGroups = "true";
      };
    };

    # Optional: Add hop3-cli to system packages
    environment.systemPackages = [
      hop3Pkgs.hop3-cli
    ];
  };
}
