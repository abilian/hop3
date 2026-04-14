#!/bin/bash
# Generate WriteFreely config.ini from env vars
set -e

PORT="${PORT:-8080}"

mkdir -p data

cat > config.ini << EOF
[server]
hidden_host          =
port                 = ${PORT}
bind                 = 0.0.0.0
tls_cert_path        =
tls_key_path         =
autocert             = false
templates_parent_dir =
static_parent_dir    =
pages_parent_dir     =
keys_parent_dir      =
hash_seed            = $(head -c 32 /dev/urandom | base64)
gopher_port          = 0

[database]
type     = sqlite3
filename = data/writefreely.db
username =
password =
database =
host     =
port     =
tls      = false

[app]
site_name          = WriteFreely
site_description   =
host               = http://localhost:${PORT}
theme              = write
editor             =
disable_js         = false
webfonts           = true
landing            =
simple_nav         = false
wf_modesty         = false
chorus             = false
forest             = false
disable_drafts     = false
single_user        = false
open_registration  = false
open_deletion      = false
min_username_len   = 3
max_blogs          = 1
federation         = true
public_stats       = true
monetization       = false
notes_only         = false
private            = false
local_timeline     = true
user_invites       =
default_visibility = public
update_checks      = false
disable_password_auth = false
EOF

# Initialize the database if it doesn't exist
if [ ! -f data/writefreely.db ]; then
    ./writefreely --init-db || true
    ./writefreely --gen-keys || true
fi
