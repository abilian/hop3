#!/bin/bash
set -e
VERSION="${JENKINS_VERSION:-2.541.2}"
echo "Downloading Jenkins v${VERSION}..."
curl -sL "https://get.jenkins.io/war-stable/${VERSION}/jenkins.war" -o jenkins.war
# Verify the download was successful (WAR files are zip archives)
if ! unzip -t jenkins.war > /dev/null 2>&1; then
    echo "ERROR: Downloaded file is not a valid WAR/zip file"
    exit 1
fi
mkdir -p jenkins_home
echo "Jenkins downloaded successfully"
