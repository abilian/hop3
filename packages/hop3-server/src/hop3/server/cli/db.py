# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Server-side CLI commands for database schema management.

These commands wrap Alembic so callers (operators, the deployer) do not
need to know the alembic.ini path or the venv layout. The deployer calls
``hop3-server db:upgrade`` after installing a new package and before
restarting the server.
"""

from __future__ import annotations

import sys
from pathlib import Path

from hop3.lib.registry import register

from ._base import Command

_UNSTAMPED_HINTS = (
    "duplicate column name",  # SQLite — column added by create_all()
    "already exists",  # SQLite/PG — table/column already there
    "DuplicateColumn",  # PG psycopg2
    "DuplicateTable",  # PG psycopg2
)


def _looks_like_unstamped_db(exc: BaseException) -> bool:
    """Heuristic: an upgrade error whose message smells like a pre-alembic DB.

    The signature of this case is alembic running the first migration's
    DDL against a DB that already has the resulting objects, because the
    schema was created via metadata.create_all() before alembic was
    introduced. The fix is db:stamp, not db:upgrade.
    """
    msg = str(exc)
    return any(hint in msg for hint in _UNSTAMPED_HINTS)


def _database_url() -> str:
    """Resolve the DB URL the same way ``alembic/env.py`` does.

    Must agree with env.py (and ``orm.session.get_session_factory``) so the
    adoption check below inspects the very database the migrations will run
    against.
    """
    import os  # noqa: PLC0415

    from hop3 import config as c  # noqa: PLC0415

    return os.environ.get("HOP3_DATABASE_URI") or f"sqlite:///{c.HOP3_ROOT}/hop3.db"


def _adopt_unstamped_db(cfg) -> None:
    """Make an unstamped database safe to ``upgrade`` from base.

    Hop3 historically created its schema via ``metadata.create_all()`` and
    never stamped Alembic (orm/session.py falls back to create_all). Such a
    DB already has the current tables/columns but no ``alembic_version`` row,
    so a plain ``upgrade`` replays every migration from base and the first
    real delta dies with "duplicate column".

    We detect that state and stamp the *base* revision, then let the caller
    run ``upgrade``: the delta migrations are idempotent (they skip columns
    that already exist), so adoption applies only what is genuinely missing —
    correct whether the create_all DB is at head or slightly behind.

    Cases:
    - already stamped        -> no-op (normal upgrade follows)
    - unstamped + populated  -> stamp base (adopt), then upgrade fills gaps
    - unstamped + empty       -> create_all + stamp head (the initial
      migration is an empty placeholder, so it cannot build the schema)
    """
    from alembic import command  # noqa: PLC0415
    from alembic.runtime.migration import MigrationContext  # noqa: PLC0415
    from alembic.script import ScriptDirectory  # noqa: PLC0415
    from sqlalchemy import create_engine, inspect  # noqa: PLC0415

    engine = create_engine(_database_url())
    try:
        with engine.connect() as conn:
            current = MigrationContext.configure(conn).get_current_revision()
            has_app = inspect(conn).has_table("app")

        if current is not None:
            return  # already under Alembic's control

        if has_app:
            base = ScriptDirectory.from_config(cfg).get_bases()[0]
            print(
                f"Adopting pre-Alembic database (schema present, unstamped): "
                f"stamping base {base} so only missing migrations apply.",
                file=sys.stderr,
            )
            command.stamp(cfg, base)
        else:
            # Empty DB: the initial migration is an empty placeholder, so it
            # can't create the schema. Build it from the models and stamp head.
            from hop3.orm.app import App  # noqa: PLC0415

            print(
                "Empty database: creating schema from models and stamping head.",
                file=sys.stderr,
            )
            App.metadata.create_all(engine)
            command.stamp(cfg, "head")
    finally:
        engine.dispose()


def _alembic_config():
    """Build a programmatic Alembic Config pointing at the bundled alembic.ini.

    Resolving the path from ``hop3.__file__`` works whether the package is
    installed normally, editable, or run from a wheel — wherever the
    ``hop3`` package lives, the ``alembic.ini`` and ``alembic/`` directory
    ship alongside it.
    """
    from alembic.config import Config  # noqa: PLC0415

    import hop3  # noqa: PLC0415

    pkg_root = Path(hop3.__file__).parent
    ini_path = pkg_root / "alembic.ini"
    if not ini_path.exists():
        msg = f"alembic.ini not found at {ini_path}"
        raise FileNotFoundError(msg)
    cfg = Config(str(ini_path))
    # The bundled alembic/env.py resolves the database URL from Hop3 config,
    # so we don't need to set sqlalchemy.url here.
    return cfg


@register
class DbCmd(Command):
    """Manage the database schema (migrations).

    Subcommands:
        db:upgrade   Run pending migrations to bring the schema up to date
        db:current   Show the current alembic revision
        db:stamp     Mark the DB at a specific revision without running migrations

    Use 'hop3-server db:<subcommand> --help' for details.
    """

    name = "db"


@register
class DbUpgradeCmd(Command):
    """Run pending migrations.

    Usage:
        hop3-server db:upgrade [--revision REV]

    By default, upgrades to ``head`` (latest revision). Pass ``--revision``
    to target a specific revision (e.g. for staged rollouts).

    This command is idempotent: running it when the DB is already at the
    target revision is a no-op.

    Examples:
        hop3-server db:upgrade
        hop3-server db:upgrade --revision 961bfd2ecce5
    """

    name = "db:upgrade"

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--revision",
            default="head",
            help="Target revision (default: head)",
        )

    def run(self, revision: str = "head") -> None:
        from alembic import command  # noqa: PLC0415

        cfg = _alembic_config()
        try:
            # Adopt a pre-Alembic (create_all, unstamped) DB before upgrading,
            # so `upgrade` applies only genuinely-missing migrations instead of
            # replaying from base against an already-complete schema.
            _adopt_unstamped_db(cfg)
            command.upgrade(cfg, revision)
        except Exception as exc:
            print(f"Error: migration failed: {exc}", file=sys.stderr)
            if _looks_like_unstamped_db(exc):
                print(
                    "\nHint: this database appears to predate Alembic — its "
                    "schema was created via metadata.create_all() and was "
                    "never stamped with a revision. To mark it as current "
                    "without running migrations, run:\n\n"
                    "    hop3-server db:stamp head\n\n"
                    "Then re-run db:upgrade to apply any future migrations.",
                    file=sys.stderr,
                )
            sys.exit(1)


@register
class DbCurrentCmd(Command):
    """Show the current alembic revision.

    Usage:
        hop3-server db:current

    Output is the revision identifier (or empty if the DB has never been
    stamped). Useful for verifying a deployment landed on the expected
    schema, or for diagnosing pre-alembic databases that need stamping.
    """

    name = "db:current"

    def run(self) -> None:
        from alembic import command  # noqa: PLC0415

        cfg = _alembic_config()
        try:
            command.current(cfg)
        except Exception as exc:
            print(f"Error: could not read current revision: {exc}", file=sys.stderr)
            sys.exit(1)


@register
class DbStampCmd(Command):
    """Mark the DB at a specific revision without running migrations.

    Usage:
        hop3-server db:stamp <revision>

    This rewrites the ``alembic_version`` table to record the given
    revision as current, without executing any migration scripts.

    Use this for databases created from ``metadata.create_all()`` (i.e.
    before Alembic was introduced) so subsequent ``db:upgrade`` runs only
    apply newer migrations. Typical rescue flow:

        hop3-server db:stamp head        # tell alembic the schema is current
        # ... later, after new migrations exist ...
        hop3-server db:upgrade           # applies only the new ones
    """

    name = "db:stamp"

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "revision",
            help="Revision to stamp (e.g. 'head' or a specific hash)",
        )

    def run(self, revision: str) -> None:
        from alembic import command  # noqa: PLC0415

        cfg = _alembic_config()
        try:
            command.stamp(cfg, revision)
        except Exception as exc:
            print(f"Error: stamp failed: {exc}", file=sys.stderr)
            sys.exit(1)
