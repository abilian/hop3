# Copyright (c) 2025, Abilian SAS
# SPDX-FileCopyrightText: 2024-2025 Abilian SAS <https://abilian.com>
# SPDX-FileCopyrightText: 2024-2025 Stefane Fermigier
# SPDX-License-Identifier: Apache-2.0

"""Entry point for hop3-tui."""

from __future__ import annotations

from hop3_tui.app import Hop3TUI


def main() -> None:
    """Run the Hop3 TUI application."""
    app = Hop3TUI()
    app.run()


if __name__ == "__main__":
    main()
