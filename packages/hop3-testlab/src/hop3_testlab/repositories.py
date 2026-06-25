# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Read repositories over the shared result-store models.

These read the ``hop3_testing.results`` models (the shared schema). Trend/diff/
flakiness queries are added as the dashboard grows; for now: recent runs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from hop3_testing.results.compression import decompress
from hop3_testing.results.models import BuildLog, RunLease, TestResultRecord, TestRun
from sqlalchemy import select

from hop3_testlab import leasing
from hop3_testlab.discriminators import type_of
from hop3_testlab.models import (
    CANCELLED,
    QUEUED,
    RUNNING,
    BuildRequest,
    Credential,
    Profile,
    Server,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class RunsRepository:
    """Read access to test runs."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_recent(self, limit: int = 20) -> list[TestRun]:
        """Return the most recent runs (with a run_uid), newest first.

        Legacy rows without a run_uid are skipped — they can't be linked to a
        detail page.
        """
        stmt = (
            select(TestRun)
            .where(TestRun.run_uid.isnot(None))
            .order_by(TestRun.started_at.desc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt).all())

    def get(self, run_uid: str) -> TestRun | None:
        """Return the run with this user-facing run_uid."""
        stmt = select(TestRun).where(TestRun.run_uid == run_uid)
        return self.session.scalars(stmt).one_or_none()

    def latest_by_trigger(self, trigger: str) -> TestRun | None:
        """The most-recent run carrying this provenance ``trigger`` (e.g. a
        dispatcher's ``build-<id>`` tag), used to link a build to its run."""
        stmt = (
            select(TestRun)
            .where(TestRun.trigger == trigger)
            .order_by(TestRun.started_at.desc(), TestRun.id.desc())
            .limit(1)
        )
        return self.session.scalars(stmt).one_or_none()

    def results_for(self, run: TestRun) -> list[TestResultRecord]:
        """Return a run's test results, failed-first then by name."""
        stmt = (
            select(TestResultRecord)
            .where(TestResultRecord.run_id == run.id)
            .order_by(TestResultRecord.passed.asc(), TestResultRecord.test_name.asc())
        )
        return list(self.session.scalars(stmt).all())

    def progress_by_type(self, run: TestRun) -> dict[str, dict[str, int]]:
        """Per-type ``{done, passed, failed}`` for a run's results so far.

        Types are app / demo / tutorial (see ``discriminators.type_of``), keyed
        identically to the engine's planned counts so the live panel can show
        "done / planned" per type.
        """
        out = {
            t: {"done": 0, "passed": 0, "failed": 0}
            for t in ("app", "demo", "tutorial")
        }
        for record in self.results_for(run):
            bucket = out.setdefault(
                type_of(record.test_name), {"done": 0, "passed": 0, "failed": 0}
            )
            bucket["done"] += 1
            if record.passed:
                bucket["passed"] += 1
            else:
                bucket["failed"] += 1
        return out

    def previous_run(self, run: TestRun) -> TestRun | None:
        """Return the most recent earlier run of the same mode (for the diff)."""
        stmt = (
            select(TestRun)
            .where(TestRun.mode == run.mode, TestRun.started_at < run.started_at)
            .order_by(TestRun.started_at.desc())
            .limit(1)
        )
        return self.session.scalars(stmt).one_or_none()

    def result_by_bundle(self, bundle_run_id: str) -> TestResultRecord | None:
        """Return the result carrying this bundle id (the `why` key)."""
        stmt = (
            select(TestResultRecord)
            .where(TestResultRecord.bundle_run_id == bundle_run_id)
            .order_by(TestResultRecord.id.desc())
        )
        return self.session.scalars(stmt).first()

    def target_busy(self, target_id: str) -> bool:
        """True if a run currently holds the target's lease (UX pre-check)."""
        return leasing.is_held(self.session, target_id)

    # --- live "current run" support (dashboard panel + stop) ------------------

    def current_lease(self) -> RunLease | None:
        """The live lease (something is running now), or None when idle."""
        return leasing.current_lease(self.session)

    def active_run(self) -> TestRun | None:
        """The in-flight run: newest with no ``finished_at`` yet, or None.

        There is at most one at a time: the lease serialises runs and
        ``sweep_orphans`` (called at lease-acquire) clears any row a prior
        crashed/killed run left unfinished, so the newest-unfinished row is the
        live one. May be None in the brief window after the lease is taken but
        before the engine's ``start_run`` has created the row.
        """
        stmt = (
            select(TestRun)
            .where(TestRun.finished_at.is_(None), TestRun.run_uid.isnot(None))
            .order_by(TestRun.started_at.desc())
            .limit(1)
        )
        return self.session.scalars(stmt).one_or_none()

    def recent_completed(
        self, mode: str, target_type: str | None = None, limit: int = 5
    ) -> list[TestRun]:
        """Recent *finished* runs of the same scope — the ETA history basis."""
        stmt = select(TestRun).where(
            TestRun.finished_at.isnot(None), TestRun.mode == mode
        )
        if target_type:
            stmt = stmt.where(TestRun.target_type == target_type)
        stmt = stmt.order_by(TestRun.started_at.desc()).limit(limit)
        return list(self.session.scalars(stmt).all())

    def abort_active(self, by: str) -> TestRun | None:
        """Mark the in-flight run as aborted (stamps ``finished_at`` + metadata).

        The engine was killed mid-run so it never called ``finish_run``; this is
        the authoritative finish so the run stops showing as live and is labelled
        'interrupted' rather than lingering forever.
        """
        run = self.active_run()
        if run is None:
            return None
        run.finished_at = datetime.now(timezone.utc)
        meta = dict(run.run_metadata or {})
        meta["aborted"] = True
        meta["aborted_by"] = by
        run.run_metadata = meta  # reassign so SQLAlchemy flags the JSON dirty
        self.session.commit()
        return run

    def sweep_orphans(self) -> int:
        """Stamp every lingering in-flight run as aborted; return the count.

        A run killed mid-flight (e.g. via the Stop control) or crashed never
        calls ``finish_run``, so it keeps ``finished_at`` NULL forever and would
        masquerade as the live run under the next lease (``active_run`` returns
        the newest unfinished row). Called at lease-acquire time: v1 runs one
        suite at a time, so any unfinished row at that moment is an orphan from a
        previous run. Revisit the unscoped sweep when targets run concurrently.
        """
        orphans = list(
            self.session.scalars(
                select(TestRun).where(TestRun.finished_at.is_(None))
            ).all()
        )
        for run in orphans:
            run.finished_at = datetime.now(timezone.utc)
            meta = dict(run.run_metadata or {})
            meta.setdefault("aborted", True)
            meta.setdefault("aborted_by", "orphan-sweep")
            run.run_metadata = meta  # reassign so SQLAlchemy flags the JSON dirty
        if orphans:
            self.session.commit()
        return len(orphans)

    def release_lease(self, target_id: str) -> None:
        """Drop the target's lease (stop path; caller isn't the holder)."""
        leasing.force_release(self.session, target_id)

    def get_result(self, result_id: int) -> TestResultRecord | None:
        """Return one build's result record."""
        return self.session.get(TestResultRecord, result_id)

    def build_logs(self, result_id: int) -> list[dict]:
        """Return a build's decompressed per-phase logs, in capture order."""
        stmt = (
            select(BuildLog)
            .where(BuildLog.test_result_id == result_id)
            .order_by(BuildLog.id.asc())
        )
        return [
            {"phase": r.phase, "text": decompress(r.algo, r.data), "size": r.size}
            for r in self.session.scalars(stmt)
        ]

    def pass_fail_history(self, limit_runs: int = 10) -> dict[str, list[bool]]:
        """Per-test pass/fail outcomes over the last N runs, oldest-first.

        Feeds the flakiness ranking. N is small, so the per-run fetch is fine.
        """
        recent = self.session.scalars(
            select(TestRun).order_by(TestRun.started_at.desc()).limit(limit_runs)
        ).all()
        history: dict[str, list[bool]] = {}
        for run in reversed(recent):  # oldest first
            for result in self.results_for(run):
                history.setdefault(result.test_name, []).append(bool(result.passed))
        return history


# --- Lab-owned write repos (profiles / server pool / build queue) -------------


class ProfilesRepository:
    """CRUD over build profiles (a Lab-owned table)."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_all(self) -> list[Profile]:
        return list(self.session.scalars(select(Profile).order_by(Profile.name)).all())

    def get(self, profile_id: int) -> Profile | None:
        return self.session.get(Profile, profile_id)

    def by_name(self, name: str) -> Profile | None:
        return self.session.scalars(
            select(Profile).where(Profile.name == name)
        ).one_or_none()

    def create(self, **fields) -> Profile:
        profile = Profile(**fields)
        self.session.add(profile)
        self.session.flush()
        return profile

    def update(self, profile_id: int, **fields) -> Profile | None:
        profile = self.session.get(Profile, profile_id)
        if profile is None:
            return None
        for key, value in fields.items():
            setattr(profile, key, value)
        self.session.flush()
        return profile

    def delete(self, profile_id: int) -> bool:
        profile = self.session.get(Profile, profile_id)
        if profile is None:
            return False
        self.session.delete(profile)
        self.session.flush()
        return True


class ServersRepository:
    """CRUD over the server pool (a Lab-owned table)."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_all(self, *, enabled_only: bool = False) -> list[Server]:
        stmt = select(Server).order_by(Server.name)
        if enabled_only:
            stmt = stmt.where(Server.enabled.is_(True))
        return list(self.session.scalars(stmt).all())

    def get(self, server_id: int) -> Server | None:
        return self.session.get(Server, server_id)

    def create(self, **fields) -> Server:
        server = Server(**fields)
        self.session.add(server)
        self.session.flush()
        return server

    def update(self, server_id: int, **fields) -> Server | None:
        server = self.session.get(Server, server_id)
        if server is None:
            return None
        for key, value in fields.items():
            setattr(server, key, value)
        self.session.flush()
        return server

    def delete(self, server_id: int) -> bool:
        server = self.session.get(Server, server_id)
        if server is None:
            return False
        self.session.delete(server)
        self.session.flush()
        return True


class CredentialsRepository:
    """CRUD over cloud-provider credentials (a Lab-owned table). Holds secrets."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_all(self) -> list[Credential]:
        stmt = select(Credential).order_by(Credential.name)
        return list(self.session.scalars(stmt).all())

    def get(self, credential_id: int) -> Credential | None:
        return self.session.get(Credential, credential_id)

    def active(self, kind: str) -> Credential | None:
        """The active credential of ``kind`` (the one the worker uses)."""
        # ponytail: first row of this kind is "the active one". A `default` flag /
        # per-Server selection arrives in Slice 2 (several accounts in parallel).
        stmt = (
            select(Credential)
            .where(Credential.kind == kind)
            .order_by(Credential.name)
        )
        return self.session.scalars(stmt).first()

    def create(self, **fields) -> Credential:
        credential = Credential(**fields)
        self.session.add(credential)
        self.session.flush()
        return credential

    def delete(self, credential_id: int) -> bool:
        credential = self.session.get(Credential, credential_id)
        if credential is None:
            return False
        self.session.delete(credential)
        self.session.flush()
        return True


class BuildQueueRepository:
    """The build queue (a Lab-owned table): enqueue + lifecycle transitions."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def enqueue(self, profile_id: int, actor: str | None = None) -> BuildRequest:
        request = BuildRequest(profile_id=profile_id, actor=actor)
        self.session.add(request)
        self.session.flush()
        return request

    def get(self, request_id: int) -> BuildRequest | None:
        return self.session.get(BuildRequest, request_id)

    def list_recent(self, limit: int = 50) -> list[BuildRequest]:
        stmt = (
            select(BuildRequest)
            .order_by(BuildRequest.created_at.desc(), BuildRequest.id.desc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt).all())

    def list_running(self) -> list[BuildRequest]:
        """All requests currently marked running (for the stale-run sweep)."""
        stmt = select(BuildRequest).where(BuildRequest.status == RUNNING)
        return list(self.session.scalars(stmt).all())

    def next_pending(self) -> BuildRequest | None:
        """The oldest still-queued request (FIFO), or None."""
        stmt = (
            select(BuildRequest)
            .where(BuildRequest.status == QUEUED)
            .order_by(BuildRequest.created_at, BuildRequest.id)
            .limit(1)
        )
        return self.session.scalars(stmt).one_or_none()

    def mark(self, request_id: int, status: str, **fields) -> BuildRequest | None:
        request = self.session.get(BuildRequest, request_id)
        if request is None:
            return None
        request.status = status
        for key, value in fields.items():
            setattr(request, key, value)
        self.session.flush()
        return request

    def cancel(self, request_id: int) -> bool:
        """Cancel a *pending* request (a no-op once it's been dispatched)."""
        request = self.session.get(BuildRequest, request_id)
        if request is None or request.status != QUEUED:
            return False
        request.status = CANCELLED
        self.session.flush()
        return True
