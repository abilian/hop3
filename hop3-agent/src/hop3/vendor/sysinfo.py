# Copyright (c) 2023-2024, Abilian SAS

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import time
from pathlib import Path

import attr


def cache(timeout):
    def decorator(func):
        def wrapper(self, *args, **kwargs):
            cache_key = func.__name__
            cached_result = self._get_cached_result(cache_key, timeout)
            if cached_result is not None:
                return cached_result

            result = func(self, *args, **kwargs)
            self._set_cache(cache_key, result)
            return result

        return wrapper

    return decorator


@attr.frozen
class SysInfo:
    _cache: dict = attr.field(factory=dict)

    #
    # Cache
    #
    def _get_cached_result(self, key, timeout):
        if key in self._cache:
            result, timestamp = self._cache[key]
            if time.time() - timestamp < timeout:
                return result
        return None

    def _set_cache(self, key, value):
        self._cache[key] = (value, time.time())

    #
    # Arch / OS
    #
    def platform_name(self):
        return platform.system()

    @cache(60)
    def system_arch(self):
        return self._run_command("dpkg --print-architecture")

    @cache(60)
    def system_virt(self):
        return self._run_command("systemd-detect-virt || true")

    @cache(60)
    def distrib_codename(self):
        return self._lsb_release("c")

    @cache(60)
    def distrib_version(self):
        return self._lsb_release("r")

    def free_space_in_directory(self, dirpath):
        stat = os.statvfs(dirpath)
        return stat.f_frsize * stat.f_bavail

    #
    # Disk
    #
    @cache(3600)
    def get_total_disk_space(self):
        return str(shutil.disk_usage("/")[0] // (2**30)) + "GB"

    @cache(3600)
    def get_available_disk_space(self):
        return str(shutil.disk_usage("/")[2] // (2**30)) + "GB"

    #
    # Network
    #
    @cache(3600)
    def get_host_name(self):
        return self._run_command("hostname")

    @cache(3600)
    def get_ip_address(self):
        try:
            result = self._run_command("ip route get 1")
            return result.split("src ")[1].split(" ")[0] if result else None
        except Exception:
            return None

    @cache(3600)
    def has_ipv6(self):
        return Path("/proc/net/if_inet6").exists()

    #
    # CPU
    #
    @cache(3600)
    def get_cpu_core(self):
        try:
            result = self._run_command("lscpu | grep socket:")
            return result.split(":")[1].strip(" ").strip("\\n'") if result else None
        except Exception:
            return None

    #
    # HDD
    #
    @cache(3600)
    def get_hd_size(self):
        try:
            result = self._run_command("sudo lshw -class disk | grep size")
            return result.split("(", 1)[1].split(")")[0] if result else None
        except Exception:
            return None

    @cache(3600)
    def get_hd_type(self):
        try:
            result = self._run_command(
                "sudo lshw -class disk -class storage | grep description"
            )
            return result.split("\\n")[0].split(":")[1].strip(" ") if result else None
        except Exception:
            return None

    #
    # Vendor
    #
    @cache(3600)
    def get_manufacturer(self):
        return self._run_command("sudo dmidecode -s system-manufacturer")[2:-3]

    @cache(3600)
    def get_model(self):
        return self._run_command("sudo dmidecode -s system-product-name")[2:-3]

    @cache(3600)
    def get_serial_number(self):
        return self._run_command("sudo dmidecode -s system-serial-number")[2:-3]

    #
    # RAM
    #
    @cache(3600)
    def get_ram_type(self):
        try:
            cmd = 'sudo dmidecode --type 17 | grep -B 2 "Type Detail: Synchronous" | grep -w "Type:"'
            result = self._run_command(cmd)
            return result.split("\tType:")[1].strip(" ").strip("\n") if result else None
        except Exception:
            return None

    @cache(3600)
    def get_ram_size(self):
        try:
            cmd = "grep MemTotal /proc/meminfo"
            result = self._run_command(cmd)
            ram_size = round(int(result.split()[1]) / 1024000) if result else None
            return str(ram_size) + " GB" if ram_size else None
        except Exception:
            return None

    #
    # Internal
    #
    def _lsb_release(self, key):
        return self._run_command(f"lsb_release -s{key}")

    def _run_command(self, cmd):
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, shell=True)
            return result.stdout.decode().strip()
        except subprocess.CalledProcessError:
            return None
