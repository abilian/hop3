#!/bin/bash
# Install Ghost using ghost-cli (the official installation method)

set -e

GHOST_VERSION="${GHOST_VERSION:-5.74.5}"

echo "Installing Ghost v${GHOST_VERSION} using ghost-cli..."

# ghost-cli requires an empty directory with proper permissions
# Create install dir in current directory (which has correct perms)
INSTALL_DIR="ghost-install-temp"
mkdir -p "$INSTALL_DIR"
chmod 755 "$INSTALL_DIR"

# Use npx to run ghost-cli without global install
# --no-prompt: Don't ask questions
# --no-stack: Don't check system stack
# --no-setup: Don't run setup (we'll configure later)
# --db mysql: Use MySQL
npx ghost-cli@latest install "${GHOST_VERSION}" \
    --no-prompt \
    --no-stack \
    --no-setup \
    --db mysql \
    --dir "$INSTALL_DIR"

# Move installed files to current directory (preserving hop3.toml and scripts)
# Remove symlinks first as they have absolute paths
rm -f "$INSTALL_DIR/current"
rm -f "$INSTALL_DIR/content/themes/casper" "$INSTALL_DIR/content/themes/source" 2>/dev/null

# Copy theme files from versions directory to content/themes
if [ -d "$INSTALL_DIR/versions/${GHOST_VERSION}/content/themes/casper" ]; then
    cp -r "$INSTALL_DIR/versions/${GHOST_VERSION}/content/themes/casper" "$INSTALL_DIR/content/themes/"
fi
if [ -d "$INSTALL_DIR/versions/${GHOST_VERSION}/content/themes/source" ]; then
    cp -r "$INSTALL_DIR/versions/${GHOST_VERSION}/content/themes/source" "$INSTALL_DIR/content/themes/"
fi

mv "$INSTALL_DIR"/* .
rm -rf "$INSTALL_DIR"

# Recreate the 'current' symlink with relative path
rm -f current
ln -s "versions/${GHOST_VERSION}" current

# Create content directories if not created
mkdir -p content/data content/images content/logs content/themes content/settings

# Create the log directory for uWSGI (workaround for hop3 not creating it)
mkdir -p ../log

echo "Ghost v${GHOST_VERSION} installed successfully"
