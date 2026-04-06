"""Jenkins: Java WAR file, JDK runtime."""

from hop3_nix_gen.spec import AppSpec, Source

SPEC = AppSpec(
    pname="jenkins",
    version="2.541.2",
    description="The leading open source automation server for CI/CD",
    template="java-war",
    runtime_package="jdk17",
    war_file="jenkins.war",
    source=Source(
        url="https://get.jenkins.io/war-stable/${version}/jenkins.war",
        sha256="3J1TLlTUt+t9eO3NMheHbdSBG0nRo7ZuWZrUpkLVcZM=",
    ),
    env_exports={
        "JENKINS_HOME": "${JENKINS_HOME:-./jenkins_home}",
    },
    pre_exec_commands=[
        'mkdir -p "$JENKINS_HOME"',
    ],
    exec_args=[
        '--httpPort="${PORT:-8080}"',
        '"$@"',
    ],
    runtime_env={
        "JENKINS_HOME": "./jenkins_home",
        "JAVA_OPTS": (
            "-Djava.awt.headless=true -Djenkins.install.runSetupWizard=false"
        ),
    },
    extra_paths=["${jdk}/bin"],
)
