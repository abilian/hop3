---
date: 2026-04-17
template: blog_post.html
description: Making Hop3 run on Ubuntu, Debian, Fedora, Rocky, and more.
tags:
  - Engineering
  - Installation
---

# Building a Multi-Distribution Installer

Hop3 runs on Ubuntu, Debian, Fedora, Rocky Linux, and AlmaLinux. Making this work required solving some surprisingly tricky problems around package names, version detection, and distribution-specific quirks.

## The Challenge

When you write `apt-get install docker`, you expect it to work. But:

- On Debian 12, the package is `docker.io`
- On Ubuntu 24.04, it's also `docker.io`, but with different companion packages
- On Fedora, it's `moby-engine` (Fedora's Docker fork)
- On Rocky/AlmaLinux, there's no Docker package at all in the base repos

Multiply this by every dependency (Python, Node, Go, databases, etc.) and you have a maintenance nightmare.

## Our Solution

We built a distribution-aware installer with three layers:

### 1. Distribution Detection

First, we detect which distribution we're running on:

```python
def detect_distro() -> DistroInfo:
    """Detect the current Linux distribution."""
    if Path("/etc/os-release").exists():
        info = parse_os_release()
        return DistroInfo(
            id=info.get("ID", "unknown"),
            version=info.get("VERSION_ID", ""),
            codename=info.get("VERSION_CODENAME", ""),
            family=_get_family(info.get("ID_LIKE", "")),
        )
    # Fallback detection...
```

This gives us structured information:

```python
DistroInfo(
    id="ubuntu",
    version="24.04",
    codename="noble",
    family="debian",
)
```

### 2. Family-Based Handlers

We group distributions into families with shared setup strategies. On the server side these live in `hop3-server`'s OS plugins (`packages/hop3-server/src/hop3/plugins/oses/`), each pairing a base mixin with a family strategy:

```
debian_base.py / debian_family.py  → Debian, Ubuntu, Linux Mint, Pop!_OS
redhat_base.py / redhat_family.py  → Fedora, Rocky, AlmaLinux, CentOS, RHEL
arch.py                            → Arch, Manjaro, EndeavourOS
bsd.py, macos.py                   → BSD and macOS targets
```

