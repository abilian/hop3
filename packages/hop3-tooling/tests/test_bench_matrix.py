# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the benchmark matrix's pure logic (no box required)."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner
from hop3_tooling.bench.cli import main
from hop3_tooling.bench.matrix import (
    SERVER_ID_ENVVAR,
    VARIANTS,
    Cell,
    MatrixError,
    anchor,
    hcloud_env,
    load_corpus,
    parse_variants,
    reason_from,
    recipe_dir,
)
from hop3_tooling.bench.report import render_matrix


class TestLoadCorpus:
    """The corpus comes from the committed pre-registration, never a duplicate
    list in the runner — otherwise a run can drift from what was pre-registered.
    """

    def _protocol(self, tmp_path: Path, body: str) -> Path:
        path = tmp_path / "protocol.yaml"
        path.write_text(body)
        return path

    def test_reads_pre_registered_apps(self, tmp_path):
        protocol = self._protocol(
            tmp_path, "corpus:\n  name: golden\n  apps: [wordpress, gitea, isso]\n"
        )
        assert load_corpus(protocol) == ["wordpress", "gitea", "isso"]

    def test_missing_protocol_is_loud(self, tmp_path):
        with pytest.raises(MatrixError, match="pre-registration not found"):
            load_corpus(tmp_path / "nope.yaml")

    def test_empty_corpus_is_loud(self, tmp_path):
        """A gate that benchmarks nothing must not look like a green run."""
        protocol = self._protocol(tmp_path, "corpus:\n  name: golden\n  apps: []\n")
        with pytest.raises(MatrixError, match="refusing to benchmark nothing"):
            load_corpus(protocol)

    def test_the_real_protocol_is_loadable(self):
        """The committed protocol.yaml must stay machine-readable."""
        apps = load_corpus(Path("notes/benchmarks/protocol.yaml"))
        assert len(apps) >= 10
        assert "wordpress" in apps


class TestReasonFrom:
    """A failure whose cause was discarded is a silent skip; the per-variant
    reasons are the point of the exercise."""

    def test_prefers_the_precise_cause(self):
        log = "noise\nERROR: deploying app failed: build died\nmore noise"
        assert reason_from(log) == "ERROR: deploying app failed: build died"

    def test_falls_back_to_any_error_line(self):
        assert "timeout" in reason_from("started\nrequest timeout after 60s\n").lower()

    def test_never_returns_empty(self):
        assert reason_from("nothing interesting here") == "no diagnostic in log"

    def test_is_json_safe_and_bounded(self):
        reason = reason_from('ERROR: deploying app failed: say "hi" \\ ' + "x" * 500)
        assert '"' not in reason
        assert "\\" not in reason
        assert len(reason) <= 200


class TestParseVariants:
    def test_defaults_to_all(self):
        assert parse_variants("") == list(VARIANTS)

    def test_selects_a_subset(self):
        assert parse_variants("nix, nix-gen") == ["nix", "nix-gen"]

    def test_rejects_unknown(self):
        with pytest.raises(MatrixError, match="unknown variant"):
            parse_variants("nix,bogus")


def test_recipe_dir_maps_variant_to_apps_tree():
    assert recipe_dir(Path("/repo"), "nix-gen", "gitea") == Path(
        "/repo/apps/real-apps-nix-gen/gitea"
    )


class TestServerId:
    """The bench targets one dedicated box, named by the environment — never a
    hardcoded id, and never a box it creates."""

    def test_comes_from_the_environment(self, monkeypatch):
        monkeypatch.setenv(SERVER_ID_ENVVAR, "424242")
        result = CliRunner().invoke(main, ["matrix", "--help"])
        assert result.exit_code == 0
        assert SERVER_ID_ENVVAR in result.output  # documented in --help

    def test_missing_id_fails_loud(self, monkeypatch):
        """No id, no run — never fall back to guessing a box."""
        monkeypatch.delenv(SERVER_ID_ENVVAR, raising=False)
        result = CliRunner().invoke(main, ["matrix"])
        assert result.exit_code != 0
        assert "server-id" in result.output.lower()


class TestCell:
    def test_omits_empty_fields(self):
        record = Cell(app="gitea", variant="nix", status="no-recipe").to_json()
        assert '"seconds"' not in record
        assert '"reason"' not in record

    def test_keeps_failure_detail(self):
        record = Cell(
            app="gitea",
            variant="nix",
            status="failed",
            seconds=12,
            rc=1,
            reason="boom",
            log="logs/nix-gitea.log",
        ).to_json()
        for field in ('"seconds": 12', '"rc": 1', '"reason": "boom"', '"log"'):
            assert field in record


