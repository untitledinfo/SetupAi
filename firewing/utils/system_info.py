"""Hardware/runtime detection.

Shared by:
  - `setup-ai doctor` / the install wizard (§6/§system detection)
  - the `/v1/system` and `/health` API endpoints
so there is exactly one place that knows how to answer "what am I
running on", instead of duplicated detection logic in the CLI and API.
"""

from __future__ import annotations

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
    if shutil.which("nvidia-smi") is None:
        return GpuInfo(available=False)
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
            total_vram_mb=int(total),
            free_vram_mb=int(free),
            cuda_version=cuda_version,
        )
    except (subprocess.SubprocessError, OSError, ValueError, IndexError):
        # nvidia-smi exists but failed/parsed oddly — report as unavailable
        # rather than crashing the health check.
        return GpuInfo(available=False)


def _detect_ram_mb() -> int | None:
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return kb // 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


def _detect_disk_mb(path: str = "/") -> int | None:
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
        cpu_count=__import__("os").cpu_count(),
        total_ram_mb=_detect_ram_mb(),
        free_disk_mb=_detect_disk_mb(),
        docker_available=shutil.which("docker") is not None,
        gpu=_detect_gpu(),
    )
