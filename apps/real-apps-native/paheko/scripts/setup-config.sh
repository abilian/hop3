#!/bin/bash
set -e

mkdir -p data

if [ ! -f src/config.local.php ]; then
    cat > src/config.local.php <<EOF
<?php
const DATA_ROOT = __DIR__ . '/../data';
const DB_FILE = DATA_ROOT . '/paheko.sqlite';
const SECRET_KEY = '$(head -c 32 /dev/urandom | base64)';
EOF
fi
