#!/bin/bash
set -e
VERSION="${SONARQUBE_VERSION:-26.2.0.119303}"
echo "Downloading SonarQube v${VERSION}..."
curl -sL "https://binaries.sonarsource.com/Distribution/sonarqube/sonarqube-${VERSION}.zip" -o /tmp/sonarqube.zip
unzip -q /tmp/sonarqube.zip
mv sonarqube-${VERSION}/* .
rm -rf sonarqube-${VERSION} /tmp/sonarqube.zip
chmod +x bin/linux-x86-64/sonar.sh
echo "SonarQube downloaded successfully"
