# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Language toolchain for Java projects."""

from __future__ import annotations

from hop3.core.protocols import BuildArtifact
from hop3.lib import log

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

    @property
    def is_maven(self) -> bool:
        """Check if this is a Maven project."""
        return (self.src_path / "pom.xml").exists()

    @property
    def is_gradle(self) -> bool:
        """Check if this is a Gradle project."""
        return (self.src_path / "build.gradle").exists() or (
            self.src_path / "build.gradle.kts"
        ).exists()

    def build(self) -> BuildArtifact:
        """Build the Java application using Maven or Gradle."""
        log(f"Building Java application '{self.app_name}'", level=1, fg="blue")

        if self.is_maven:
            log("Building with Maven...", level=2, fg="cyan")
            result = self.shell("mvn -B package -DskipTests", check=False)
        elif self.is_gradle:
            # Check for gradlew wrapper
            if (self.src_path / "gradlew").exists():
                log("Building with Gradle wrapper...", level=2, fg="cyan")
                result = self.shell("./gradlew build -x test", check=False)
            else:
                log("Building with Gradle...", level=2, fg="cyan")
                result = self.shell("gradle build -x test", check=False)
        else:
            log("No recognized build tool found", level=1, fg="red")
            return BuildArtifact(
                kind="java",
                location=str(self.src_path),
                metadata={"app_name": self.app_name},
            )

        if result.returncode == 0:
            log("Java build successful", level=2, fg="green")
        else:
            log(
                "Java build failed - check pom.xml/build.gradle and source code",
                level=1,
                fg="red",
            )

        return BuildArtifact(
            kind="java",
            location=str(self.src_path),
            metadata={"app_name": self.app_name},
        )
