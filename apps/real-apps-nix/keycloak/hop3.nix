# hop3.nix - Nix expression for Keycloak deployment
#
# Wraps pkgs.keycloak with a startup wrapper that:
#
#   1. Lazily copies the (read-only) nixpkgs keycloak tree into a
#      writable per-app home at $PWD/.keycloak-home.
#   2. Sets KC_HOME_DIR to that copy so kc.sh's implicit `build` step
#      (Quarkus augmentation) can write to lib/quarkus/ and data/.
#   3. Execs kc.sh from the writable copy so kc.sh's own
#      install-dir detection agrees with KC_HOME_DIR.
#
# This workaround is intentionally hand-crafted — the nix-gen variant
# (apps/bad/real-apps-nix-bad/keycloak-gen/) fails precisely because
# the nixpkgs-wrapper template can't yet express "copy package tree
# to writable dir at deploy time". See DEFERRED-APPS.md blocker #12
# for the template-extension proposal.

{ pkgs ? import <nixpkgs> {} }:

let
  keycloak = pkgs.keycloak;
  # Keycloak 26 requires JDK 21. Nixpkgs bundles Zulu 21 internally for
  # its own kc.sh compiled wrapper; we reuse the same JDK explicitly so
  # our wrapper can bypass kc.sh (whose hardcoded nix-store paths
  # defeat the writable-home trick) and exec .kc.sh-wrapped directly.
  jdk = pkgs.zulu21;

  app = pkgs.stdenv.mkDerivation {
    pname = "keycloak";
    version = keycloak.version;
    meta.description = "Enterprise SSO / OIDC / SAML identity and access management";

    dontUnpack = true;
    dontBuild = true;

    installPhase = ''
      mkdir -p $out/bin $out/hop3

      cat > $out/bin/keycloak-wrapper << 'WRAPPER'
#!/bin/sh
set -e

PORT="''${PORT:-8080}"

# Build the writable home lazily. First deploy pays the ~200MB
# cp cost; subsequent redeploys reuse the existing copy (it stays
# in $PWD across redeploys because Hop3 preserves the src dir).
HOME_DIR="$PWD/.keycloak-home"
if [ ! -f "$HOME_DIR/.hop3-ready" ]; then
  rm -rf "$HOME_DIR"
  # Preserve nix-store mode bits (files are 0444 or 0555) so scripts
  # keep exec bits; skip only ownership. The subsequent chmod adds
  # write for the owner without touching exec. -L dereferences
  # symlinks so we get real files owned+writable by hop3.
  cp -rL --no-preserve=ownership ${keycloak}/. "$HOME_DIR"
  chmod -R u+w "$HOME_DIR"
  touch "$HOME_DIR/.hop3-ready"
fi

# NIXPKGS' kc.sh is a compiled wrapper that hardcodes paths back into
# the read-only nix store (JAVA_HOME, .kc.sh-wrapped). When we copy
# it to $HOME_DIR/bin/kc.sh, the binary STILL jumps to the original
# store path — defeating the whole point of the writable copy. So we
# exec the underlying upstream shell script .kc.sh-wrapped directly,
# setting JAVA_HOME ourselves. .kc.sh-wrapped uses relative path
# resolution ($(dirname $0)/..) so it sees our writable tree.
export JAVA_HOME="${jdk}"
export PATH="${jdk}/bin:$PATH"
export KC_HOME_DIR="$HOME_DIR"
export KC_DB=postgres
export KC_DB_URL="jdbc:postgresql://''${PGHOST:-localhost}:''${PGPORT:-5432}/''${PGDATABASE:-keycloak}"
export KC_DB_USERNAME="''${PGUSER:-keycloak}"
export KC_DB_PASSWORD="''${PGPASSWORD:-}"
export KC_BOOTSTRAP_ADMIN_USERNAME="''${KC_BOOTSTRAP_ADMIN_USERNAME:-admin}"
export KC_BOOTSTRAP_ADMIN_PASSWORD="''${KC_BOOTSTRAP_ADMIN_PASSWORD:-changeme}"

exec "$HOME_DIR/bin/.kc.sh-wrapped" start-dev \
    --http-host=0.0.0.0 \
    --http-port="''${PORT}"
WRAPPER
      chmod +x $out/bin/keycloak-wrapper

      cat > $out/hop3/runtime.json << EOF
{
  "workers": {
    "web": "$out/bin/keycloak-wrapper"
  },
  "env": {},
  "path": [
    "$out/bin",
    "${keycloak}/bin"
  ]
}
EOF
    '';
  };

in
{
  package = app;
  env = {};
}
