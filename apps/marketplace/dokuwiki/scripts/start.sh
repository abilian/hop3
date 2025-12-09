#!/bin/bash
# DokuWiki start script for Hop3

set -eu

DATA_DIR="${HOP3_DATA_DIR:-/app/data}"
CODE_DIR="${HOP3_CODE_DIR:-/app/code}"
PKG_DIR="${HOP3_PKG_DIR:-/app/pkg}"

# Initialize data directory on first run
if [[ ! -e "${DATA_DIR}/data" ]]; then
    echo "==> Initializing data directory on first run"
    cp -r "${CODE_DIR}/data/." "${DATA_DIR}/data"
else
    # this allows deleting playground, formatting pages and not bring them back on restart
    rsync -v -a --ignore-existing --exclude "pages/*" --exclude "log/" "${CODE_DIR}/data/" "${DATA_DIR}/data/"
fi

mkdir -p "${DATA_DIR}/conf" "${DATA_DIR}/templates" "${DATA_DIR}/plugins" /run/dokuwiki/sessions /run/dokuwiki/log
rm -rf "${DATA_DIR}/data/log" && ln -s /run/dokuwiki/log "${DATA_DIR}/data/log"

# Create 'regular' conf files so that they are immediately writable
# dist, example, template files are not copied. they have to copied over 'carefully'
cp "${CODE_DIR}/conf.orig/.htaccess" "${CODE_DIR}/conf.orig/"*.php "${CODE_DIR}/conf.orig/"*.conf "${DATA_DIR}/conf/" 2>/dev/null || true

# required for siteexport plugin
if [[ ! -f "${DATA_DIR}/preload.php" ]]; then
    cp "${CODE_DIR}/inc/preload.php.dist" "${DATA_DIR}/preload.php" 2>/dev/null || true
fi

for f in $(ls "${CODE_DIR}/lib/tpl.orig" 2>/dev/null); do
    rm -rf "${DATA_DIR}/templates/$f"
    cp -rf "${CODE_DIR}/lib/tpl.orig/$f" "${DATA_DIR}/templates/$f"
done

for f in $(ls "${CODE_DIR}/lib/plugins.orig" 2>/dev/null); do
    rm -rf "${DATA_DIR}/plugins/$f"
    # skip copying auth plugins (see #10)
    if [[ ! -d "${CODE_DIR}/lib/plugins.orig/$f" || $f != auth* ]]; then
        echo "==> Copying plugin: $f"
        cp -rf "${CODE_DIR}/lib/plugins.orig/$f" "${DATA_DIR}/plugins/$f"
    fi
done

[[ -z "${MAIL_FROM_DISPLAY_NAME:-}" ]] && export MAIL_FROM_DISPLAY_NAME=DokuWiki
[[ -z "${OIDC_PROVIDER_NAME:-}" ]] && export OIDC_PROVIDER_NAME=SSO

# https://www.dokuwiki.org/plugin:config#protecting_settings
cp "${PKG_DIR}/templates/local.protected.php.template" "${DATA_DIR}/conf/local.protected.php"

# we only provide a template, the user can change this using the acl UI
# this file is needed for SSO and non-SSO modes
if [[ ! -f "${DATA_DIR}/conf/acl.auth.php" ]]; then
    cp "${CODE_DIR}/conf.orig/acl.auth.php.template" "${DATA_DIR}/conf/acl.auth.php" 2>/dev/null || true
fi

if [[ -n "${OIDC_ISSUER:-}" ]]; then
    echo "==> Setting up OIDC"

    cp -rf "${CODE_DIR}/lib/plugins.orig/authplain" "${DATA_DIR}/plugins/"
    cp -rf "${CODE_DIR}/lib/plugins.orig/oauth" "${DATA_DIR}/plugins/"
    cp -rf "${CODE_DIR}/lib/plugins.orig/oauthgeneric" "${DATA_DIR}/plugins/"

    # putting this in protected file ensures user cannot change it in UI
    if ! grep -q "plugins\['oauth'\] = 1" "${DATA_DIR}/conf/plugins.required.php" 2>/dev/null; then
        echo -e "\n\$plugins['oauth'] = 1;\n\$plugins['oauthgeneric'] = 1;\n" >> "${DATA_DIR}/conf/plugins.required.php"
    fi

    if [[ ! -f "${DATA_DIR}/conf/users.auth.php" ]]; then
        cp "${CODE_DIR}/conf.orig/users.auth.php.dist" "${DATA_DIR}/conf/users.auth.php" 2>/dev/null || true
    fi

    # be careful as to what is in this file since not all values are persisted by the admin UI
    if [[ ! -f "${DATA_DIR}/conf/local.php" ]]; then
        cat > "${DATA_DIR}/conf/local.php" <<'EOF'
<?php

// Add custom configuration here
// make users as doku wiki admins (https://www.dokuwiki.org/config:superuser)
// $conf['superuser']   = 'username';
EOF
    fi

    # previous LDAP plugin had registration disabled by default
    if ! grep -q openregister "${DATA_DIR}/conf/local.php"; then
        echo -e "\n\$conf['openregister'] = 0;\n" >> "${DATA_DIR}/conf/local.php"
    fi
else
    echo "==> Setting up plain auth"

    cp -rf "${CODE_DIR}/lib/plugins.orig/authplain" "${DATA_DIR}/plugins/authplain"

    if [[ ! -f "${DATA_DIR}/conf/users.auth.php" ]]; then
        cp "${CODE_DIR}/conf.orig/users.auth.php.dist" "${DATA_DIR}/conf/users.auth.php" 2>/dev/null || true
    fi

    if [[ ! -f "${DATA_DIR}/conf/local.php" ]]; then
        cat > "${DATA_DIR}/conf/local.php" <<'EOF'
<?php

// Add custom configuration here
// $conf['title'] = 'My Wiki';
EOF
    fi
fi

if [[ ! -f "${DATA_DIR}/php.ini" ]]; then
    echo -e "; Add custom PHP configuration in this file\n; Settings here are merged with the package's built-in php.ini\n\n" > "${DATA_DIR}/php.ini"
fi

chown -R www-data:www-data "${DATA_DIR}" /run/dokuwiki

echo "==> Starting apache"
APACHE_CONFDIR="" source /etc/apache2/envvars
rm -f "${APACHE_PID_FILE}"
exec /usr/sbin/apache2 -DFOREGROUND
