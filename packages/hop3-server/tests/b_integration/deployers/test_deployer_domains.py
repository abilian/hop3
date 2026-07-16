# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for the [domains] -> HOST_NAME deployment path.

Drives ``_process_config_dependencies`` end-to-end with a real hop3.toml on
disk, a real AppConfig, a real App in an in-memory database, and verifies
that HOST_NAME lands in env_vars correctly across the policy / conflict /
no-op axes the unit tests cover at finer grain.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hop3.deployers.deployer import _process_config_dependencies
from hop3.lib.console import Abort
from hop3.orm import App, AppRepository, EnvVar
from hop3.project.config import AppConfig
from hop3.project.schema import Hop3TomlValidationError

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.orm import Session


def _write_hop3_toml(app_dir: Path, content: str) -> None:
    """Write a hop3.toml inside the layout AppConfig.from_dir expects."""
    src = app_dir / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "hop3.toml").write_text(content)


def _make_app(db_session: Session, name: str) -> App:
    app = App(name=name)
    AppRepository(session=db_session).add(app, auto_commit=True)
    return app


def _host_name(app: App) -> str | None:
    for env_var in app.env_vars:
        if env_var.name == "HOST_NAME":
            return env_var.value
    return None


@pytest.mark.integration
def test_domains_translates_to_host_name(tmp_path: Path, db_session: Session) -> None:
    """A fresh app with [domains].list gets HOST_NAME populated, space-joined."""
    _write_hop3_toml(
        tmp_path,
        """
[domains]
list = ["abilian.com", "www.abilian.com", "fermigier.com"]
""",
    )
    app = _make_app(db_session, "testapp")
    app_config = AppConfig.from_dir(tmp_path)

    _process_config_dependencies(app, app_config, db_session)

    assert _host_name(app) == "abilian.com www.abilian.com fermigier.com"


@pytest.mark.integration
def test_domains_empty_list_is_noop(tmp_path: Path, db_session: Session) -> None:
    """list = [] must not write or unset HOST_NAME."""
    _write_hop3_toml(
        tmp_path,
        """
[domains]
list = []
""",
    )
    app = _make_app(db_session, "testapp")
    # Pre-existing HOST_NAME — empty list must leave it alone.
    app.env_vars.append(EnvVar(name="HOST_NAME", value="preset.example.com", app=app))
    db_session.commit()

    app_config = AppConfig.from_dir(tmp_path)
    _process_config_dependencies(app, app_config, db_session)

    assert _host_name(app) == "preset.example.com"


@pytest.mark.integration
def test_domains_keep_existing_policy_preserves_manual_value(
    tmp_path: Path, db_session: Session
) -> None:
    """Default policy keep-existing must not clobber a manually set HOST_NAME
    (e.g., one set via ``hop3 config set`` or ``hop3 domains add`` between
    deploys)."""
    _write_hop3_toml(
        tmp_path,
        """
[domains]
list = ["declared.example.com"]
""",
    )
    app = _make_app(db_session, "testapp")
    app.env_vars.append(EnvVar(name="HOST_NAME", value="manual.example.com", app=app))
    db_session.commit()

    app_config = AppConfig.from_dir(tmp_path)
    _process_config_dependencies(app, app_config, db_session)

    assert _host_name(app) == "manual.example.com"


@pytest.mark.integration
def test_domains_override_policy_replaces_manual_value(
    tmp_path: Path, db_session: Session
) -> None:
    """policy = override must reapply the hop3.toml value on every deploy."""
    _write_hop3_toml(
        tmp_path,
        """
[domains]
list = ["declared.example.com", "www.declared.example.com"]
_policy = "override"
""",
    )
    app = _make_app(db_session, "testapp")
    app.env_vars.append(EnvVar(name="HOST_NAME", value="manual.example.com", app=app))
    db_session.commit()

    app_config = AppConfig.from_dir(tmp_path)
    _process_config_dependencies(app, app_config, db_session)

    assert _host_name(app) == "declared.example.com www.declared.example.com"


@pytest.mark.integration
def test_domains_conflict_with_other_app_aborts_deploy(
    tmp_path: Path, db_session: Session
) -> None:
    """If another app already holds the hostname, the deploy must abort."""
    # Another app already claims abilian.com (space-separated storage,
    # the canonical post-deploy form).
    other = _make_app(db_session, "otherapp")
    other.env_vars.append(
        EnvVar(name="HOST_NAME", value="abilian.com www.abilian.com", app=other)
    )
    db_session.commit()

    _write_hop3_toml(
        tmp_path,
        """
[domains]
list = ["abilian.com"]
""",
    )
    app = _make_app(db_session, "newapp")
    app_config = AppConfig.from_dir(tmp_path)

    with pytest.raises(Abort) as exc:
        _process_config_dependencies(app, app_config, db_session)
    assert "otherapp" in str(exc.value)
    assert "abilian.com" in str(exc.value)
    # The conflicting app's binding must not have been disturbed.
    assert _host_name(other) == "abilian.com www.abilian.com"
    # The new app must NOT have HOST_NAME set.
    assert _host_name(app) is None


@pytest.mark.integration
def test_env_hostname_and_domains_rejected_by_schema(tmp_path: Path) -> None:
    """The schema must reject hop3.toml that sets both env.HOST_NAME and
    [domains] — the failure happens at parse time, before the deployer
    runs."""
    _write_hop3_toml(
        tmp_path,
        """
[env]
HOST_NAME = "via-env.example.com"

[domains]
list = ["via-domains.example.com"]
""",
    )
    with pytest.raises(Hop3TomlValidationError):
        AppConfig.from_dir(tmp_path)


@pytest.mark.integration
def test_domains_produce_public_url(tmp_path: Path, db_session: Session) -> None:
    """[domains].list -> HOST_NAME -> HOP3_PUBLIC_URL in the same deploy."""
    _write_hop3_toml(
        tmp_path,
        """
[domains]
list = ["shop.example.com", "www.shop.example.com"]
""",
    )
    app = _make_app(db_session, "testapp")
    app_config = AppConfig.from_dir(tmp_path)

    _process_config_dependencies(app, app_config, db_session)

    env = {ev.name: ev.value for ev in app.env_vars}
    assert env.get("HOP3_PUBLIC_URL") == "https://shop.example.com"


@pytest.mark.integration
def test_public_url_available_to_computed_vars(
    tmp_path: Path, db_session: Session
) -> None:
    """Ordering is load-bearing: set_public_url_env runs before [env.computed],
    so a recipe's ${HOP3_PUBLIC_URL} resolves in the same deploy."""
    _write_hop3_toml(
        tmp_path,
        """
[domains]
list = ["shop.example.com"]

[env.computed]
APP_URL = "${HOP3_PUBLIC_URL}"
""",
    )
    app = _make_app(db_session, "testapp")
    app_config = AppConfig.from_dir(tmp_path)

    _process_config_dependencies(app, app_config, db_session)

    env = {ev.name: ev.value for ev in app.env_vars}
    assert env.get("APP_URL") == "https://shop.example.com"
