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
        """Check if the application has Java build configuration (Maven or Gradle)."""
        build_files = ("pom.xml", "build.gradle", "build.gradle.kts")
        return any((self.src_path / f).exists() for f in build_files)

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