class TestHcloudEnv:
    """Hop3 sets HETZNER_API_TOKEN; the hcloud CLI reads HCLOUD_TOKEN. Without
    bridging them, hcloud falls back to its stored context and a rotated token
    shows up as a baffling 'unauthorized'."""

    def test_bridges_the_hop3_token_to_hclouds_name(self):
        env = hcloud_env({"HETZNER_API_TOKEN": "tok"})
        assert env["HCLOUD_TOKEN"] == "tok"

    def test_existing_hcloud_token_wins(self):
        env = hcloud_env({"HCLOUD_TOKEN": "explicit", "HETZNER_API_TOKEN": "other"})
        assert env["HCLOUD_TOKEN"] == "explicit"

    def test_no_token_at_all_is_loud(self):
        with pytest.raises(MatrixError, match="cannot reach the Hetzner API"):
            hcloud_env({})


class TestAnchor:
    """Output paths default to repo-relative. Leaving them relative crashed the
    first failed cell: `log_file.relative_to(root)` raised ValueError because the
    log path was relative while the root was absolute."""

    def test_relative_path_is_anchored_to_the_repo(self):
        root = Path("/repo")
        anchored = anchor(root, Path("notes/benchmarks/logs/run"))
        assert anchored == Path("/repo/notes/benchmarks/logs/run")

    def test_absolute_path_is_left_alone(self):
        assert anchor(Path("/repo"), Path("/tmp/elsewhere")) == Path("/tmp/elsewhere")

    def test_anchored_log_path_is_repo_relative(self):
        """The regression: a failed cell records its log path relative to root."""
        root = Path("/repo")
        log_file = anchor(root, Path("notes/benchmarks/logs/run")) / "native-wp.log"
        assert (
            str(log_file.relative_to(root)) == "notes/benchmarks/logs/run/native-wp.log"
        )


class TestReasonFromRealLogs:
    """Regression: the first matrix run reported the harness's own chatter
    ("Re-running 1 previously-failed test(s) first") as the failure cause,
    because the fallback matched any line containing "failed"."""

    def test_prefers_the_deploy_cause_over_generic_exit_code(self):
        log = (
            "Re-running 1 previously-failed test(s) first\n"
            "  Error: Deploy failed: Exit code: 1 | No connection details\n"
            "ERROR: deploying app failed: 'bugsink-1' has unpinned requirements\n"
        )
        assert reason_from(log) == (
            "ERROR: deploying app failed: 'bugsink-1' has unpinned requirements"
        )

    def test_reports_the_validation_failure(self):
        log = (
            "Re-running 1 previously-failed test(s) first\n"
            "  Error: HTTP 200 OK but body does not contain 'Hello world'\n"
        )
        assert reason_from(log).startswith(
            "Error: HTTP 200 OK but body does not contain"
        )

    def test_reports_the_classified_kind_when_that_is_all_there_is(self):
        log = "Failed tests:\n      x startup-failure - gitea-1784680115\n"
        assert "startup-failure" in reason_from(log)

    def test_never_reports_harness_bookkeeping(self):
        for noise in (
            "Re-running 1 previously-failed test(s) first",
            "No failures recorded.",
            "Failed tests:",
        ):
            assert reason_from(noise) == "no diagnostic in log"


class TestRenderMatrix:
    def test_averages_only_successful_cells(self):
        """A failed cell's duration is not the cost of a working deploy."""
        cells = [
            {"app": "a", "variant": "nix", "status": "ok", "seconds": 100},
            {"app": "b", "variant": "nix", "status": "ok", "seconds": 200},
            {"app": "c", "variant": "nix", "status": "failed", "seconds": 999},
            {"app": "d", "variant": "nix", "status": "no-recipe"},
        ]
        out = render_matrix(cells)
        assert (
            "| nix | 2 | 1 | 1 | 150 s | 150 s | 100-200 s |".replace("-", "\u2013")
            in out
        )
        assert "999" not in out.split("Failed cells:")[0]

    def test_lists_failed_cells_with_their_reason(self):
        cells = [
            {
                "app": "gitea",
                "variant": "nix-gen",
                "status": "failed",
                "seconds": 379,
                "reason": "startup-failure",
            }
        ]
        out = render_matrix(cells)
        assert "`nix-gen/gitea`" in out
        assert "startup-failure" in out


class TestAppendGuard:
    """Results files are date-named, so a same-day re-run collides. Appending
    would blend two runs — different box state — into one file that reads like a
    single measurement. The guard fires before any box operation."""

    def test_refuses_to_write_into_an_existing_results_file(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv(SERVER_ID_ENVVAR, "424242")
        existing = tmp_path / "run.jsonl"
        existing.write_text('{"app":"x","variant":"nix","status":"ok","seconds":1}\n')
        result = CliRunner().invoke(main, ["matrix", "--out", str(existing)])
        assert result.exit_code != 0
        assert "already exists" in result.output
        assert "--append" in result.output
        # the box was never touched: the guard runs first
        assert "rebuilding" not in result.output
