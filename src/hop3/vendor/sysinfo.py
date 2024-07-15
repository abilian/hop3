# Forked from: https://github.com/suhanna/System_info

# Copyright (c) 2018 The Python Packaging Authority
# Copyright (c) 2023-2024, Abilian SAS

# MIT License

import platform
import shutil
import subprocess
import sys
from subprocess import DEVNULL

import cpuinfo

RAM_TYPES = {
    0: "DDR4",
    1: "Other",
    2: "DRAM",
    3: "Synchronous DRAM",
    4: "Cache DRAM",
    5: "EDO",
    6: "EDRAM",
    7: "VRAM",
    8: "SRAM",
    9: "RAM",
    10: "ROM",
    11: "Flash",
    12: "EEPROM",
    13: "FEPROM",
    14: "EPROM",
    15: "CDRAM",
    16: "3DRAM",
    17: "SDRAM",
    18: "SGRAM",
    19: "RDRAM",
    20: "DDR",
    21: "DDR2",
    22: "DDR2 FB-DIMM",
    24: "DDR3",
    25: "FBD2",
}


class SystemInfo:
    """System Information"""

    def platform_name(self):
        return platform.system()

    def system_spec(self):
        """Collect Hardware details for Linux, Windows and Mac"""

        cinfo = cpuinfo.get_cpu_info()
        data = {
            "Processor": cinfo["brand_raw"],
            "CPU": cinfo["count"],
        }

        if self.platform_name() == "Linux":
            hardware_info = self.get_unix_system_spec(data)
        elif self.platform_name() == "Darwin":
            hardware_info = self.get_mac_system_spec(data)
        else:
            print("Operating system is not detected.")
            sys.exit(0)

        return hardware_info

    def get_unix_system_spec(self, data):
        """Collect hardware info for Linux"""

        data["Total Disk Space"] = str(shutil.disk_usage("/")[0] // (2**30)) + "GB"
        data["Available Space"] = str(shutil.disk_usage("/")[2] // (2**30)) + "GB"
        try:
            data["Host Name"] = (
                subprocess.check_output(
                    "hostname", stderr=DEVNULL, shell=True
                )
                .decode("utf-8")
                .strip("\n")
            )
        except Exception:
            data["Host Name"] = None

        try:
            data["Ip"] = (
                subprocess.check_output(
                    "ip route get 1", stderr=DEVNULL, shell=True
                )
                .decode("utf-8")
                .split("src ")[1]
                .split(" ")[0]
            )
        except Exception:
            data["Ip"] = None

        try:
            data["Operating System"] = (
                str(
                    subprocess.check_output(
                        "cat /etc/*-release | grep NAME=",
                        stderr=DEVNULL,
                        shell=True,
                    )
                )
                .partition("\\nNAME=")[2]
                .split("\\n")[0]
                .strip('"')
            )
        except Exception:
            data["Operating System"] = None

        try:
            data["OS Version"] = (
                str(
                    subprocess.check_output(
                        "cat /etc/*-release | grep VERSION_ID",
                        stderr=DEVNULL,
                        shell=True,
                    )
                )
                .partition("VERSION_ID=")[2]
                .strip('"')[:-4]
            )
        except Exception:
            data["OS Version"] = None

        try:
            data["CPU_Core"] = (
                str(
                    subprocess.check_output(
                        "lscpu | grep socket:", stderr=DEVNULL, shell=True
                    )
                )
                .split(":")[1]
                .strip(" ")
                .strip("\\n'")
            )
        except Exception:
            data["CPU_Core"] = None

        try:
            data["HD Size"] = (
                str(
                    subprocess.check_output(
                        "sudo lshw -class disk | grep size",
                        stderr=DEVNULL,
                        shell=True,
                    )
                )
                .split("(", 1)[1]
                .split(")")[0]
            )
        except Exception:
            data["HD Size"] = None

        try:
            data["Manufacturer"] = str(
                subprocess.check_output(
                    "sudo dmidecode -s system-manufacturer",
                    stderr=DEVNULL,
                    shell=True,
                )
            )[2:-3]
        except Exception:
            data["Manufacturer"] = None

        try:
            data["Model"] = str(
                subprocess.check_output(
                    "sudo dmidecode -s system-product-name",
                    stderr=DEVNULL,
                    shell=True,
                )
            )[2:-3]
        except Exception:
            data["Model"] = None

        try:
            data["Ram_Type"] = (
                subprocess.check_output(
                    'sudo dmidecode --type 17 | grep -B 2 "Type Detail: Synchronous" | grep -w "Type:"',
                    stderr=DEVNULL,
                    shell=True,
                )
                .decode("utf-8")
                .split("\tType:")[1]
                .strip(" ")
                .strip("\n")
            )
        except Exception:
            data["Ram_Type"] = None

        try:
            ram_size = round(
                int(
                    subprocess.check_output(
                        "grep MemTotal /proc/meminfo",
                        stderr=DEVNULL,
                        shell=True,
                    )
                    .decode("utf-8")
                    .split()[1]
                )
                / 1024000
            )
            data["Ram_Size"] = str(ram_size) + " GB"
        except Exception:
            data["Ram_Size"] = None

        try:
            data["HD_Type"] = (
                str(
                    subprocess.check_output(
                        "sudo lshw -class disk -class storage | grep description",
                        stderr=DEVNULL,
                        shell=True,
                    )
                )
                .split("\\n")[0]
                .split(":")[1]
                .strip(" ")
            )
        except Exception:
            data["HD_Type"] = None

        try:
            data["Serial_Number"] = str(
                subprocess.check_output(
                    "sudo dmidecode -s system-serial-number",
                    stderr=DEVNULL,
                    shell=True,
                )
            )[2:-3]
        except Exception:
            data["Serial_Number"] = None

        return data

    def get_mac_system_spec(self, data):
        """Collect hardware info for Linux"""

        data["Operating System"] = (
            subprocess.check_output(
                "sw_vers -productName", stderr=DEVNULL, shell=True
            )
            .decode("utf-8")
            .strip("\n")
        )
        data["OS Version"] = (
            subprocess.check_output(
                "sw_vers -productVersion", stderr=DEVNULL, shell=True
            )
            .decode("utf-8")
            .strip("\n")
        )
        data["Manufacturer"] = "Apple"

        try:
            data["Available Space"] = (
                subprocess.check_output(
                    "system_profiler SPStorageDataType | grep Available",
                    stderr=DEVNULL,
                    shell=True,
                )
                .decode("utf-8")
                .strip(" \n")
                .partition("Available: ")[2]
                .partition("(")[0]
                .strip(" ")
            )
        except Exception:
            data["Available Space"] = None
        try:
            data["Host Name"] = (
                subprocess.check_output(
                    "hostname", stderr=DEVNULL, shell=True
                )
                .decode("utf-8")
                .strip("\n")
            )
        except Exception:
            data["Host Name"] = None
        try:
            data["Ip"] = (
                subprocess.check_output(
                    'route -n get 1 | grep interface | cut -d ":" -f2 | xargs ipconfig getifaddr',
                    stderr=DEVNULL,
                    shell=True,
                )
                .decode("utf-8")
                .strip("\n")
            )
        except Exception:
            data["Ip"] = None
        try:
            data["CPU_Core"] = str(
                subprocess.check_output(
                    "system_profiler SPHardwareDataType | grep 'Total Number of Cores:'",
                    stderr=DEVNULL,
                    shell=True,
                )
            ).split("Cores:")[1][1:-3]
        except Exception:
            data["CPU_Core"] = None
        try:
            data["HD Size"] = data["Total Disk Space"] = (
                str(
                    subprocess.check_output(
                        "system_profiler SPStorageDataType | grep Capacity",
                        stderr=DEVNULL,
                        shell=True,
                    )
                )
                .split("Capacity:")[1]
                .strip(" ")
                .strip("\\n")
                .split("(")[0]
            )
        except Exception:
            data["HD Size"] = data["Total Disk Space"] = None
        try:
            data["Model"] = str(
                subprocess.check_output(
                    "system_profiler SPHardwareDataType | grep 'Model Name'",
                    stderr=DEVNULL,
                    shell=True,
                )
            ).split(":")[1][1:-3]
        except Exception:
            data["Model"] = None
        try:
            data["Ram_Type"] = (
                str(
                    subprocess.check_output(
                        "system_profiler SPMemoryDataType | grep Type",
                        stderr=DEVNULL,
                        shell=True,
                    )
                )
                .split("Type:")[1]
                .strip(" ")
                .strip("\\n")
            )
        except Exception:
            data["Ram_Type"] = None
        try:
            data["Ram_Size"] = (
                subprocess.check_output(
                    'system_profiler SPHardwareDataType | grep "  Memory:"',
                    stderr=DEVNULL,
                    shell=True,
                )
                .decode("utf-8")
                .partition("Memory: ")[2]
                .strip("\n")
            )
        except Exception:
            data["Ram_Size"] = None
        try:
            data["HD_Type"] = (
                str(
                    subprocess.check_output(
                        "system_profiler SPStorageDataType | grep Protocol",
                        stderr=DEVNULL,
                        shell=True,
                    )
                )
                .split("Protocol:")[1]
                .strip(" ")[:-3]
            )
        except Exception:
            data["HD_Type"] = None
        try:
            data["Serial_Number"] = str(
                subprocess.check_output(
                    "system_profiler SPHardwareDataType | grep Serial",
                    stderr=DEVNULL,
                    shell=True,
                )
            ).split(":")[1][1:-3]
        except Exception:
            data["Serial_Number"] = None

        return data


def get_system_info():
    os_info = SystemInfo()
    sys_info = os_info.system_spec()
    return sys_info
