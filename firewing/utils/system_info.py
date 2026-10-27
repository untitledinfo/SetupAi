"""Hardware/runtime detection.

Shared by:
  - `setup-ai doctor` / the install wizard (§6/§system detection)
  - the `/v1/system` and `/health` API endpoints
so there is exactly one place that knows how to answer "what am I
running on", instead of duplicated detection logic in the CLI and API.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass, asdict


@dataclass
class GpuInfo:
    available: bool
    name: str | None = None
    total_vram_mb: int | None = None
    free_vram_mb: int | None = None
    cuda_version: str | None = None


@dataclass
class SystemInfo:
    os_name: str
    os_version: str
    python_version: str
    cpu_count: int | None
    total_ram_mb: int | None
    free_disk_mb: int | None
    docker_available: bool
    gpu: GpuInfo

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def _detect_gpu() -> GpuInfo:
    # 1. Try nvidia-smi if available on PATH
    if shutil.which("nvidia-smi") is not None:
        try:
            out = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.total,memory.free",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            )
            first_line = out.stdout.strip().splitlines()[0]
            name, total, free = [p.strip() for p in first_line.split(",")]
            cuda_version = None
            try:
                smi_out = subprocess.run(
                    ["nvidia-smi"], capture_output=True, text=True, timeout=5
                )
                for line in smi_out.stdout.splitlines():
                    if "CUDA Version" in line:
                        cuda_version = line.split("CUDA Version:")[-1].strip().split()[0]
                        break
            except (subprocess.SubprocessError, OSError):
                pass
            return GpuInfo(
                available=True,
                name=name,
                total_vram_mb=int(float(total)),
                free_vram_mb=int(float(free)),
                cuda_version=cuda_version,
            )
        except (subprocess.SubprocessError, OSError, ValueError, IndexError):
            pass

    # 2. Fall back to torch.cuda if available
    try:
        import torch

        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            props = torch.cuda.get_device_properties(0)
            total_mb = int(props.total_memory // (1024 * 1024))
            allocated_mb = int(torch.cuda.memory_allocated(0) // (1024 * 1024))
            free_mb = max(0, total_mb - allocated_mb)
            return GpuInfo(
                available=True,
                name=name,
                total_vram_mb=total_mb,
                free_vram_mb=free_mb,
                cuda_version=getattr(torch.version, "cuda", None),
            )
    except Exception:
        pass

    return GpuInfo(available=False)


def _detect_ram_mb() -> int | None:
    # 1. Try psutil (cross-platform)
    try:
        import psutil

        return int(psutil.virtual_memory().total // (1024 * 1024))
    except Exception:
        pass

    # 2. Try Linux /proc/meminfo
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return kb // 1024
    except (OSError, ValueError, IndexError):
        pass

    # 3. Try Windows ctypes GlobalMemoryStatusEx
    if os.name == "nt":
        try:
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(stat)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                return int(stat.ullTotalPhys // (1024 * 1024))
        except Exception:
            pass

    return None


def _detect_disk_mb(path: str | None = None) -> int | None:
    if path is None:
        path = os.path.splitdrive(os.getcwd())[0] + os.sep if os.name == "nt" else "/"
    try:
        usage = shutil.disk_usage(path)
        return usage.free // (1024 * 1024)
    except OSError:
        return None


def get_system_info() -> SystemInfo:
    return SystemInfo(
        os_name=platform.system(),
        os_version=platform.release(),
        python_version=platform.python_version(),
        cpu_count=os.cpu_count(),
        total_ram_mb=_detect_ram_mb(),
        free_disk_mb=_detect_disk_mb(),
        docker_available=shutil.which("docker") is not None,
        gpu=_detect_gpu(),
    )
