# Copyright (c) 2023-2025, Abilian SAS

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import attr


def cache(timeout):
    """Decorator to cache the result of a function with a specified timeout.

    Input:
    - timeout: The duration for which the result should be cached.

    Returns:
    - decorator: A function wrapper that caches the result of the decorated function.
    """

    def decorator(func):
        def wrapper(self, *args, **kwargs):
            # Generate a cache key based on the function's name
            cache_key = func.__name__

            # Attempt to retrieve a cached result using the cache key and timeout
            cached_result = self._get_cached_result(cache_key, timeout)

            # If a cached result is found, return it
            if cached_result is not None:
                return cached_result

            # Otherwise, call the actual function, cache its result, and return it
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
    def _get_cached_result(self, key, timeout) -> Any:
        """Retrieve a cached result if it exists and is not expired.

        Input:
            key: The key associated with the cached result.
            timeout: The time period (in seconds) after which the cached result is considered expired.

        Returns:
            The cached result associated with the key if it is present and not expired; otherwise, None.
        """
        if key in self._cache:
            result, timestamp = self._cache[key]
            if time.time() - timestamp < timeout:
                return result
        return None

    def _set_cache(self, key, value) -> None:
        """Store a value in the cache with the corresponding key and the
        current timestamp.

        Input:
        - key: The key under which the value will be stored in the cache.
        - value: The value to be stored in the cache.
        """
        self._cache[key] = (value, time.time())

    #
    # Arch / OS
    #
    def platform_name(self) -> str:
        """Retrieve the name of the operating system platform.

        Returns:
            str: The system/OS name, e.g. 'Linux', 'Windows', or 'Java'.
        """
        return platform.system()

    @cache(60)
    def system_arch(self) -> str:
        return self._run_command("dpkg --print-architecture")

    @cache(60)
    def system_virt(self) -> str:
        return self._run_command("systemd-detect-virt || true")

    @cache(60)
    def distrib_codename(self) -> str:
        return self._lsb_release("c")

    @cache(60)
    def distrib_version(self) -> str:
        return self._lsb_release("r")

    def free_space_in_directory(self, dirpath):
        """Calculate the free space available in a given directory.

        Input:
        - dirpath: A string representing the path to the directory for which the
                   free space is to be calculated.

        Returns:
        - An integer value representing the available free space in bytes.

        Raises:
        - OSError: If the directory path does not exist or is not accessible.
        """
        stat = os.statvfs(
            dirpath
        )  # Get file system statistics for the given directory path
        return (
            stat.f_frsize * stat.f_bavail
        )  # Calculate free space using fragment size and available blocks

    #
    # Disk
    #
    @cache(3600)
    def get_total_disk_space(self) -> str:
        return str(shutil.disk_usage("/")[0] // (2**30)) + "GB"

    @cache(3600)
    def get_available_disk_space(self) -> str:
        return str(shutil.disk_usage("/")[2] // (2**30)) + "GB"

    #
    # Network
    #
    @cache(3600)
    def get_host_name(self) -> str:
        return self._run_command("hostname")

    @cache(3600)
    def get_ip_address(self) -> str:
        try:
            result = self._run_command("ip route get 1")
            return result.split("src ")[1].split(" ")[0] if result else ""
        except Exception:
            return ""

    @cache(3600)
    def has_ipv6(self) -> bool:
        return Path("/proc/net/if_inet6").exists()

    #
    # CPU
    #
    @cache(3600)
    def get_cpu_core(self) -> str:
        try:
            result = self._run_command("lscpu | grep socket:")
            return result.split(":")[1].strip(" ").strip("\\n'") if result else ""
        except Exception:
            return ""

    #
    # HDD
    #
    @cache(3600)
    def get_hd_size(self) -> str:
        try:
            result = self._run_command("sudo lshw -class disk | grep size")
            return result.split("(", 1)[1].split(")")[0] if result else ""
        except Exception:
            return ""

    @cache(3600)
    def get_hd_type(self) -> str:
        try:
            result = self._run_command(
                "sudo lshw -class disk -class storage | grep description"
            )
            return result.split("\\n")[0].split(":")[1].strip(" ") if result else ""
        except Exception:
            return ""

    #
    # Vendor
    #
    @cache(3600)
    def get_manufacturer(self) -> str:
        return self._run_command("sudo dmidecode -s system-manufacturer")[2:-3]

    @cache(3600)
    def get_model(self) -> str:
        return self._run_command("sudo dmidecode -s system-product-name")[2:-3]

    @cache(3600)
    def get_serial_number(self) -> str:
        return self._run_command("sudo dmidecode -s system-serial-number")[2:-3]

    #
    # RAM
    #
    @cache(3600)
    def get_ram_type(self) -> str:
        try:
            cmd = 'sudo dmidecode --type 17 | grep -B 2 "Type Detail: Synchronous" | grep -w "Type:"'
            result = self._run_command(cmd)
            return result.split("\tType:")[1].strip(" ").strip("\n") if result else ""
        except Exception:
            return ""

    @cache(3600)
    def get_ram_size(self) -> str:
        try:
            cmd = "grep MemTotal /proc/meminfo"
            result = self._run_command(cmd)
            ram_size = round(int(result.split()[1]) / 1024000) if result else None
            return str(ram_size) + " GB" if ram_size else ""
        except Exception:
            return ""

    #
    # Internal
    #
    def _lsb_release(self, key) -> str:
        """Retrieves the Linux Standard Base (LSB) release information for a
        given key.

        Input:
        - key: A string representing the specific LSB release information to retrieve (e.g., description, codename, etc.).

        Returns:
        - A string containing the LSB release information corresponding to the given key.
        """
        # Executes the 'lsb_release' command with specified key and returns its output
        return self._run_command(f"lsb_release -s{key}")

    def _run_command(self, cmd) -> str:
        """Executes a shell command and returns its standard output.

        Input:
        - cmd: A string representing the command to be executed in the shell.

        Returns:
        - A string containing the standard output of the executed command, stripped of leading and trailing whitespace.

        Raises:
        - Does not raise an exception but returns an empty string if the command fails to execute successfully.
        """
        try:
            # Run the command with output capture and shell execution
            result = subprocess.run(cmd, check=True, capture_output=True, shell=True)
            return result.stdout.decode().strip()
        except subprocess.CalledProcessError:
            return ""
