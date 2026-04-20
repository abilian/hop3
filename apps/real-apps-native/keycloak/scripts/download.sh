#!/bin/bash
# Download Keycloak + a JDK 21 runtime.
#
# The JDK 21 dance is a workaround for DEFERRED-APPS.md blocker #1:
# [build].packages is parsed but not consumed by the build pipeline,
# so we can't declare `openjdk-21-jdk` and get it apt-installed for us.
# The Hop3 installer ships `default-jdk` (JDK 17 on Debian bookworm)
# which isn't enough for Keycloak 26.
#
# Instead we fetch a headless JRE 21 from Adoptium and unpack it
# alongside the app — fully user-space, no root needed. Ships inside
# the per-app venv so it doesn't pollute the host.

set -e

KEYCLOAK_VERSION="${KEYCLOAK_VERSION:-26.1.4}"
JDK_VERSION_URL="${JDK_VERSION_URL:-https://api.adoptium.net/v3/binary/latest/21/ga/linux/x64/jre/hotspot/normal/eclipse}"

echo "Downloading Keycloak ${KEYCLOAK_VERSION}..."
KC_URL="https://github.com/keycloak/keycloak/releases/download/${KEYCLOAK_VERSION}/keycloak-${KEYCLOAK_VERSION}.tar.gz"
curl -fsSL "$KC_URL" -o keycloak.tar.gz
tar -xzf keycloak.tar.gz
rm keycloak.tar.gz
mv "keycloak-${KEYCLOAK_VERSION}" keycloak
echo "  → $(du -sh keycloak | cut -f1)"

echo "Downloading Temurin 21 JRE..."
# Adoptium's "latest 21 GA JRE linux x64 hotspot" redirects to a
# versioned tarball; -L follows it. Keep the fetch small (JRE, not JDK).
curl -fsSL -o jre.tar.gz "$JDK_VERSION_URL"
mkdir -p jre
tar -xzf jre.tar.gz --strip-components=1 -C jre
rm jre.tar.gz
echo "  → JRE at $(./jre/bin/java -version 2>&1 | head -1)"
