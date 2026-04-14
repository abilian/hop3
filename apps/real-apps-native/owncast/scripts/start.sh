#!/bin/bash
set -e

: "${PORT:?ERROR: PORT is required}"

mkdir -p data

# Owncast takes --webserverport and --rtmpport as CLI flags.
# RTMP (for streaming in) defaults to 1935; leave it as-is for local tests.
exec ./owncast --webserverport "${PORT}" --webserverip 0.0.0.0 --database data/owncast.db
