# Copyright (c) 2024, Abilian SAS
# ruff: noqa: A003
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SOURCES = [
    # "hop3-lib",
    "hop3-agent",
    # "hop3-build",
    # "hop3-orchestrator",
]


@dataclass
class Generator:
    source: str

    def __post_init__(self):
        self.root_dir = Path("..") / self.source / "src"
        self.output = []
        self.output_file = (Path("src") / "api" / f"{self.source}.md").open("w")

    def generate_spi(self) -> None:
        """Generate API documentation."""

        self.print(f"# API Documentation for `{self.source}`")
        self.print()

        for soure_file in sorted(self.root_dir.rglob("**/*.py")):
            source_file_name = str(soure_file.relative_to(self.root_dir))
            if source_file_name.endswith("__init__.py"):
                package_name = source_file_name[:-12].replace("/", ".")
                self.print(f"## Package `{package_name}`")
                self.print()
                self.print(f"::: {package_name}")
            else:
                module_name = source_file_name[:-3].replace("/", ".")
                self.print(f"## Module `{module_name}`")
                self.print()
                self.print(f"::: {module_name}")
            self.print()

        self.output_file.write("\n".join(self.output).strip() + "\n")

    def print(self, *args) -> None:
        self.output.append(" ".join(args))


def main() -> None:
    for source in SOURCES:
        generator = Generator(source)
        generator.generate_spi()


if __name__ == "__main__":
    main()
