# Lessons Learned: Multi-Distribution Support

Running Hop3 across Debian, Ubuntu, Fedora, Rocky, and AlmaLinux.

## Package Name Divergence

The same software has different package names across distributions:

| Software | Debian 12 | Debian 13+ | Ubuntu 24.04+ | Fedora | Rocky/Alma |
|----------|-----------|------------|---------------|--------|------------|
| Docker | `docker.io` | `docker.io` | `docker.io` | `moby-engine` | (official repo) |
| Compose v2 | `docker-compose` (v1) | `docker-compose` (v2) | `docker-compose-v2` | `docker-compose` | `docker-compose-plugin` |
| Buildx | N/A | `docker-buildx` | `docker-buildx` | N/A | `docker-buildx-plugin` |
| uWSGI | varies | varies | varies | varies | varies |

**Lesson:** Never hardcode package names. Use version-specific logic (`_get_debian_docker_packages` for the Debian family, `_get_fedora_docker_packages` for Fedora/RHEL):

```python
def _get_debian_docker_packages(distro_info):
    packages = ["docker.io"]
    if distro_info.is_ubuntu and distro_info.version_major >= 24:
        packages += ["docker-compose-v2", "docker-buildx"]
    elif distro_info.is_debian and distro_info.version_major >= 13:
        packages += ["docker-cli", "docker-compose", "docker-buildx"]  # docker.io is daemon-only on trixie
    ...
    return packages
```

## uWSGI: Install via pip, Not Distro Packages

Distribution-packaged uWSGI has inconsistent plugin loading, version mismatches, and the `project` directive causes failures in strict mode on some distros.

**Fix:** Install uWSGI via pip in Hop3's own virtualenv. This gives consistent behavior across all distributions and eliminates 70+ lines of plugin detection code.

## Python Version Detection

RHEL 9 clones (Rocky, AlmaLinux) ship Python 3.9 as the default but have 3.12 available as an optional package. The virtualenv builder picks up the default 3.9, which is too old for many apps.

**Fix:** Probe for the best available Python (`_find_best_python` in `hop3/toolchains/python.py`):

```python
def _find_best_python():
    for python in ["/usr/bin/python3.12", "/usr/bin/python3.11",
                   "/usr/bin/python3.10", "/usr/bin/python3"]:
        if Path(python).exists():  # real code also runs `python --version` to confirm it works
            return python
    return "/usr/bin/python3"
```

## Debian Backports

Debian 12 (bookworm) has older versions of some packages. Don't add the trixie repo (wrong approach) - use bookworm-backports:

```bash
echo "deb http://deb.debian.org/debian bookworm-backports main" > \
    /etc/apt/sources.list.d/backports.list
apt-get update
apt-get install -t bookworm-backports golang
```

## Rocky/AlmaLinux Docker

RHEL clones don't include Docker in native repos. Must add Docker's official CentOS repo:

```bash
dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
dnf install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

## Shell Differences

- Debian/Ubuntu: `/bin/sh` is dash (no bashisms)
- Fedora/RHEL: `/bin/sh` is bash
- Hop3 scripts should use `/bin/bash` explicitly or avoid bashisms
- `source` is a bashism - use `. /path/to/script` instead

## Init System Detection: Use `/proc/1/comm`

Hop3 runs under both systemd (production VPS) and supervisord (Docker test containers). Detecting which one is in charge looks straightforward - until a first-draft check goes wrong and nothing runs.

**Don't** use these:

- `which systemctl && test -d /run/systemd/system` - both can exist on a container where systemd is *not* actually PID 1 (leftover from the base image).
- `systemctl is-system-running` - returns `offline` or `degraded` on containers; treating those as "systemd is alive" leads to `systemctl start postgresql` calls that fail silently, then `pg_isready` reports "not running", then the installer marks the install a failure.

**Do** use `/proc/1/comm`. PID 1's comm-name is unambiguous on Linux - it is either `systemd`, `init` (supervisord/containerd/sysvinit), or the custom PID-1 the container was started with:

```python
def has_systemd() -> bool:
    try:
        return Path("/proc/1/comm").read_text().strip() == "systemd"
    except OSError:
        return False
```

When `has_systemd()` is False, fall back to:

- `supervisorctl` for process control where supervisord is in use,
- `pg_ctlcluster` (Debian) / `pg_ctl` (Fedora) for PostgreSQL on non-systemd hosts,
- `pg_isready` as the init-agnostic "is Postgres accepting connections?" check.

Keep `has_systemd()` in one place (`hop3_installer/common.py`) so every caller uses the same rule.

## Bundler Name-Collision Detection

The Hop3 single-file installer concatenates module sources via `hop3-installer/bundler.py`. A sneaky failure mode: two modules define a top-level function with the same name. The second definition silently shadows the first at import time; the concatenated installer then uses whichever won, regardless of which caller intended which.

Concrete incident: both `nix.py` and `s3.py` defined a top-level `_has_systemd()`. The `s3.py` version (which returned `True` for "offline" systemd) won in the bundled output and took precedence over `nix.py`'s correct version. The Nix daemon was then installed in multi-user mode inside a supervisord container without systemd, and no Nix command worked. Many hours lost.

**Fix:** at bundle time, AST-parse each module, track top-level function / class / assignment names across the concatenated set, and raise on collision. The only legitimate duplicates are `@typing.overload` stubs (skipped inside `_top_level_names`) and intentional alias re-exports like `_has_systemd = has_systemd` (single-underscore assignments), so except those. The check is ~30 lines; it pays for itself the first time someone renames a helper.

```python
# In bundler.py — _top_level_names() skips @overload stubs
for name in _top_level_names(code):
    if name in seen_names:
        raise ValueError(
            f"Bundler name collision: '{name}' defined in both "
            f"{seen_names[name]} and {module_path}. Move the shared "
            "definition to common.py and import it."
        )
    seen_names[name] = module_path
```

Silent shadowing is the worst bug class here - the symptoms look like application-level bugs, not installer bugs, so no one thinks to look at the bundler.
