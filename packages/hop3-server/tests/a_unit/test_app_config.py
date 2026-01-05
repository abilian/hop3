# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0
# SPDX-License-Identifier: MIT

from __future__ import annotations

from hop3.project.config import AppConfig

PROCFILE1 = """
web: gunicorn -w 4 -b
"""

PROCFILE2 = """
prebuild: echo "hello"
postbuild: echo "goodbye"
prerun: echo "prerun"

web: gunicorn -w 4 -b
cron: * * * * * echo "hello"
"""


def test_config_1(tmp_path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "Procfile").write_text(PROCFILE1)
    config = AppConfig.from_dir(tmp_path)
    assert config.web_workers == {"web": "gunicorn -w 4 -b"}
    assert config.workers == {"web": "gunicorn -w 4 -b"}

    config_dict = config.to_dict()
    expected = {
        "app_dir": str(tmp_path),
        "app_json": {},
        "has_procfile": True,
        "has_hop3_toml": False,
        "hop3_config": {},
        "procfile": {
            "post_build": "",
            "pre_build": "",
            "pre_run": "",
            "web_workers": {"web": "gunicorn -w 4 -b"},
            "workers": {"web": "gunicorn -w 4 -b"},
        },
        "src_dir": str(tmp_path / "src"),
    }
    assert config_dict == expected


def test_config_2(tmp_path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "Procfile").write_text(PROCFILE2)
    config = AppConfig.from_dir(tmp_path)
    assert config.workers == {
        "web": "gunicorn -w 4 -b",
        "cron": '* * * * * echo "hello"',
        "prebuild": 'echo "hello"',
        "postbuild": 'echo "goodbye"',
        "prerun": 'echo "prerun"',
    }

    assert config.web_workers == {"web": "gunicorn -w 4 -b"}
    assert config.pre_build == 'echo "hello"'
    assert config.post_build == 'echo "goodbye"'
    assert config.pre_run == 'echo "prerun"'

    config_dict = config.to_dict()
    expected = {
        "app_dir": str(tmp_path),
        "app_json": {},
        "has_procfile": True,
        "has_hop3_toml": False,
        "hop3_config": {},
        "procfile": {
            "post_build": 'echo "goodbye"',
            "pre_build": 'echo "hello"',
            "pre_run": 'echo "prerun"',
            "web_workers": {"web": "gunicorn -w 4 -b"},
            "workers": {
                "cron": '* * * * * echo "hello"',
                "postbuild": 'echo "goodbye"',
                "prebuild": 'echo "hello"',
                "prerun": 'echo "prerun"',
                "web": "gunicorn -w 4 -b",
            },
        },
        "src_dir": str(tmp_path / "src"),
    }
    assert config_dict == expected


def test_hop3_toml_only(tmp_path) -> None:
    """Test configuration with only hop3.toml (no Procfile)."""
    (tmp_path / "src").mkdir()
    hop3_toml_content = """
[metadata]
id = "test-app"
version = "1.0.0"

[build]
before-build = ["npm install", "npm run build"]

[run]
start = "npm start"
before-run = "python manage.py migrate"
"""
    (tmp_path / "src" / "hop3.toml").write_text(hop3_toml_content)

    config = AppConfig.from_dir(tmp_path)
    assert config.has_procfile is False
    assert config.has_hop3_toml is True

    # Check that hop3.toml workers are available
    # NOTE: prebuild is NOT in workers because build.before-build is handled
    # by deployer.py._run_hook() during build phase, not as a worker daemon
    assert config.workers == {
        "web": "npm start",
        "prerun": "python manage.py migrate",
    }
    assert config.web_workers == {"web": "npm start"}
    assert config.pre_build == "npm install && npm run build"
    assert config.pre_run == "python manage.py migrate"


def test_both_procfile_and_hop3_toml_precedence(tmp_path) -> None:
    """Test that hop3.toml takes precedence over Procfile."""
    (tmp_path / "src").mkdir()

    # Create Procfile with some workers
    procfile_content = """
web: gunicorn app:app
prebuild: echo "procfile prebuild"
worker: celery worker
"""
    (tmp_path / "src" / "Procfile").write_text(procfile_content)

    # Create hop3.toml that overrides some workers
    hop3_toml_content = """
[build]
before-build = "echo 'hop3 prebuild'"

[run]
start = "uvicorn app:app"
before-run = "alembic upgrade head"
"""
    (tmp_path / "src" / "hop3.toml").write_text(hop3_toml_content)

    config = AppConfig.from_dir(tmp_path)
    assert config.has_procfile is True
    assert config.has_hop3_toml is True

    # hop3.toml should override 'web', but 'worker' and 'prebuild' from Procfile remain
    # NOTE: build.before-build from hop3.toml is NOT added to workers (handled by deployer)
    # but Procfile's prebuild worker IS kept since Procfiles define workers directly
    assert (
        config.workers
        == {
            "web": "uvicorn app:app",  # From hop3.toml (overrides Procfile)
            "worker": "celery worker",  # From Procfile (not in hop3.toml)
            "prebuild": 'echo "procfile prebuild"',  # From Procfile (hop3.toml before-build != worker)
            "prerun": "alembic upgrade head",  # From hop3.toml only
        }
    )
    assert config.web_workers == {"web": "uvicorn app:app"}
    # pre_build comes from hop3.toml's build.before-build (for hook execution)
    assert config.pre_build == "echo 'hop3 prebuild'"
    assert config.pre_run == "alembic upgrade head"


def test_no_config_files(tmp_path) -> None:
    """Test that AppConfig works with no Procfile or hop3.toml (empty defaults)."""
    (tmp_path / "src").mkdir()

    config = AppConfig.from_dir(tmp_path)
    assert config.has_procfile is False
    assert config.has_hop3_toml is False

    # Should have empty defaults
    assert config.workers == {}
    assert config.web_workers == {}
    assert config.pre_build == ""
    assert config.post_build == ""
    assert config.pre_run == ""

    # to_dict should work without errors
    config_dict = config.to_dict()
    assert config_dict["has_procfile"] is False
    assert config_dict["has_hop3_toml"] is False
    assert config_dict["procfile"]["workers"] == {}


def test_hop3_toml_with_list_commands(tmp_path) -> None:
    """Test hop3.toml with multiple commands in list format."""
    (tmp_path / "src").mkdir()
    hop3_toml_content = """
[build]
before-build = ["pip install -r requirements.txt", "python setup.py build"]

[run]
start = ["gunicorn app:app", "--bind 0.0.0.0:8000"]
"""
    (tmp_path / "src" / "hop3.toml").write_text(hop3_toml_content)

    config = AppConfig.from_dir(tmp_path)

    # List commands should be joined with &&
    assert (
        config.pre_build == "pip install -r requirements.txt && python setup.py build"
    )
    assert config.workers["web"] == "gunicorn app:app && --bind 0.0.0.0:8000"
