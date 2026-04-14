#!/bin/bash
set -e

: "${PORT:?ERROR: PORT is required}"

mkdir -p /data/configs /data/customFiles /data/logs /data/pipeline
cd /data

export SERVER_PORT="${PORT}"
export SERVER_ADDRESS="0.0.0.0"

exec java -jar /opt/Stirling-PDF.jar
