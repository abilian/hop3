#!/usr/bin/env python3

from pathlib import Path


def main():
    import sys
    src_path = Path(sys.argv[1])
    if not src_path.exists():
        print(f"Source path {src_path} does not exist.")
        return
    lines = src_path.read_text().splitlines()

    in_toc = False
    result = []
    for line in lines:
        if line == "<!-- toc -->":
            in_toc = True
        if line == "<!-- tocstop -->":
            in_toc = False
        if in_toc and line.startswith("  *"):
            line = "  " + line
        result.append(line)

    src_path.write_text("\n".join(result))


if __name__ == "__main__":
    main()
