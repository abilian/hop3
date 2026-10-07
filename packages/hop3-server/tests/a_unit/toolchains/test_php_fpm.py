# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
"""
The php-fpm pool the PHP toolchain builds.

Ten catalog apps served through a single-threaded `php -S`; Nextcloud and
Matomo deadlock against their own only worker. php-fpm runs as a uWSGI
attach-daemon so the Emperor stays the only process manager (ADR 023).
"""

from __future__ import annotations

import pytest

from hop3.lib import Abort
from hop3.run.fastcgi import FCGI_PING_PATH
from hop3.toolchains import php_fpm
from hop3.toolchains.php_fpm import (
    POOL_CONFIG_NAME,
    POOL_TEMPLATE_NAME,
    document_root,
    php_fpm_binary,
    pool_config,
    render_pool_config,
    web_command,
)


class TestTheDocumentRootIsNotAlwaysTheProjectRoot:
    def test_a_front_controller_directory_wins(self, tmp_path) -> None:
        """Serving the project root would publish .env and the vendor tree."""
        (tmp_path / "public").mkdir()
        (tmp_path / "public" / "index.php").touch()
        (tmp_path / ".env").write_text("APP_KEY=secret\n")
        assert document_root(tmp_path) == tmp_path / "public"

    @pytest.mark.parametrize("name", ["public", "web", "htdocs", "www"])
    def test_each_known_convention_is_recognised(self, tmp_path, name) -> None:
        (tmp_path / name).mkdir()
        (tmp_path / name / "index.php").touch()
        assert document_root(tmp_path) == tmp_path / name

    def test_a_directory_without_a_front_controller_is_not_it(self, tmp_path) -> None:
        """WordPress has a `web` of its own that is not a document root."""
        (tmp_path / "web").mkdir()
        (tmp_path / "index.php").touch()
        assert document_root(tmp_path) == tmp_path

    def test_a_flat_project_serves_its_root(self, tmp_path) -> None:
        (tmp_path / "index.php").touch()
        assert document_root(tmp_path) == tmp_path

    def test_a_recipe_can_say_so_itself(self, tmp_path) -> None:
        (tmp_path / "public").mkdir()
        (tmp_path / "public" / "index.php").touch()
        (tmp_path / "httpdocs").mkdir()
        assert document_root(tmp_path, "httpdocs") == tmp_path / "httpdocs"

    def test_a_declared_root_above_the_project_aborts(self, tmp_path) -> None:
        """`..` is a directory, and serving it publishes the app's neighbours."""
        project = tmp_path / "src"
        project.mkdir()
        with pytest.raises(Abort, match="inside the application source"):
            document_root(project, "..")

    def test_a_declared_root_that_does_not_exist_aborts(self, tmp_path) -> None:
        with pytest.raises(Abort) as excinfo:
            document_root(tmp_path, "nope")
        assert "[build].document-root" in str(excinfo.value)

    def test_the_abort_names_the_key_a_recipe_can_actually_set(self, tmp_path) -> None:
        """
        It used to name `PHP_DOCUMENT_ROOT`, an environment variable read from
        a file nothing writes — so the message sent a reader to a knob that
        could not work.
        """
        with pytest.raises(Abort) as excinfo:
            document_root(tmp_path, "nope")
        assert "PHP_DOCUMENT_ROOT" not in str(excinfo.value)


class TestThePoolAnswersTheReadinessGate:
    def test_it_exposes_the_ping_path_the_probe_asks_for(self, tmp_path) -> None:
        config = pool_config("myapp", tmp_path / "php-fpm.log")
        assert f"ping.path = {FCGI_PING_PATH}" in config

    def test_it_runs_in_the_foreground(self, tmp_path) -> None:
        """An attach-daemon that forks away is a daemon uWSGI cannot supervise."""
        assert "daemonize = no" in pool_config("myapp", tmp_path / "l.log")

    def test_worker_output_reaches_the_app_log(self, tmp_path) -> None:
        """Otherwise a PHP fatal is dropped and the app fails undiagnosably."""
        config = pool_config("myapp", tmp_path / "php-fpm.log")
        assert "catch_workers_output = yes" in config
        assert str(tmp_path / "php-fpm.log") in config

    def test_the_pool_is_named_for_the_app(self, tmp_path) -> None:
        assert "[myapp]" in pool_config("myapp", tmp_path / "l.log")

    def test_the_port_is_left_for_start_time(self, tmp_path) -> None:
        """It is allocated at deploy, so it cannot be baked in at build."""
        config = pool_config("myapp", tmp_path / "l.log")
        assert "listen = 127.0.0.1:__HOP3_PORT__" in config


