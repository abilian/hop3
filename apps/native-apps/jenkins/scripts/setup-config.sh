#!/bin/bash
set -e
cd "$(dirname "$0")/.."

mkdir -p jenkins_home

# Skip setup wizard
mkdir -p jenkins_home/init.groovy.d
cat > jenkins_home/init.groovy.d/basic-security.groovy << 'EOF'
#!groovy
import jenkins.model.*
import hudson.security.*

def instance = Jenkins.getInstance()
def hudsonRealm = new HudsonPrivateSecurityRealm(false)
hudsonRealm.createAccount("admin", "admin")
instance.setSecurityRealm(hudsonRealm)

def strategy = new FullControlOnceLoggedInAuthorizationStrategy()
strategy.setAllowAnonymousRead(false)
instance.setAuthorizationStrategy(strategy)
instance.save()
EOF

echo "Jenkins configuration ready"
