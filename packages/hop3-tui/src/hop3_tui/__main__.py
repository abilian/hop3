# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Entry point for the Hop3 TUI."""

from __future__ import annotations

from turbodesk import run

from hop3_tui.app import Hop3TUI, app


def main() -> None:
    hop3 = Hop3TUI()
    run(app(hop3), title="Hop3")


if __name__ == "__main__":
    main()
