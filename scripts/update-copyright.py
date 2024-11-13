import re
from pathlib import Path

from devtools import debug

PAT_1Y = r"# Copyright \(c\) ([0-9]+), Abilian SAS"
PAT_2Y = r"# Copyright \(c\) ([0-9]+)-([0-9]+), Abilian SAS"

CURRENT_YEAR = 2024


def main():
    python_files = list(Path("packages").rglob("*.py"))
    for python_file in python_files:
        update_copyright(python_file)


def update_copyright(python_file):
    content = python_file.read_text()

    m1 = re.search(PAT_1Y, content)
    m2 = re.search(PAT_2Y, content)
    if not m1 and not m2:
        print(f"Adding copyright in {python_file}")
        content = f"# Copyright (c) {CURRENT_YEAR}, Abilian SAS\n" + content
        python_file.write_text(content)
        return

    new_content_lines = []
    for line in content.split("\n"):
        if not line.startswith("#"):
            new_content_lines.append(line)
            continue

        m = re.match(PAT_1Y, line)
        if m:
            year = int(m.group(1))
            if year == CURRENT_YEAR:
                return

            print(f"Updating copyright in {python_file}")
            line = f"# Copyright (c) {year}-{CURRENT_YEAR}, Abilian SAS"

        m = re.match(PAT_2Y, line)
        if m:
            year_start = int(m.group(1))
            year_end = int(m.group(2))
            if year_end == CURRENT_YEAR:
                return

            line = f"# Copyright (c) {year_start}-{CURRENT_YEAR}, Abilian SAS"

        new_content_lines.append(line)

    new_content = "\n".join(new_content_lines)
    python_file.write_text(new_content)


if __name__ == "__main__":
    main()
