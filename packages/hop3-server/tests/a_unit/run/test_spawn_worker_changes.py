# Copyright (c) 2016 Rui Carmo
# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for the pure worker-scaling delta math in AppLauncher.

`_calculate_worker_changes` decides which uWSGI worker ordinals to create
and which to destroy given the current per-kind worker counts and the
requested scaling deltas. It is pure arithmetic over plain dicts/ranges,
so we exercise it directly without touching the filesystem or the ORM.
"""

from __future__ import annotations

from hop3.run.spawn import AppLauncher


def make_launcher(deltas: dict[str, int]) -> AppLauncher:
    """
    Build an AppLauncher with given deltas, skipping I/O-heavy __post_init__.

    `_calculate_worker_changes` only reads `self.deltas`, so a bare instance
    with that attribute set is enough — and avoids __post_init__'s disk/DB work.
    """
    launcher = AppLauncher.__new__(AppLauncher)
    launcher.deltas = deltas
    return launcher


def test_no_deltas_creates_each_worker_once() -> None:
    """With no scaling deltas, every declared worker is created at its count."""
    launcher = make_launcher({})
    worker_count = {"web": 2}

    to_create, to_destroy = launcher._calculate_worker_changes(worker_count)

    assert list(to_create["web"]) == [1, 2]
    assert to_destroy == {}
    # No deltas means the count is left untouched.
    assert worker_count == {"web": 2}


def test_scale_up_extends_create_range_and_bumps_count() -> None:
    """A positive delta adds higher ordinals to create and raises the count."""
    launcher = make_launcher({"web": 1})
    worker_count = {"web": 2}

    to_create, to_destroy = launcher._calculate_worker_changes(worker_count)

    assert list(to_create["web"]) == [1, 2, 3]
    assert to_destroy == {}
    assert worker_count == {"web": 3}


def test_scale_down_marks_top_ordinals_for_destruction() -> None:
    """A negative delta keeps the lower ordinals and destroys the top ones."""
    launcher = make_launcher({"web": -1})
    worker_count = {"web": 3}

    to_create, to_destroy = launcher._calculate_worker_changes(worker_count)

    assert list(to_create["web"]) == [1, 2]
    assert list(to_destroy["web"]) == [3]
    assert worker_count == {"web": 2}


def test_scale_down_by_two_destroys_two_top_ordinals() -> None:
    """Destroying two workers removes the two highest ordinals, in descending order."""
    launcher = make_launcher({"web": -2})
    worker_count = {"web": 3}

    to_create, to_destroy = launcher._calculate_worker_changes(worker_count)

    assert list(to_create["web"]) == [1]
    assert list(to_destroy["web"]) == [3, 2]
    assert worker_count == {"web": 1}


def test_deltas_for_unlisted_kind_are_ignored() -> None:
    """A delta keyed to a worker kind that isn't running has no effect."""
    launcher = make_launcher({"worker": 5})
    worker_count = {"web": 1}

    to_create, to_destroy = launcher._calculate_worker_changes(worker_count)

    assert list(to_create["web"]) == [1]
    assert to_destroy == {}
    assert worker_count == {"web": 1}


def test_each_kind_scaled_independently() -> None:
    """Mixed deltas scale each worker kind on its own count."""
    launcher = make_launcher({"web": 1, "worker": -1})
    worker_count = {"web": 1, "worker": 2}

    to_create, to_destroy = launcher._calculate_worker_changes(worker_count)

    assert list(to_create["web"]) == [1, 2]
    assert list(to_create["worker"]) == [1]
    assert "web" not in to_destroy
    assert list(to_destroy["worker"]) == [2]
    assert worker_count == {"web": 2, "worker": 1}


def test_zero_delta_behaves_like_no_delta() -> None:
    """An explicit zero delta is falsy and leaves the worker count unchanged."""
    launcher = make_launcher({"web": 0})
    worker_count = {"web": 2}

    to_create, to_destroy = launcher._calculate_worker_changes(worker_count)

    assert list(to_create["web"]) == [1, 2]
    assert to_destroy == {}
    assert worker_count == {"web": 2}
