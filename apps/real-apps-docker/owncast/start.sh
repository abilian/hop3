#!/bin/bash
set -e

: "${PORT:?ERROR: PORT is required}"

cd /opt/owncast

exec ./owncast --webserverport "${PORT}" --webserverip 0.0.0.0 --database /data/owncast.db
