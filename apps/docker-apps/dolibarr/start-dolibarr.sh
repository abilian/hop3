#!/bin/bash
set -e

# Validate required environment variables (injected by Hop3)
: "${PGHOST:?ERROR: PGHOST is required}"
: "${PGPORT:?ERROR: PGPORT is required}"
: "${PGDATABASE:?ERROR: PGDATABASE is required}"
: "${PGUSER:?ERROR: PGUSER is required}"
: "${PGPASSWORD:?ERROR: PGPASSWORD is required}"

# Optional with defaults
DOLI_URL_ROOT="${DOLI_URL_ROOT:-http://localhost:8080}"
DOLI_INSTANCE_ID="${DOLI_INSTANCE_ID:-hop3_dolibarr}"

# Generate conf.php
cat > /var/www/dolibarr/htdocs/conf/conf.php << EOF
<?php
\$dolibarr_main_url_root = '${DOLI_URL_ROOT}';
\$dolibarr_main_document_root = '/var/www/dolibarr/htdocs';
\$dolibarr_main_url_root_alt = '/custom';
\$dolibarr_main_document_root_alt = '/var/www/dolibarr/htdocs/custom';
\$dolibarr_main_data_root = '/var/lib/dolibarr/documents';
\$dolibarr_main_db_host = '${PGHOST}';
\$dolibarr_main_db_port = '${PGPORT}';
\$dolibarr_main_db_name = '${PGDATABASE}';
\$dolibarr_main_db_user = '${PGUSER}';
\$dolibarr_main_db_pass = '${PGPASSWORD}';
\$dolibarr_main_db_type = 'pgsql';
\$dolibarr_main_db_character_set = 'utf8';
\$dolibarr_main_db_collation = 'utf8_general_ci';
\$dolibarr_main_authentication = 'dolibarr';
\$dolibarr_main_prod = 1;
\$dolibarr_main_force_https = 0;
\$dolibarr_main_restrict_os_commands = 'mysqldump, mysql, pg_dump, psql';
\$dolibarr_nocsrfcheck = 0;
\$dolibarr_main_instance_unique_id = '${DOLI_INSTANCE_ID}';
EOF

# Set permissions
chown -R www-data:www-data /var/www/dolibarr /var/lib/dolibarr
chmod 644 /var/www/dolibarr/htdocs/conf/conf.php

# Start Apache in foreground
exec apache2ctl -D FOREGROUND
