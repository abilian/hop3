#!/bin/bash
set -e
VERSION="${EASY_APPOINTMENTS_VERSION:-1.5.0}"
echo "Downloading Easy!Appointments v${VERSION}..."
curl -sL "https://github.com/alextselegidis/easyappointments/archive/refs/tags/${VERSION}.tar.gz" | tar xz --strip-components=1
echo "Easy!Appointments downloaded successfully"
