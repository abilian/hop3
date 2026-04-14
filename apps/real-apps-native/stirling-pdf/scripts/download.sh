#!/bin/bash
# Download Stirling-PDF fat JAR
set -e

STIRLING_PDF_VERSION="${STIRLING_PDF_VERSION:-v2.9.2}"
URL="https://github.com/Stirling-Tools/Stirling-PDF/releases/download/${STIRLING_PDF_VERSION}/Stirling-PDF.jar"

echo "Downloading Stirling-PDF ${STIRLING_PDF_VERSION}..."
curl -fsSL "$URL" -o Stirling-PDF.jar
echo "Downloaded $(du -h Stirling-PDF.jar | cut -f1) of Stirling-PDF.jar"