class TestTheWebCommand:
    """
    The command has to survive being `exec`'d.

    `uwsgi.worker` wraps every worker as ``sh -c "cd … ; exec <command>"``, so
    the command must be one program. It used to be
    ``sed … > … && exec php-fpm …``: `exec` landed on `sed`, replacing the
    shell, and php-fpm was never reached — the pool did not start once, on any
    app. These tests replaced ones that asserted that string's *shape*, which
    is how a command that could not work had passing tests.
    """

    def test_it_runs_the_pool(self, tmp_path) -> None:
        command = web_command("/usr/sbin/php-fpm8.3", tmp_path)
        assert command.startswith("/usr/sbin/php-fpm8.3 ")
        assert str(tmp_path / POOL_CONFIG_NAME) in command

    def test_it_is_one_program_so_exec_lands_on_the_pool(self, tmp_path) -> None:
        """
        The caller prepends `exec`. Any shell operator here would put it on
        the wrong word, and the pool would never be what uWSGI supervises.
        """
        command = web_command("/usr/sbin/php-fpm8.3", tmp_path)
        for operator in ("&&", "||", ";", "|", ">", "<"):
            assert operator not in command, (
                f"{operator!r} makes this compound, so the caller's `exec` "
                f"would apply to its first word instead of php-fpm"
            )

    def test_it_does_not_name_the_template(self, tmp_path) -> None:
        """The template is rendered before the worker runs, not by it."""
        command = web_command("/usr/sbin/php-fpm8.3", tmp_path)
        assert str(tmp_path / POOL_TEMPLATE_NAME) not in command

    def test_the_pool_stays_in_the_foreground(self, tmp_path) -> None:
        """A daemon that forks away is one uWSGI cannot supervise."""
        assert "--nodaemonize" in web_command("/usr/sbin/php-fpm8.3", tmp_path)


class TestThePoolPassesTheAppsEnvironment:
    """
    php-fpm clears a worker's environment by default, and Hop3 injects every
    addon credential as an environment variable. Without `clear_env = no` a
    PHP app is the one runtime on the platform that cannot read the database
    it was provisioned.
    """

    def test_the_environment_reaches_the_workers(self, tmp_path) -> None:
        assert "clear_env = no" in pool_config("myapp", tmp_path / "l.log")


class TestRenderingThePool:
    def test_the_port_replaces_the_placeholder(self, tmp_path) -> None:
        rendered = render_pool_config(pool_config("myapp", tmp_path / "l.log"), "41781")
        assert "listen = 127.0.0.1:41781" in rendered

    def test_nothing_is_left_to_substitute(self, tmp_path) -> None:
        rendered = render_pool_config(pool_config("myapp", tmp_path / "l.log"), "41781")
        assert "__HOP3_PORT__" not in rendered


class TestFindingTheBinary:
    def test_a_versioned_name_is_accepted(self, monkeypatch) -> None:
        """Debian ships php-fpm8.3; the unversioned name is often absent."""
        monkeypatch.setattr(
            php_fpm.shutil,
            "which",
            lambda name: "/usr/sbin/php-fpm8.3" if name == "php-fpm8.3" else None,
        )
        assert php_fpm_binary() == "/usr/sbin/php-fpm8.3"

    def test_no_php_fpm_aborts_at_build_time(self, monkeypatch) -> None:
        """Not as a vassal crash-looping five minutes later."""
        monkeypatch.setattr(php_fpm.shutil, "which", lambda name: None)
        with pytest.raises(Abort) as excinfo:
            php_fpm_binary()
        assert "php-fpm" in str(excinfo.value)
        assert "apt-get install php-fpm" in str(excinfo.value)
