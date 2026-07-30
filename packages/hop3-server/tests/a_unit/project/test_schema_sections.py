# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""Rules the hop3.toml sections enforce at parse time."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from hop3.project.schema import ProbeSection


class TestProbeMustBeCreatable:
    """
    A [probe] Hop3 cannot create is a [probe] Hop3 cannot use.

    `create` was optional, meaning "the app makes this account itself from the
    injected vars". Hop3 has no way to confirm it did, so the smoke test was
    never given the credential — the section read as configuration and did
    nothing whatsoever.

    Both recipes that used the form proved why it cannot stand. matomo's
    installer and uptime-kuma's bootstrap each created the probe only in the
    branch where they also created the ADMIN, so any instance that already had
    one silently got no probe, and nothing anywhere noticed.
    """

    def test_a_probe_without_create_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="create"):
            ProbeSection(username="hop3probe")

    def test_a_blank_create_is_rejected(self) -> None:
        """Whitespace is not a command; accepting it restores the inert state."""
        with pytest.raises(ValidationError, match="do nothing"):
            ProbeSection(username="hop3probe", create="   ")

    def test_a_probe_with_a_create_command_is_accepted(self) -> None:
        section = ProbeSection(username="hop3probe", create="make-probe")
        assert section.create == "make-probe"

    def test_the_username_still_defaults(self) -> None:
        assert ProbeSection(create="make-probe").username == "hop3probe"
