#!/bin/bash
# Download WordPress

set -e

WP_VERSION="${WP_VERSION:-6.4.2}"
DOWNLOAD_URL="https://wordpress.org/wordpress-${WP_VERSION}.tar.gz"

echo "Downloading WordPress v${WP_VERSION}..."

# Download and extract (strip the top-level directory)
curl -sL "$DOWNLOAD_URL" | tar xz --strip-components=1

# Create wp-content directories with proper permissions
mkdir -p wp-content/uploads wp-content/plugins wp-content/themes
chmod 755 wp-content wp-content/uploads wp-content/plugins wp-content/themes

echo "WordPress downloaded successfully"
