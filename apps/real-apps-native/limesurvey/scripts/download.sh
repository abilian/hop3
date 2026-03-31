#!/bin/bash
set -e
VERSION="${LIMESURVEY_VERSION:-6.16.10}"
DATE_SUFFIX="${LIMESURVEY_DATE:-260223}"
echo "Downloading LimeSurvey v${VERSION}..."
# Download from official LimeSurvey site
curl -sL "https://download.limesurvey.org/latest-master/limesurvey${VERSION}+${DATE_SUFFIX}.zip" -o limesurvey.zip
unzip -q limesurvey.zip
mv limesurvey/* . 2>/dev/null || mv limesurvey*/* . 2>/dev/null || true
rm -rf limesurvey limesurvey.zip
mkdir -p tmp upload
chmod 755 tmp upload
echo "LimeSurvey downloaded successfully"
