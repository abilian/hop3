#!/bin/bash
# Download Etherpad source

set -e

ETHERPAD_VERSION="${ETHERPAD_VERSION:-2.0.3}"
DOWNLOAD_URL="https://github.com/ether/etherpad-lite/archive/refs/tags/v${ETHERPAD_VERSION}.tar.gz"

echo "Downloading Etherpad v${ETHERPAD_VERSION}..."

# Download and extract (strip the top-level directory)
curl -sL "$DOWNLOAD_URL" | tar xz --strip-components=1

# pnpm >= 10 no longer reads `auto-install-peers` from .npmrc (Etherpad 2.x sets
# it there), so a newer pnpm falls back to the default (true) while the lockfile
# records autoInstallPeers: false. The frozen install (CI=true bin/installDeps.sh)
# then aborts with ERR_PNPM_LOCKFILE_CONFIG_MISMATCH. Pin the setting in
# pnpm-workspace.yaml, which pnpm 10+ does honor, so it matches the lockfile.
if [ -f pnpm-workspace.yaml ] && ! grep -q '^autoInstallPeers:' pnpm-workspace.yaml; then
  printf '\nautoInstallPeers: false\n' >> pnpm-workspace.yaml
fi

# pnpm >= 10 no longer runs a dependency's install/build scripts unless it is
# explicitly approved; under `CI=true` (frozen install) an unapproved one aborts
# with ERR_PNPM_IGNORED_BUILDS. `onlyBuiltDependencies` is NOT enough here: it
# records the approval in the lockfile, which a `--frozen-lockfile` install can't
# write, so the scripts stay ignored. `dangerouslyAllowAllBuilds` is a runtime
# override that needs no lockfile change — it restores pnpm 9's default of
# running build scripts, which Etherpad's native deps (esbuild, @swc/core, …)
# require. (Verified against pnpm 11 with a frozen install.)
if [ -f pnpm-workspace.yaml ] && ! grep -q '^dangerouslyAllowAllBuilds:' pnpm-workspace.yaml; then
  printf '\ndangerouslyAllowAllBuilds: true\n' >> pnpm-workspace.yaml
fi

echo "Etherpad source downloaded successfully"
