# hop3.nix - Nix expression for Kanboard deployment
#
# Downloads Kanboard and serves with PHP built-in server.
# Kanban project management requiring MySQL.

{ pkgs ? import (fetchTarball {
  url = "https://github.com/NixOS/nixpkgs/archive/50ab793786d9de88ee30ec4e4c24fb4236fc2674.tar.gz";
  sha256 = "1s2gr5rcyqvpr58vxdcb095mdhblij9bfzaximrva2243aal3dgx";
}) {} }:

let
  version = "1.2.37";

  php = pkgs.php82.withExtensions ({ enabled, all }: enabled ++ [
    all.mysqli
    all.pdo_mysql
    all.pdo_sqlite
    all.gd
    all.mbstring
    all.xml
    all.curl
    all.zip
    all.ldap
  ]);

  kanboardSrc = pkgs.fetchurl {
    url = "https://github.com/kanboard/kanboard/archive/refs/tags/v${version}.tar.gz";
    sha256 = "TVOLDXS3rX4n4cMQiztpkwmkYAbkTDhagD2+wZ+Erv8=";
  };

  app = pkgs.stdenv.mkDerivation {
    pname = "kanboard";
    inherit version;
    meta = {
      description = "Kanban project management software";
    };

    src = kanboardSrc;

    dontBuild = true;

    unpackPhase = ''
      tar xzf $src --strip-components=1
    '';

    installPhase = ''
      mkdir -p $out/app $out/bin

      cp -r . $out/app/
      mkdir -p $out/app/data $out/app/plugins

      cat > $out/bin/kanboard << 'WRAPPER'
#!/bin/sh
set -e

# Kanboard was served straight out of the read-only store (`-t $out/app`), so it
# could not write its SQLite database, its config or its uploads — and had no
# administrator anyone could sign in as.
cp -a $out/app/. .
chmod -R u+w .
mkdir -p data plugins

# config.php is PHP, and any output before it is included reaches the client
# ahead of the headers — which kills Set-Cookie, and with it the session the
# login POST needs. Kanboard's own error message for that is "The username is
# required", which points at the form rather than at the transport.
if [ ! -f config.php ]; then
  cat > config.php << CFGEOF
<?php
// Guarded. Kanboard includes config.php from more than one entry point, and a
// bare define() of an already-defined constant emits a PHP warning — output
// before the headers, which kills Set-Cookie and with it the session the login
// POST needs. Kanboard then answers "The username is required", which describes
// the form rather than the transport that failed underneath it.
if (!defined('DB_DRIVER')) {
    define('DB_DRIVER', 'mysql');
    define('DB_HOSTNAME', getenv('MYSQL_HOST') ?: '127.0.0.1');
    define('DB_PORT', (int)(getenv('MYSQL_PORT') ?: 3306));
    define('DB_NAME', getenv('MYSQL_DATABASE') ?: 'kanboard');
    define('DB_USERNAME', getenv('MYSQL_USER') ?: 'kanboard');
    define('DB_PASSWORD', getenv('MYSQL_PASSWORD') ?: "");
    define('DEBUG', false);
    // stderr, not Kanboard's default file log: when the file is unwritable it
    // warns to the RESPONSE, ahead of the headers, which kills Set-Cookie and
    // with it the session the login POST needs.
    define('LOG_DRIVER', 'stderr');
    // The web plugin installer lets a signed-in admin install arbitrary remote
    // code. The working variants keep it off.
    define('PLUGIN_INSTALLER', false);
}
CFGEOF
fi

# Warnings from anywhere else in the tree do the same damage, and PHP's builtin
# server prints them to the response by default — so they are turned off on the
# interpreter's command line below. NOT via `PHP_INI_SCAN_DIR=`: that also stops
# PHP reading the conf.d Nix writes its `extension=` lines into, which silently
# removed every declared extension and left Kanboard reporting
# "PHP extension required: pdo_mysql" for an extension the derivation ships.

${php}/bin/php cli db:migrate 2>/dev/null || true

# Kanboard ships admin/admin, and there is no `cli user:reset-password`
# subcommand — the earlier call to one was swallowed by `|| true` and did
# nothing at all. The working variants go through Kanboard's own container and
# write the bcrypt hash directly, which is what this does. It runs on every
# start because the generated password is the only credential the operator has.
if [ -n "''${HOP3_ADMIN_PASSWORD:-}" ]; then
  ${php}/bin/php <<'PHPRESET'
<?php
require getcwd() . '/app/common.php';
$password = getenv('HOP3_ADMIN_PASSWORD');
$username = getenv('HOP3_ADMIN_USER') ?: 'admin';
$db = $container['db'];
$admin = $db->table('users')->eq('username', $username)->findOne();
if (empty($admin)) {
    fwrite(STDERR, "Kanboard user '$username' not found; db:migrate must run first\n");
    exit(1);
}
$hash = password_hash($password, PASSWORD_BCRYPT);
if ($db->table('users')->eq('id', $admin['id'])->update(array('password' => $hash)) === false) {
    fwrite(STDERR, "Failed to reset the Kanboard password for '$username'\n");
    exit(1);
}
PHPRESET
fi

exec ${php}/bin/php -d display_errors=0 -d error_reporting=0 -S 0.0.0.0:''${PORT:-8080} -t .
WRAPPER
      sed -i "s|\$out|$out|g" $out/bin/kanboard
      chmod +x $out/bin/kanboard

      mkdir -p $out/hop3
      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/kanboard"
  },
  "env": {
    "DEBUG": "false"
  },
  "path": [
    "$out/bin",
    "${php}/bin"
  ]
}
EOF
    '';
  };

in
{
  package = app;
  env = {
    DEBUG = "false";
  };
}
