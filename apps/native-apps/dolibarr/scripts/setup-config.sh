#!/bin/bash
set -e
cd "$(dirname "$0")/.."

# Create config if not exists
if [ ! -f htdocs/conf/conf.php ]; then
    cat > htdocs/conf/conf.php << EOF
<?php
\$dolibarr_main_url_root='http://localhost:${PORT:-8080}';
\$dolibarr_main_document_root='$(pwd)/htdocs';
\$dolibarr_main_data_root='$(pwd)/documents';
\$dolibarr_main_db_host='${PGHOST:-localhost}';
\$dolibarr_main_db_port='${PGPORT:-5432}';
\$dolibarr_main_db_name='${PGDATABASE:-dolibarr}';
\$dolibarr_main_db_user='${PGUSER:-dolibarr}';
\$dolibarr_main_db_pass='${PGPASSWORD:-}';
\$dolibarr_main_db_type='pgsql';
\$dolibarr_main_db_character_set='utf8';
\$dolibarr_main_db_collation='utf8_unicode_ci';
EOF
fi

echo "Dolibarr configuration ready"
