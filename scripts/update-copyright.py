import re
from pathlib import Path

CURRENT_YEAR = 2025


def main():
    python_files = list(Path("packages").rglob("*.py"))
    for python_file in python_files:
        update_copyright(python_file)


def update_copyright(python_file):
    content = python_file.read_text()

    new_content_lines = []
    for line in content.split("\n"):
        if not line.startswith("#"):
            new_content_lines.append(line)
            continue

        m = re.match(r"# Copyright \(c\) ([0-9]+), Abilian SAS", line)
        if m:
            print(f"Updating copyright in {python_file}")
            year = int(m.group(1))
            if year == CURRENT_YEAR:
                print(f"Skipping {python_file}")
                return

            line = f"# Copyright (c) {year}-{CURRENT_YEAR}, Abilian SAS"

        m = re.match(r"# Copyright \(c\) ([0-9]+)-([0-9]+), Abilian SAS", line)
        if m:
            print(f"Updating copyright in {python_file}")
            year_start = int(m.group(1))
            year_end = int(m.group(2))
            if year_end == CURRENT_YEAR:
                print(f"Skipping {python_file}")
                return

            line = f"# Copyright (c) {year_start}-{CURRENT_YEAR}, Abilian SAS"

        new_content_lines.append(line)

    new_content = "\n".join(new_content_lines)
    python_file.write_text(new_content)


if __name__ == "__main__":
    main()
