# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Language toolchain for Java projects."""

from __future__ import annotations

from hop3.core.protocols import BuildArtifact

from ._base import LanguageToolchain


class JavaToolchain(LanguageToolchain):
    """Language toolchain for Java projects.

    This is responsible for building Java projects by checking for Maven
    (pom.xml) or Gradle (build.gradle) configuration files.
    """

    name = "Java"
    requirements = ["java"]  # noqa: RUF012

    def accept(self) -> bool:
        """Check if the application has Java build configuration."""
        # Check for Maven pom.xml
        if (self.src_path / "pom.xml").exists():
            return True
        # Check for Gradle build.gradle or build.gradle.kts
        if (self.src_path / "build.gradle").exists():
            return True
        if (self.src_path / "build.gradle.kts").exists():
            return True
        return False

    def build(self) -> BuildArtifact:
        """Build the Java application.

        Java projects typically use a Procfile prebuild step to compile
        (e.g., 'prebuild: mvn package' or 'prebuild: ./gradlew build').
        """
        return BuildArtifact(
            kind="java",
            location=str(self.src_path),
            metadata={"app_name": self.app_name},
        )
