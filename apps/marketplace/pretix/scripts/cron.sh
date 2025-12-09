#!/bin/bash
# Pretix cron script for Hop3
# Runs housekeeping tasks

set -eu

VENV_PATH="${VENV_PATH:-/app/code/venv}"

source ${VENV_PATH}/bin/activate
exec python -m pretix runperiodic
