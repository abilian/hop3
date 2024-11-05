# Copyright (c) 2023-2024, Abilian SAS

import os
import shutil
import sys
from pathlib import Path

import tomlkit
from cleez.colors import red
from dotenv import load_dotenv
from invoke import Context, UnexpectedExit, task

load_dotenv()

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"


SUB_REPOS = [
    "hop3-lib",
    "hop3-agent",
    "hop3-cli",
    "hop3-server",
    "hop3-web",
    "hop3-testing",
]

RSYNC_EXCLUDES = [
    # ".git",
    ".env",
    ".venv",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    ".nox",
    ".tox",
    ".cache",
    ".coverage",
]

try:
    from abilian_devtools.invoke import import_tasks

    import_tasks(globals())
except ImportError:
    pass


#
# Subrepos tasks
#
@task
def install(c, quiet=False):
    """Install all sub-packages (and dependencies)"""
    # first uninstall all
    c.run(
        "pip list --format freeze | grep -E '^hop3-' | xargs pip uninstall -yq &>/dev/null",
        warn=True,
    )

    opts = []
    if quiet:
        opts.append("-qq")
    options = " ".join(opts)

    if shutil.which("uv"):
        # c.run(f"uv pip install {options} --no-cache-dir -e .")
        run_in_subrepos(c, f"uv sync --inexact {options}")
        run_in_subrepos(c, f"uv pip install {options} --no-cache-dir -e .")
    else:
        # c.run(f"pip install {options} --no-cache-dir -e .")
        run_in_subrepos(c, f"pip install {options} --no-cache-dir -e .")


@task
def install_dev(c, quiet=False):
    """Install all sub-packages (and dependencies, including dev)"""
    # first uninstall all
    c.run(
        "pip list --format freeze | grep -E '^hop3-' | xargs pip uninstall -yq &>/dev/null",
        warn=True,
    )

    c.run("poetry install")
    run_in_subrepos(c, "poetry install")


@task
def lint(c):
    """Lint (static check) the whole project."""
    # c.run("ruff check .")
    # c.run("pre-commit run --all-files")

    run_in_subrepos(c, "make lint")


@task
def format(c):  # noqa: A001
    """Format the whole project."""
    run_in_subrepos(c, "make format")


@task
def test(c):
    """Run tests (in each subrepo)."""
    run_in_subrepos(c, "make test")


@task
def test_with_coverage(c):
    """(broken) Run tests with coverage (and combine results)."""
    run_in_subrepos(c, "pytest --cov hop3")
    c.run("coverage combine */.coverage")
    # c.run("codecov --file .coverage")


@task
def mypy(c):
    """Run mypy (in each subrepo)."""
    run_in_subrepos(c, "mypy src")


@task
def pyright(c):
    """Run pyright (in each subrepo)."""
    run_in_subrepos(c, "pyright src")


@task
def clean(c):
    """Clean the whole project."""
    run_in_subrepos(c, "make clean")


@task
def fix(c):
    """Run ruff fixes in all subrepos."""
    run_in_subrepos(c, "ruff --fix src tests")


@task
def run(c, cmd: str):
    """Run given command in all subrepos."""
    run_in_subrepos(c, cmd)


@task
def update(c):
    """Update dependencies the whole project."""
    c.run("uv sync -U --inexact")
    c.run("pre-commit autoupdate")

    run_in_subrepos(c, "poetry update && poetry install")
    run_in_subrepos(c, "pre-commit autoupdate")


#
# Other tasks
#
@task
def bump_version(c, bump: str = "patch"):
    """Update version - use 'patch' (default), 'minor' or 'major' as an argument."""

    c.run(f"poetry version {bump}")

    # Set same version in all subrepos
    version = get_version()
    run_in_subrepos(c, f"poetry version {version}")