A strategy detects its family from `/etc/os-release` and installs the base system (nginx, certbot, Python, the language toolchains, PostgreSQL). The distro-specific package juggling for Docker, backports, and external repositories lives alongside the server installer (`hop3-installer`'s `server_installer/deps_*.py`), which is where the examples below come from.

Each handler implements the same interface:

```python
class DebianInstaller:
    def install_packages(self, packages: list[str]) -> None:
        subprocess.run(["apt-get", "install", "-y", *packages])

    def add_repository(self, repo: str) -> None:
        # Add to sources.list.d
        ...

    def get_docker_packages(self) -> list[str]:
        # Version-specific logic
        ...
```

### 3. Version-Specific Logic

Here's where it gets interesting. Docker packages vary by distribution *and* version:

```python
def _get_docker_packages(distro: DistroInfo) -> list[str]:
    """Get Docker packages for this distribution."""

    if distro.id == "debian":
        if distro.version >= "13":  # Trixie
            return ["docker.io", "docker-compose", "docker-buildx"]
        else:  # Bookworm and older
            return ["docker.io", "docker-compose"]

    elif distro.id == "ubuntu":
        if distro.version >= "24.04":
            return ["docker.io", "docker-compose-v2", "docker-buildx"]
        else:
            return ["docker.io", "docker-compose"]

    elif distro.family == "fedora":
        if _is_rhel_clone(distro):  # Rocky, Alma
            # No native packages, use Docker's repo
            _setup_docker_repo_for_rhel()
            return [
                "docker-ce",
                "docker-ce-cli",
                "containerd.io",
                "docker-buildx-plugin",
                "docker-compose-plugin",
            ]
        else:  # Fedora
            return ["moby-engine", "docker-compose"]
```

## Real Problems We Solved

### Problem 1: Python Version on RHEL Clones

Rocky Linux 9 ships with Python 3.9 as the default, but also has Python 3.12 available. Our virtualenvs were being created with 3.9, causing compatibility issues.

**Solution**: Find the best available Python:

```python
def _find_best_python() -> str:
    """Find the best Python interpreter (prefer newer versions)."""
    candidates = [
        "/usr/bin/python3.12",
        "/usr/bin/python3.11",
        "/usr/bin/python3.10",
        "/usr/bin/python3",
    ]
    for python in candidates:
        if Path(python).exists():
            result = subprocess.run(
                [python, "--version"],
                capture_output=True,
            )
            if result.returncode == 0:
                return python
    return "/usr/bin/python3"
```

### Problem 2: uWSGI Package Variations

uWSGI packages are a mess across distributions:

- Debian: `uwsgi`, `uwsgi-plugin-python3`
- Ubuntu: Similar, but different plugin names
- Fedora: `uwsgi`, `uwsgi-plugin-python3`
- Rocky: No packages at all

**Solution**: Install uWSGI via pip in Hop3's virtualenv:

```python
def install_uwsgi():
    """Install uWSGI in Hop3's venv (consistent across distros)."""
    venv_pip = Path("/home/hop3/venv/bin/pip")
    subprocess.run([str(venv_pip), "install", "uwsgi"])
```

This sidesteps fragile per-distro plugin detection entirely: the base package lists no longer carry a system `uwsgi` at all, and every distribution ends up with the same interpreter and the same uWSGI build.

### Problem 3: Backports for Debian Stable

Debian Stable freezes its toolchains for the life of a release, so the stock Go on Bookworm lags behind what many apps expect. Rather than mix releases, we pull a newer Go from the matching `-backports` suite.

**Solution**: Enable backports and install from there:

```python
def _setup_debian_backports(distro: DistroInfo):
    """Add Debian backports repository."""
    if distro.codename == "bookworm":
        backports = f"deb http://deb.debian.org/debian {distro.codename}-backports main"
        sources_file = Path(f"/etc/apt/sources.list.d/{distro.codename}-backports.list")
        sources_file.write_text(backports)
        subprocess.run(["apt-get", "update"])

def install_go(distro: DistroInfo):
    if distro.id == "debian" and distro.codename == "bookworm":
        # Install from backports
        subprocess.run([
            "apt-get", "install", "-y",
            "-t", "bookworm-backports",
            "golang-go"
        ])
    else:
        subprocess.run(["apt-get", "install", "-y", "golang-go"])
```

### Problem 4: RHEL Clones Need External Repos

Rocky Linux and AlmaLinux don't ship Docker packages. You need Docker's official repository.

**Solution**: Detect RHEL clones and add the repo:

```python
def _is_rhel_clone(distro: DistroInfo) -> bool:
    """Check if this is a RHEL clone (Rocky, Alma, CentOS)."""
    return distro.id in ("rocky", "almalinux", "centos")

def _setup_docker_repo_for_rhel():
    """Add Docker's official CentOS repository."""
    subprocess.run([
        "dnf", "config-manager", "--add-repo",
        "https://download.docker.com/linux/centos/docker-ce.repo"
    ])
```

## Testing Across Distributions

We use Hetzner Cloud to spin up VMs for each distribution. The `hop3-test cloud` command drives a single image, a list, or the whole matrix:

```bash
# Test on Ubuntu 24.04
hop3-test cloud --image ubuntu-24.04

# Test on Rocky Linux 9
hop3-test cloud --image rocky-9

# Test several at once
hop3-test cloud --images debian-13,fedora-42,alma-9

# Or the full matrix
hop3-test cloud --images all

# List the images we know about
hop3-test cloud --list-images
```

Each test:
1. Creates a fresh VM
2. Runs the installer
3. Deploys test applications
4. Verifies everything works
5. Tears down the VM

This catches distribution-specific issues before they reach users.

## Lessons Learned

1. **Don't assume package names**: Always verify on each distribution
2. **Version matters**: `docker-compose` vs `docker-compose-v2` broke things
3. **Pip is your friend**: Installing tools via pip avoids distro package chaos
4. **Test on real systems**: Containers hide differences from the host OS
5. **Document everything**: Future you will forget why Rocky needs special handling

## Distributions We Target

Detection is family-based: a strategy matches on `ID` or `ID_LIKE` from `/etc/os-release`, so Debian and Red Hat derivatives generally come along for the ride even when we don't name them explicitly. The images we exercise in CI are:

| Family | Image we test | Notes |
|--------|---------------|-------|
| Debian | Debian 13 (trixie) | Plus Ubuntu derivatives via the same strategy |
| Ubuntu | Ubuntu 24.04 LTS | Default, best-exercised target |
| Fedora | Fedora 42 | Native `moby-engine`, recent toolchains |
| Rocky Linux | Rocky 9 | RHEL 9 clone, Docker from Docker's repo |
| AlmaLinux | Alma 9 | RHEL 9 clone, Docker from Docker's repo |

Arch, BSD, and macOS strategies also exist for development targets; the curated CI matrix above is what we lean on for server installs.

## Try It

Install Hop3 on your distribution:

```bash
curl -LsSf https://hop3.cloud/install-server.py | sudo python3 -
```

The installer will detect your distribution and do the right thing.

---

*Have a distribution we don't support? [Open an issue](https://github.com/abilian/hop3/issues) and we'll look into it.*
