#!/bin/bash
set -e
cat > config.json << EOF
{
  "production": {
    "host": "0.0.0.0",
    "port": ${PORT:-8080},
    "db": {
      "dialect": "postgres",
      "host": "${PGHOST:-localhost}",
      "port": ${PGPORT:-5432},
      "database": "${PGDATABASE:-hedgedoc}",
      "username": "${PGUSER:-hedgedoc}",
      "password": "${PGPASSWORD:-}"
    },
    "sessionSecret": "$(head -c 32 /dev/urandom | base64)",
    "allowAnonymous": true,
    "allowAnonymousEdits": true,
    "defaultPermission": "freely"
  }
}
EOF
npx sequelize db:migrate
echo "HedgeDoc configuration created"
