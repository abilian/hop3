# NixOS module for Hop3 PaaS server
{ config, lib, pkgs, ... }:

with lib;

let
  cfg = config.services.hop3;

  # Get hop3-server package from the flake overlay
  hop3Pkgs = pkgs;
in
{
  options.services.hop3 = {
    enable = mkEnableOption "Hop3 PaaS server";

    package = mkOption {
      type = types.package;
      default = hop3Pkgs.python312Packages.hop3-server;
      defaultText = literalExpression "pkgs.python312Packages.hop3-server";
      description = "The hop3-server package to use.";
    };

    user = mkOption {
      type = types.str;
      default = "hop3";
      description = "User account under which Hop3 runs.";
    };

    group = mkOption {
      type = types.str;
      default = "hop3";
      description = "Group under which Hop3 runs.";
    };

    homeDir = mkOption {
      type = types.path;
      default = "/home/hop3";
      description = "Home directory for Hop3 data and app deployments.";
    };

    host = mkOption {
      type = types.str;
      default = "127.0.0.1";
      description = "Host address to bind the API server.";
    };

    port = mkOption {
      type = types.port;
      default = 8000;
      description = "Port for Hop3 API server.";
    };

    secretKeyFile = mkOption {
      type = types.nullOr types.path;
      default = null;
      description = ''
        Path to a file containing the JWT secret key.
        If not set, a random key will be generated on first start.
      '';
    };

    database = {
      type = mkOption {
        type = types.enum [ "sqlite" "postgresql" ];
        default = "sqlite";
        description = "Database backend to use.";
      };

      createLocally = mkOption {
        type = types.bool;
        default = true;
        description = ''
          Whether to create a local PostgreSQL database.
          Only applies when database.type is "postgresql".
        '';
      };

      name = mkOption {
        type = types.str;
        default = "hop3";
        description = "Database name (for PostgreSQL).";
      };
    };

    nginx = {
      enable = mkOption {
        type = types.bool;
        default = false;
        description = "Whether to configure Nginx as a reverse proxy.";
      };

      virtualHost = mkOption {
        type = types.str;
        default = "hop3.localhost";
        description = "Virtual host name for Nginx.";
      };

      enableSSL = mkOption {
        type = types.bool;
        default = false;
        description = "Whether to enable ACME SSL certificates.";
      };
    };

    openFirewall = mkOption {
      type = types.bool;
      default = false;
      description = "Whether to open firewall ports for HTTP/HTTPS.";
    };
  };

  config = mkIf cfg.enable {
    # Create user and group
    users.users.${cfg.user} = {
      isSystemUser = true;
      group = cfg.group;
      home = cfg.homeDir;
      createHome = true;
      shell = pkgs.bash;
      description = "Hop3 PaaS service user";
    };

    users.groups.${cfg.group} = { };

    # Create home directory structure
    systemd.tmpfiles.rules = [
      "d ${cfg.homeDir} 0750 ${cfg.user} ${cfg.group} -"
      "d ${cfg.homeDir}/apps 0750 ${cfg.user} ${cfg.group} -"
      "d ${cfg.homeDir}/nginx 0750 ${cfg.user} ${cfg.group} -"
      "d ${cfg.homeDir}/uwsgi-available 0750 ${cfg.user} ${cfg.group} -"
      "d ${cfg.homeDir}/uwsgi-enabled 0750 ${cfg.user} ${cfg.group} -"
      "d ${cfg.homeDir}/logs 0750 ${cfg.user} ${cfg.group} -"
    ];

    # PostgreSQL setup (if enabled)
    services.postgresql = mkIf (cfg.database.type == "postgresql" && cfg.database.createLocally) {
      enable = true;
      ensureDatabases = [ cfg.database.name ];
      ensureUsers = [
        {
          name = cfg.user;
          ensureDBOwnership = true;
        }
      ];
    };

    # Main systemd service
    systemd.services.hop3-server = {
      description = "Hop3 PaaS Server";
      after = [ "network.target" ]
        ++ optionals (cfg.database.type == "postgresql") [ "postgresql.service" ];
      wants = optionals (cfg.database.type == "postgresql") [ "postgresql.service" ];
      wantedBy = [ "multi-user.target" ];

      environment = {
        HOP3_HOME = cfg.homeDir;
        HOP3_DATABASE_URL = if cfg.database.type == "postgresql"
          then "postgresql:///${cfg.database.name}?host=/run/postgresql"
          else "sqlite:///${cfg.homeDir}/hop3.db";
      };

      serviceConfig = {
        Type = "simple";
        User = cfg.user;
        Group = cfg.group;
        WorkingDirectory = cfg.homeDir;

        ExecStart = ''
          ${cfg.package}/bin/hop3-server serve \
            --host ${cfg.host} \
            --port ${toString cfg.port}
        '';

        Restart = "on-failure";
        RestartSec = 5;

        # Security hardening
        NoNewPrivileges = true;
        ProtectSystem = "strict";
        ProtectHome = "read-only";
        ReadWritePaths = [ cfg.homeDir ];
        PrivateTmp = true;
        PrivateDevices = true;
        ProtectKernelTunables = true;
        ProtectKernelModules = true;
        ProtectControlGroups = true;
        RestrictSUIDSGID = true;
        RestrictNamespaces = true;

        # Load secret key from file if specified
        LoadCredential = mkIf (cfg.secretKeyFile != null) [
          "secret-key:${cfg.secretKeyFile}"
        ];
      };

      # Set secret key from credential if provided
      preStart = mkIf (cfg.secretKeyFile != null) ''
        export HOP3_SECRET_KEY=$(cat $CREDENTIALS_DIRECTORY/secret-key)
      '';
    };

    # Nginx reverse proxy (if enabled)
    services.nginx = mkIf cfg.nginx.enable {
      enable = true;

      virtualHosts.${cfg.nginx.virtualHost} = {
        forceSSL = cfg.nginx.enableSSL;
        enableACME = cfg.nginx.enableSSL;

        locations."/" = {
          proxyPass = "http://${cfg.host}:${toString cfg.port}";
          proxyWebsockets = true;
          extraConfig = ''
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
          '';
        };
      };
    };

    # Firewall rules (if enabled)
    networking.firewall = mkIf cfg.openFirewall {
      allowedTCPPorts = [ 80 ] ++ optionals cfg.nginx.enableSSL [ 443 ];
    };

    # ACME configuration for Let's Encrypt
    security.acme = mkIf (cfg.nginx.enable && cfg.nginx.enableSSL) {
      acceptTerms = true;
      defaults.email = mkDefault "admin@${cfg.nginx.virtualHost}";
    };
  };
}
