#!/usr/bin/env sh

( cd ../.. && hop3-deploy --host hop3.dev --local --with all --clean )

python test-script.py docker-based/wordpress --debug
