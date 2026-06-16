# Copyright (c) 2025, Abilian SAS
# test_generate_archive.py
from __future__ import annotations

import io
import tarfile
import tempfile
from pathlib import Path

from hop3_cli.commands.arguments import describe_archive, generate_archive

# hop3.toml whose [build].ignore is the canonical, declarative ignore list for
# the `hop3 deploy` upload (ADR 046 §5).
HOP3_TOML = """\
[metadata]
id = "demo"

[build]
ignore = [
    "*.log",
    "!important.log",
    "config.local.json",
    "dist/",
]
"""


def _names(archive_bytes: bytes) -> list[str]:
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as tar:
        return tar.getnames()


def test_build_ignore_drives_the_upload():
    """[build].ignore patterns (plus built-in defaults) decide what ships."""
    with tempfile.TemporaryDirectory() as temp_dir:
        project_dir = Path(temp_dir)
        (project_dir / "hop3.toml").write_text(HOP3_TOML)

        # Included
        (project_dir / "src").mkdir()
        (project_dir / "src" / "main.py").write_text("print('hi')")
        (project_dir / "README.md").write_text("# Demo")
        (project_dir / "important.log").write_text("keep me")

        # Excluded by [build].ignore
        (project_dir / "debug.log").touch()
        (project_dir / "config.local.json").touch()
        (project_dir / "dist").mkdir()
        (project_dir / "dist" / "bundle.js").touch()

        names = _names(generate_archive(project_dir))
        assert "src/main.py" in names
        assert "README.md" in names
        assert "hop3.toml" in names
        assert "important.log" in names  # negation re-includes it
        assert "debug.log" not in names
        assert "config.local.json" not in names
        assert "dist/bundle.js" not in names


def test_builtin_defaults_apply_without_any_config():
    """Caches/VCS/dep dirs are excluded even with no hop3.toml and no ignore file."""
    with tempfile.TemporaryDirectory() as temp_dir:
        project_dir = Path(temp_dir)
        (project_dir / "app.py").write_text("x = 1")  # an app indicator

        for rel in (
            "node_modules/left-pad/index.js",
            ".venv/bin/python",
            "__pycache__/app.cpython-312.pyc",
            "src/app.pyc",
            ".idea/workspace.xml",
            ".git/HEAD",
            "target/release/app",  # Rust/Maven build output — never deployed
        ):
            p = project_dir / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.touch()

        names = _names(generate_archive(project_dir))
        assert "app.py" in names
        assert not any(n.startswith("node_modules/") for n in names)
        assert not any(n.startswith(".venv/") for n in names)
        assert not any(n.startswith("__pycache__/") for n in names)
        assert not any(n.startswith(".git/") for n in names)
        assert not any(n.startswith("target/") for n in names)
        assert "src/app.pyc" not in names
        assert ".idea/workspace.xml" not in names


def test_gitignore_is_not_consulted_for_the_upload():
    """`.gitignore` governs the git-push path, not the `hop3 deploy` upload.

    Its patterns must NOT exclude anything here, and the file itself ships like
    any other source file.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        project_dir = Path(temp_dir)
        (project_dir / "app.py").write_text("x = 1")
        (project_dir / ".gitignore").write_text("secret.txt\n")
        (project_dir / "secret.txt").write_text("not actually ignored here")

        names = _names(generate_archive(project_dir))
        assert "secret.txt" in names  # .gitignore did NOT exclude it
        assert ".gitignore" in names  # shipped as a normal file


def test_dockerignore_does_not_govern_the_deploy_source():
    """`.dockerignore` scopes the server-side `docker build`, not this upload.

    Frameworks like Quarkus ship a `.dockerignore` of `*` + a `target/`
    allowlist; honoring it here would strip pom.xml/src and leave the server
    with "no language toolchain". Excluding build output is done via
    [build].ignore instead.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        project_dir = Path(temp_dir)
        (project_dir / ".dockerignore").write_text(
            "*\n!target/*-runner\n!target/quarkus-app/*\n"
        )
        (project_dir / "hop3.toml").write_text(
            '[metadata]\nid = "q"\n[build]\nignore = ["target/"]\n'
        )
        (project_dir / "pom.xml").write_text("<project/>")
        (project_dir / "src").mkdir()
        (project_dir / "src" / "App.java").write_text("class App {}")
        (project_dir / "target").mkdir()
        (project_dir / "target" / "App.class").touch()

        names = _names(generate_archive(project_dir))
        assert "pom.xml" in names  # not gutted by .dockerignore
        assert "src/App.java" in names
        assert "target/App.class" not in names  # excluded by [build].ignore


def test_hop3ignore_is_deprecated_but_still_honored(capsys):
    """A legacy `.hop3ignore` still works for one release, with a loud warning."""
    with tempfile.TemporaryDirectory() as temp_dir:
        project_dir = Path(temp_dir)
        (project_dir / "app.py").write_text("x = 1")
        (project_dir / ".hop3ignore").write_text("secret.txt\n")
        (project_dir / "secret.txt").write_text("ignored via deprecated file")

        names = _names(generate_archive(project_dir))
        assert "secret.txt" not in names  # honored
        assert "app.py" in names

        warning = capsys.readouterr().err
        assert ".hop3ignore" in warning
        assert "deprecated" in warning.lower()
        assert "[build].ignore" in warning


def test_build_ignore_takes_precedence_over_hop3ignore(capsys):
    """When [build].ignore is present, the deprecated .hop3ignore is not read."""
    with tempfile.TemporaryDirectory() as temp_dir:
        project_dir = Path(temp_dir)
        (project_dir / "hop3.toml").write_text(
            '[metadata]\nid = "d"\n[build]\nignore = ["a.txt"]\n'
        )
        (project_dir / ".hop3ignore").write_text("b.txt\n")
        (project_dir / "a.txt").touch()
        (project_dir / "b.txt").touch()

        names = _names(generate_archive(project_dir))
        assert "a.txt" not in names  # [build].ignore applied
        assert "b.txt" in names  # .hop3ignore NOT read
        assert ".hop3ignore" not in capsys.readouterr().err  # no deprecation warning


def test_describe_archive_shows_included_by_size_and_excludes_ignored():
    """`hop3 deploy --dry-run` manifest: included files by size, ignored gone."""
    with tempfile.TemporaryDirectory() as temp_dir:
        project_dir = Path(temp_dir)
        (project_dir / "hop3.toml").write_text('[build]\nignore = ["data/"]\n')
        (project_dir / "app.py").write_text("x = 1\n")
        # Big included file (the culprit a user would want to see).
        (project_dir / "media").mkdir()
        (project_dir / "media" / "video.mp4").write_bytes(b"0" * 3_000_000)
        # Excluded by [build].ignore — must NOT appear or count toward total.
        (project_dir / "data").mkdir()
        (project_dir / "data" / "dump.sql").write_bytes(b"0" * 9_000_000)
        # Excluded by built-in defaults.
        (project_dir / ".git").mkdir()
        (project_dir / ".git" / "blob").write_bytes(b"0" * 9_000_000)

        out = describe_archive(project_dir)

        assert "media/video.mp4" in out  # largest included file is surfaced
        assert "2.9 MB" in out  # human size of the 3,000,000-byte file
        assert "data/dump.sql" not in out  # ignored: not in manifest
        assert ".git" not in out  # built-in default: not in manifest
        # Total reflects only included files (~2.9 MB), not the 21 MB on disk.
        assert "Deploy archive: 2.9 MB" in out
