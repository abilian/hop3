#!/bin/bash
set -e

: "${PORT:?ERROR: PORT is required}"

mkdir -p configs customFiles logs pipeline

export SERVER_PORT="${PORT}"
export SERVER_ADDRESS="0.0.0.0"

exec java -jar Stirling-PDF.jar