@task
def graph(c):
    """Generate dependency graph in all subprojects."""
    run_in_subrepos(c, "mkdir -p doc")
    for sub_repo in SUB_REPOS:
        output = "doc/dependency-graph.png"
        target = f"src/{sub_repo.replace('-', '_')}"
        cmd = f"pydeps --max-bacon 2 --cluster -o {output} -T png {target}"
        h1(f"Running '{cmd}' in subrepos: {sub_repo}")
        with c.cd(sub_repo):
            c.run(cmd)


@task
def watch(c, host=None):
    """Watch for changes and push to a remote server."""
    import watchfiles

    if not host:
        host = os.environ.get("HOP3_HOST")
    if not host:
        print(
            "Please set HOP3_HOST env var or "
            "pass it as an argument (--host=example.com)."
        )
        sys.exit()

    excludes_args = " ".join([f"--exclude={e}" for e in RSYNC_EXCLUDES])

    # TODO: fix
    def sync():
        print(f"{BOLD}Syncing to remote server (hop3@{host})...{DIM}")
        c.run(f"rsync -e ssh -avz {excludes_args} ./ root@{host}:/home/hop3/hop3-src/")

    sync()
    for _changes in watchfiles.watch("."):
        print("Changes detected, syncing...")
        sync()


#
# Release task
#


@task
def release(c: Context):
    """Release a new version."""
    c.run("make clean")

    version = get_version()

    try:
        c.run("git diff --quiet")
    except UnexpectedExit:
        print("Your repo is dirty. Please commit or stash changes first.")
        sys.exit(1)

    h1("Checking versions are all set properly...")
    for sub_repo in SUB_REPOS:
        check_version_subrepo(c, sub_repo, version)

    c.run(f"git checkout -b release-{version}")

    for sub_repo in SUB_REPOS:
        release_subrepo(c, sub_repo, version)

    c.run(f"git commit -a -m 'Release {version}'")

    c.run("git checkout release")
    c.run(f"git merge release-{version}")
    c.run(f"git commit -a -m 'Release {version}'")
    c.run(f"git tag -a v{version} -m 'Release {version}'")
    c.run("git push origin release")
    c.run("git push --tags")

    c.run("git checkout main")


def check_version_subrepo(c, sub_repo, version):
    with c.cd(sub_repo):
        sub_version = get_version()

        if sub_version != version:
            print(
                f"{RED}ERROR: version mismatch for {sub_repo}: "
                f"expected {version}, got {sub_version}{RESET}"
            )
            sys.exit(1)


def release_subrepo(c: Context, sub_repo, version):
    h1(f"Releasing {sub_repo}...")

    pyproject_path = Path(sub_repo, "pyproject.toml")
    old_pyproject = pyproject_path.read_text()
    pyproject_json = tomlkit.loads(old_pyproject)

    # TODO: fixme
    if pyproject_json["tool"]["poetry"]["name"] == "hop3-cli":
        pyproject_json["tool"]["poetry"]["name"] = "hop3"

    deps = pyproject_json["tool"]["poetry"]["dependencies"]
    new_deps = {}
    for dep in deps:
        if dep.startswith("hop3-"):
            new_deps[dep] = f"={version}"
        else:
            new_deps[dep] = deps[dep]

    pyproject_json["tool"]["poetry"]["dependencies"] = new_deps
    pyproject_path.write_text(tomlkit.dumps(pyproject_json))

    with c.cd(sub_repo):
        c.run("poetry build")
        try:
            c.run("twine upload dist/*")
        except:  # noqa: E722
            print(red("ERROR: Release failed. Continuing anyway"))


#
# Helpers
#
def h1(msg):
    print()
    print(BOLD + msg + RESET)
    print()


def run_in_subrepos(c, cmd):
    for sub_repo in SUB_REPOS:
        h1(f"Running '{cmd}' in subrepos: {sub_repo}")
        with c.cd(sub_repo):
            c.run(cmd)
        print()


def get_version():
    pyproject_json = tomlkit.loads(Path("pyproject.toml").read_text())
    return pyproject_json["tool"]["poetry"]["version"]
