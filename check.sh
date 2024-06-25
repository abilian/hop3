#!/bin/sh

set -eax

make deploy

cd sandbox/000-static && \
    hop config:set NGINX_SERVER_NAME=static.hop-dev.abilian.com
