# Copyright (c) 2026, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for hop3.lib.sysinfo.

These tests exercise the pure logic of ``SysInfo``: its caching layer, the
output-parsing branches of the various ``get_*`` helpers, and ``_run_command``.

System probing methods normally consume real command output. To test the pure
parsing logic hermetically, we subclass ``SysInfo`` and override
``_run_command`` to feed sample data -- no filesystem or subprocess mocking is
needed (the class is ``attr.frozen``, so a subclass that returns a fixed value
is the cleanest stub).
"""

from __future__ import annotations

import hop3.lib.sysinfo as sysinfo_mod
from hop3.lib.sysinfo import SysInfo


def make_stub(output: str) -> SysInfo:
    """Return a SysInfo whose ``_run_command`` always yields ``output``."""

    class Stub(SysInfo):
        def _run_command(self, cmd):
            return output

    return Stub()


def make_counting_stub(output: str) -> tuple[SysInfo, dict]:
    """Return (SysInfo, counter) where ``_run_command`` increments counter."""
    counter = {"n": 0}

    class Stub(SysInfo):
        def _run_command(self, cmd):
            counter["n"] += 1
            return output

    return Stub(), counter


class TestPlatformName:
    def test_platform_name_is_supported_os(self) -> None:
        sys_info = SysInfo()

        # We only support Linux and macOS.
        assert sys_info.platform_name() in {"Linux", "Darwin"}


class TestCacheHelpers:
    def test_set_and_get_returns_value_within_timeout(self) -> None:
        sys_info = SysInfo()

        sys_info._set_cache("k", "val")

        assert sys_info._get_cached_result("k", 60) == "val"

    def test_get_missing_key_returns_none(self) -> None:
        sys_info = SysInfo()

        assert sys_info._get_cached_result("absent", 60) is None

    def test_get_expired_entry_returns_none(self, monkeypatch) -> None:
        sys_info = SysInfo()
        clock = {"t": 1000.0}
        monkeypatch.setattr(sysinfo_mod.time, "time", lambda: clock["t"])

        sys_info._set_cache("k", "val")
        clock["t"] = 1000.0 + 61  # past the 60s window

        assert sys_info._get_cached_result("k", 60) is None

    def test_get_zero_timeout_is_always_expired(self) -> None:
        sys_info = SysInfo()

        sys_info._set_cache("k", "val")

        # With timeout 0 the strict "< timeout" comparison never holds.
        assert sys_info._get_cached_result("k", 0) is None

    def test_falsy_value_is_distinguished_from_missing(self) -> None:
        sys_info = SysInfo()

        sys_info._set_cache("k", "")

        # Empty string is a real cached value, not a cache miss.
        assert sys_info._get_cached_result("k", 60) == ""


class TestCacheDecorator:
    def test_second_call_is_served_from_cache(self) -> None:
        sys_info, counter = make_counting_stub("arch")

        first = sys_info.system_arch()
        second = sys_info.system_arch()

        assert first == second == "arch"
        assert counter["n"] == 1

    def test_empty_result_is_cached(self) -> None:
        sys_info, counter = make_counting_stub("")

        sys_info.get_host_name()
        sys_info.get_host_name()

        # Empty string must be cached, not re-fetched as if it were a miss.
        assert counter["n"] == 1

    def test_cache_refetches_after_expiry(self, monkeypatch) -> None:
        clock = {"t": 1000.0}
        monkeypatch.setattr(sysinfo_mod.time, "time", lambda: clock["t"])
        counter = {"n": 0}

        class Stub(SysInfo):
            def _run_command(self, cmd):
                counter["n"] += 1
                return f"arch{counter['n']}"

        sys_info = Stub()

        first = sys_info.system_arch()
        clock["t"] = 1000.0 + 59  # still within the 60s window
        cached = sys_info.system_arch()
        clock["t"] = 1000.0 + 61  # window elapsed
        refreshed = sys_info.system_arch()

        assert first == cached == "arch1"
        assert refreshed == "arch2"
        assert counter["n"] == 2


class TestRunCommand:
    def test_string_command_is_shlex_split_and_stripped(self) -> None:
        sys_info = SysInfo()

        assert sys_info._run_command("echo hello world") == "hello world"

    def test_list_command_runs_directly(self) -> None:
        sys_info = SysInfo()

        assert sys_info._run_command(["echo", "hi"]) == "hi"

    def test_output_is_stripped_of_whitespace(self) -> None:
        sys_info = SysInfo()

        assert sys_info._run_command(["printf", "  padded  "]) == "padded"

    def test_failing_command_returns_empty_string(self) -> None:
        sys_info = SysInfo()

        # 'false' exits non-zero -> CalledProcessError -> "".
        assert sys_info._run_command("false") == ""

    def test_missing_command_returns_empty_string(self) -> None:
        sys_info = SysInfo()

        # FileNotFoundError is caught and turned into "".
        assert sys_info._run_command("nonexistent_command_xyz_123") == ""


class TestLsbRelease:
    def test_builds_lsb_release_invocation(self) -> None:
        captured = {}

        class Stub(SysInfo):
            def _run_command(self, cmd):
                captured["cmd"] = cmd
                return "noble"

        result = Stub()._lsb_release("c")

        assert result == "noble"
        assert captured["cmd"] == "lsb_release -sc"


class TestFreeSpace:
    def test_free_space_is_non_negative_int(self, tmp_path) -> None:
        sys_info = SysInfo()

        free = sys_info.free_space_in_directory(str(tmp_path))

        assert isinstance(free, int)
        assert free >= 0


class TestHasIpv6:
    def test_returns_bool(self) -> None:
        sys_info = SysInfo()

        # Host-dependent value, but the contract is a bool.
        assert isinstance(sys_info.has_ipv6(), bool)


class TestIpAddressParsing:
    def test_extracts_src_address_from_ip_route(self) -> None:
        route = "1.0.0.0 via 10.0.0.1 dev eth0 src 203.0.113.7 uid 0"

        assert make_stub(route).get_ip_address() == "203.0.113.7"

    def test_empty_output_returns_empty_string(self) -> None:
        assert make_stub("").get_ip_address() == ""

    def test_malformed_output_without_src_returns_empty_string(self) -> None:
        # No "src " token -> IndexError -> caught -> "".
        assert make_stub("no source token here").get_ip_address() == ""


class TestCpuCoreParsing:
    def test_extracts_socket_count(self) -> None:
        assert make_stub("Socket:    2").get_cpu_core() == "2"

    def test_empty_output_returns_empty_string(self) -> None:
        assert make_stub("").get_cpu_core() == ""

    def test_output_without_colon_returns_empty_string(self) -> None:
        # split(":")[1] raises IndexError -> caught -> "".
        assert make_stub("justtext").get_cpu_core() == ""


class TestHdParsing:
    def test_hd_size_extracts_parenthesised_value(self) -> None:
        assert make_stub("size: 500GB (500 GB)").get_hd_size() == "500 GB"

    def test_hd_size_without_parens_returns_empty_string(self) -> None:
        assert make_stub("no parens here").get_hd_size() == ""

    def test_hd_size_empty_output_returns_empty_string(self) -> None:
        assert make_stub("").get_hd_size() == ""

    def test_hd_type_extracts_description(self) -> None:
        assert make_stub("description: ATA Disk").get_hd_type() == "ATA Disk"

    def test_hd_type_without_colon_returns_empty_string(self) -> None:
        assert make_stub("nodescription").get_hd_type() == ""

    def test_hd_type_empty_output_returns_empty_string(self) -> None:
        assert make_stub("").get_hd_type() == ""


class TestVendorParsing:
    def test_manufacturer_strips_dmidecode_padding(self) -> None:
        # Implementation slices [2:-3] off the raw output.
        assert make_stub("Dell Inc.xyz").get_manufacturer() == "ll Inc."

    def test_model_strips_dmidecode_padding(self) -> None:
        assert make_stub("OptiPlexxyz").get_model() == "tiPlex"

    def test_serial_number_strips_dmidecode_padding(self) -> None:
        assert make_stub("ABCD1234xyz").get_serial_number() == "CD1234"


class TestRamParsing:
    def test_ram_type_extracts_value_after_type_label(self) -> None:
        assert make_stub("\tType: DDR4").get_ram_type() == "DDR4"

    def test_ram_type_empty_output_returns_empty_string(self) -> None:
        assert make_stub("").get_ram_type() == ""

    def test_ram_type_without_label_returns_empty_string(self) -> None:
        # No "\tType:" token -> IndexError -> caught -> "".
        assert make_stub("Speed: 3200 MT/s").get_ram_type() == ""

    def test_ram_size_converts_kb_to_rounded_gb(self) -> None:
        # 16384000 kB / 1024000 -> 16 GB.
        assert make_stub("MemTotal:  16384000 kB").get_ram_size() == "16 GB"

    def test_ram_size_empty_output_returns_empty_string(self) -> None:
        assert make_stub("").get_ram_size() == ""

    def test_ram_size_unparseable_output_returns_empty_string(self) -> None:
        # int(...) on a non-numeric field raises -> caught -> "".
        assert make_stub("MemTotal: notanumber kB").get_ram_size() == ""

    def test_ram_size_rounding_to_zero_returns_empty_string(self) -> None:
        # Tiny value rounds to 0 GB, which is falsy -> "".
        assert make_stub("MemTotal: 1 kB").get_ram_size() == ""
