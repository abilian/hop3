# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
The vassal ``.ini`` name/glob boundary — apps must not reap each other.

The regression: every app-scoped sweep globbed ``{name}*.ini`` while the
writer emitted ``{name}_{kind}.{ordinal}.ini``, so stopping or destroying
``wiki`` unlinked ``wiki-js_web.1.ini`` and silently took down a different
app. ``run/reaper.py`` had already fixed the identical prefix collision for
processes; this is its filesystem twin.
"""

from __future__ import annotations

import fnmatch

from hop3.run.uwsgi.naming import vassal_glob, vassal_name


def test_glob_matches_the_apps_own_vassals():
    pattern = vassal_glob("wiki")
    assert fnmatch.fnmatch(vassal_name("wiki", "web", 1), pattern)
    assert fnmatch.fnmatch(vassal_name("wiki", "worker", 3), pattern)
    assert fnmatch.fnmatch(vassal_name("wiki", "waf", 1), pattern)


def test_glob_does_not_match_a_prefix_sharing_app():
    # The bug: `wiki*.ini` matched every one of these.
    pattern = vassal_glob("wiki")
    for other in ("wiki-js", "wiki2", "wikimedia"):
        assert not fnmatch.fnmatch(vassal_name(other, "web", 1), pattern), other


def test_sweep_on_disk_leaves_the_other_app_alone(tmp_path):
    mine = tmp_path / vassal_name("wiki", "web", 1)
    theirs = tmp_path / vassal_name("wiki-js", "web", 1)
    mine.touch()
    theirs.touch()

    for f in tmp_path.glob(vassal_glob("wiki")):
        f.unlink()

    assert not mine.exists()
    assert theirs.exists(), "destroying 'wiki' removed 'wiki-js' vassal config"
