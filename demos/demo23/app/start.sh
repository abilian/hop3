#!/bin/bash
set -e

echo "==> Starting DokuWiki"

# Ensure data directories are writable
chown -R www-data:www-data /var/www/html/data /var/www/html/conf /var/www/html/lib/plugins

echo "==> Starting Apache"
exec apache2-foreground
