"""Hardware/runtime detection.

Shared by:
  - `setup-ai doctor` / the install wizard (§6/§system detection)
  - the `/v1/system` and `/health` API endpoints
so there is exactly one place that knows how to answer "what am I
running on", instead of duplicated detection logic in the CLI and API.
"""

from __future__ import annotations

import json
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
    vendor: str = "unknown"  # "amd", "nvidia", "intel", "apple", "unknown"
    backend: str = "cpu"     # "rocm", "cuda", "mps", "xpu", "cpu"
    is_rocm: bool = False
    hip_version: str | None = None


@dataclass
class HardwareAccelerator:
    vendor: str              # "amd", "nvidia", "apple", "intel", "cpu"
    name: str
    backend: str             # "rocm", "cuda", "mps", "xpu", "cpu"
    backend_active: bool
    total_vram_mb: int | None = None
    free_vram_mb: int | None = None
    driver_version: str | None = None
    compute_version: str | None = None


@dataclass
class DeviceMatchResult:
    status: str              # "matched", "mismatch", "cpu_fallback"
    primary_accelerator: HardwareAccelerator
    recommended_device: str  # "cuda", "mps", "xpu", "cpu"
    recommended_dtype: str   # "bfloat16", "float16", "float32"
    recommended_quantization: str | None  # "int4", "int8", None
    mismatch_warning: str | None = None
    install_hint: str | None = None
    hardware_list: list[HardwareAccelerator] | None = None

    def to_dict(self) -> dict:
        return asdict(self)


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
    device_match: DeviceMatchResult | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def _detect_physical_gpus() -> list[dict]:
    """Detect physical GPUs across Windows, Linux, and macOS even without PyTorch."""
    results: list[dict] = []

    # Windows: fast, non-blocking registry query for all physical display adapters
    if os.name == "nt":
        try:
            import winreg

            base = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base) as k:
                idx = 0
                while True:
                    try:
                        subkey = winreg.EnumKey(k, idx)
                        idx += 1
                        if not subkey.isdigit():
                            continue
                        with winreg.OpenKey(k, subkey) as sk:
                            try:
                                desc, _ = winreg.QueryValueEx(sk, "DriverDesc")
                                lower = desc.lower()
                                if any(virt in lower for virt in ["virtual", "basic display", "rdp", "remotedesktop", "vmware", "mumuplayer"]):
                                    continue

                                driver_ver = None
                                try:
                                    driver_ver, _ = winreg.QueryValueEx(sk, "DriverVersion")
                                except FileNotFoundError:
                                    pass

                                vram_mb = None
                                try:
                                    mem, _ = winreg.QueryValueEx(sk, "HardwareInformation.qwMemorySize")
                                    vram_mb = int(mem // (1024 * 1024))
                                except FileNotFoundError:
                                    pass

                                vendor = "unknown"
                                if any(k in lower for k in ["amd", "radeon", "advanced micro devices", "firepro", "instinct"]):
                                    vendor = "amd"
                                elif any(k in lower for k in ["nvidia", "geforce", "rtx", "gtx", "quadro", "tesla"]):
                                    vendor = "nvidia"
                                elif any(k in lower for k in ["intel", "arc", "iris", "uhd"]):
                                    vendor = "intel"

                                results.append({
                                    "name": desc,
                                    "vendor": vendor,
                                    "driver_version": driver_ver,
                                    "vram_mb": vram_mb,
                                })
                            except FileNotFoundError:
                                pass
                    except OSError:
                        break
        except Exception:
            pass

    # Linux
    elif platform.system() == "Linux":
        try:
            drm_dir = "/sys/class/drm"
            if os.path.exists(drm_dir):
                for card in os.listdir(drm_dir):
                    if not card.startswith("card") or "-" in card:
                        continue
                    dev_path = os.path.join(drm_dir, card, "device")
                    vendor_file = os.path.join(dev_path, "vendor")
                    if os.path.exists(vendor_file):
                        with open(vendor_file, "r", encoding="utf-8") as f:
                            ven_id = f.read().strip().lower()
                        vendor = "unknown"
                        name = card
                        if ven_id == "0x1002":
                            vendor = "amd"
                            name = "AMD Radeon / Instinct GPU"
                        elif ven_id == "0x10de":
                            vendor = "nvidia"
                            name = "NVIDIA GPU"
                        elif ven_id == "0x8086":
                            vendor = "intel"
                            name = "Intel GPU"

                        vram_mb = None
                        vram_file = os.path.join(dev_path, "mem_info_vram_total")
                        if os.path.exists(vram_file):
                            try:
                                with open(vram_file, "r", encoding="utf-8") as vf:
                                    vram_mb = int(int(vf.read().strip()) // (1024 * 1024))
                            except Exception:
                                pass

                        results.append({
                            "name": name,
                            "vendor": vendor,
                            "driver_version": None,
                            "vram_mb": vram_mb,
                        })
        except Exception:
            pass

        if not results and shutil.which("lspci"):
            try:
                proc = subprocess.run(["lspci"], capture_output=True, text=True, timeout=3)
                for line in proc.stdout.splitlines():
                    lower = line.lower()
                    if "vga" in lower or "3d controller" in lower or "display" in lower:
                        vendor = "unknown"
                        if "amd" in lower or "radeon" in lower or "advanced micro devices" in lower:
                            vendor = "amd"
                        elif "nvidia" in lower:
                            vendor = "nvidia"
                        elif "intel" in lower:
                            vendor = "intel"
                        results.append({
                            "name": line.split(":")[-1].strip(),
                            "vendor": vendor,
                            "driver_version": None,
                            "vram_mb": None,
                        })
            except Exception:
                pass

    # macOS (Darwin)
    elif platform.system() == "Darwin":
        if platform.machine() == "arm64":
            results.append({
                "name": "Apple Silicon Unified GPU",
                "vendor": "apple",
                "driver_version": None,
                "vram_mb": _detect_ram_mb(),
            })

    return results


def detect_hardware() -> list[HardwareAccelerator]:
    """Inspect all available accelerators (AMD ROCm, NVIDIA CUDA, Apple MPS, Intel XPU, CPU)."""
    hardware: list[HardwareAccelerator] = []

    torch_cuda = False
    torch_rocm = False
    torch_mps = False
    torch_xpu = False
    hip_version = None
    cuda_version = None
    torch_device_name = None
    torch_vram_mb = None
    torch_free_mb = None

    try:
        import torch

        if torch.cuda.is_available():
            hip_version = getattr(torch.version, "hip", None)
            cuda_version = getattr(torch.version, "cuda", None)
            if hip_version is not None:
                torch_rocm = True
            else:
                torch_cuda = True
            try:
                torch_device_name = torch.cuda.get_device_name(0)
                props = torch.cuda.get_device_properties(0)
                torch_vram_mb = int(props.total_memory // (1024 * 1024))
                alloc = int(torch.cuda.memory_allocated(0) // (1024 * 1024))
                torch_free_mb = max(0, torch_vram_mb - alloc)
            except Exception:
                pass

        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            torch_mps = True
        if hasattr(torch, "xpu") and torch.xpu.is_available():
            torch_xpu = True
    except Exception:
        pass

    physical_gpus = _detect_physical_gpus()

    if physical_gpus:
        for pg in physical_gpus:
            vendor = pg["vendor"]
            name = pg["name"]
            vram = pg["vram_mb"]
            driver = pg.get("driver_version")

            if vendor == "amd":
                backend_active = torch_rocm
                backend = "rocm"
                comp_ver = f"ROCm {hip_version}" if hip_version else None
                hardware.append(
                    HardwareAccelerator(
                        vendor="amd",
                        name=torch_device_name if (torch_rocm and torch_device_name) else name,
                        backend=backend,
                        backend_active=backend_active,
                        total_vram_mb=torch_vram_mb or vram,
                        free_vram_mb=torch_free_mb,
                        driver_version=driver,
                        compute_version=comp_ver,
                    )
                )
            elif vendor == "nvidia":
                backend_active = torch_cuda
                backend = "cuda"
                comp_ver = f"CUDA {cuda_version}" if cuda_version else None
                hardware.append(
                    HardwareAccelerator(
                        vendor="nvidia",
                        name=torch_device_name if (torch_cuda and torch_device_name) else name,
                        backend=backend,
                        backend_active=backend_active,
                        total_vram_mb=torch_vram_mb or vram,
                        free_vram_mb=torch_free_mb,
                        driver_version=driver,
                        compute_version=comp_ver,
                    )
                )
            elif vendor == "apple":
                hardware.append(
                    HardwareAccelerator(
                        vendor="apple",
                        name=name,
                        backend="mps",
                        backend_active=torch_mps,
                        total_vram_mb=vram or _detect_ram_mb(),
                        free_vram_mb=None,
                        compute_version="Apple Metal MPS",
                    )
                )
            elif vendor == "intel":
                hardware.append(
                    HardwareAccelerator(
                        vendor="intel",
                        name=name,
                        backend="xpu",
                        backend_active=torch_xpu,
                        total_vram_mb=vram,
                        free_vram_mb=None,
                        compute_version="Intel oneAPI XPU" if torch_xpu else None,
                    )
                )
            else:
                hardware.append(
                    HardwareAccelerator(
                        vendor="unknown",
                        name=name,
                        backend="cpu",
                        backend_active=False,
                        total_vram_mb=vram,
                    )
                )

    elif torch_cuda or torch_rocm:
        vendor = "amd" if torch_rocm else "nvidia"
        backend = "rocm" if torch_rocm else "cuda"
        comp_ver = f"ROCm {hip_version}" if torch_rocm else f"CUDA {cuda_version}"
        hardware.append(
            HardwareAccelerator(
                vendor=vendor,
                name=torch_device_name or f"{vendor.upper()} GPU",
                backend=backend,
                backend_active=True,
                total_vram_mb=torch_vram_mb,
                free_vram_mb=torch_free_mb,
                compute_version=comp_ver,
            )
        )
    elif torch_mps:
        hardware.append(
            HardwareAccelerator(
                vendor="apple",
                name="Apple Silicon (MPS)",
                backend="mps",
                backend_active=True,
                total_vram_mb=_detect_ram_mb(),
                compute_version="Apple Metal MPS",
            )
        )

    cpu_cores = os.cpu_count() or 1
    ram = _detect_ram_mb()
    hardware.append(
        HardwareAccelerator(
            vendor="cpu",
            name=f"CPU ({cpu_cores} cores, {ram or 'unknown'} MB RAM)",
            backend="cpu",
            backend_active=True,
            total_vram_mb=ram,
            free_vram_mb=ram,
        )
    )

    return hardware


def match_device_settings(
    config_device: str | None = None, model_path: str | None = None
) -> DeviceMatchResult:
    """Analyze detected hardware vs PyTorch runtime and recommend optimal device, dtype, and quantization."""
    hw_list = detect_hardware()

    non_cpu = [h for h in hw_list if h.backend != "cpu"]
    primary = non_cpu[0] if non_cpu else hw_list[-1]

    status = "cpu_fallback"
    recommended_device = "cpu"
    recommended_dtype = "float32"
    recommended_quantization = "int4"
    mismatch_warning = None
    install_hint = None

    if primary.backend != "cpu":
        if primary.backend_active:
            status = "matched"
            recommended_device = "cuda" if primary.backend in ("cuda", "rocm") else primary.backend

            if primary.backend in ("cuda", "rocm"):
                try:
                    import torch

                    if torch.cuda.is_available() and torch.cuda.is_bf16_supported():
                        recommended_dtype = "bfloat16"
                    else:
                        recommended_dtype = "float16"
                except Exception:
                    recommended_dtype = "float16"
            elif primary.backend == "mps":
                recommended_dtype = "float16"
            elif primary.backend == "xpu":
                recommended_dtype = "bfloat16"

            vram = primary.total_vram_mb or 0
            if vram >= 28000:
                recommended_quantization = None
            elif vram >= 12000:
                recommended_quantization = "int8"
            else:
                recommended_quantization = "int4"
        else:
            status = "mismatch"
            recommended_device = "cpu"
            recommended_dtype = "float32"
            recommended_quantization = "int4"

            if primary.vendor == "amd":
                mismatch_warning = (
                    f"Physical AMD GPU detected ('{primary.name}') but PyTorch ROCm/HIP is not active. "
                    "The model will run on CPU unless PyTorch with ROCm acceleration is installed."
                )
                if platform.system() == "Linux":
                    install_hint = "pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm6.2"
                else:
                    install_hint = "pip install torch-directml (or install PyTorch with ROCm for Windows / WSL2)"
            elif primary.vendor == "nvidia":
                mismatch_warning = (
                    f"Physical NVIDIA GPU detected ('{primary.name}') but PyTorch CUDA is not active. "
                    "The model will run on CPU unless PyTorch with CUDA acceleration is installed."
                )
                install_hint = "pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124"
            elif primary.vendor == "intel":
                mismatch_warning = (
                    f"Physical Intel GPU detected ('{primary.name}') but PyTorch XPU is not active."
                )
                install_hint = "pip install intel-extension-for-pytorch (or PyTorch 2.4+ with XPU)"

    if config_device and config_device != "auto" and config_device != recommended_device:
        if config_device.startswith("cuda") and status != "matched":
            mismatch_warning = (
                f"Configuration requests device='{config_device}', but no active GPU acceleration backend was found. "
                "Inference will fail or fallback to CPU."
            )

    return DeviceMatchResult(
        status=status,
        primary_accelerator=primary,
        recommended_device=recommended_device,
        recommended_dtype=recommended_dtype,
        recommended_quantization=recommended_quantization,
        mismatch_warning=mismatch_warning,
        install_hint=install_hint,
        hardware_list=hw_list,
    )


def _detect_gpu() -> GpuInfo:
    # 1. Try rocm-smi if available on PATH (for AMD GPUs)
    if shutil.which("rocm-smi") is not None:
        try:
            out = subprocess.run(["rocm-smi", "--showproductname"], capture_output=True, text=True, timeout=5)
            for line in out.stdout.splitlines():
                if "Card series:" in line or "Product Name:" in line:
                    card_name = line.split(":")[-1].strip()
                    return GpuInfo(
                        available=True,
                        name=card_name,
                        vendor="amd",
                        backend="rocm",
                        is_rocm=True,
                    )
        except Exception:
            pass

    # 2. Try nvidia-smi if available on PATH
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
                vendor="nvidia",
                backend="cuda",
            )
        except (subprocess.SubprocessError, OSError, ValueError, IndexError):
            pass

    # 3. Fall back to torch.cuda if available
    try:
        import torch

        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            props = torch.cuda.get_device_properties(0)
            total_mb = int(props.total_memory // (1024 * 1024))
            allocated_mb = int(torch.cuda.memory_allocated(0) // (1024 * 1024))
            free_mb = max(0, total_mb - allocated_mb)
            hip_ver = getattr(torch.version, "hip", None)
            cuda_ver = getattr(torch.version, "cuda", None)
            is_rocm = hip_ver is not None
            vendor = "amd" if is_rocm else "nvidia"
            backend = "rocm" if is_rocm else "cuda"
            return GpuInfo(
                available=True,
                name=name,
                total_vram_mb=total_mb,
                free_vram_mb=free_mb,
                cuda_version=cuda_ver,
                vendor=vendor,
                backend=backend,
                is_rocm=is_rocm,
                hip_version=hip_ver,
            )
    except Exception:
        pass

    # 4. Check if physical GPU exists even if PyTorch backend is not active
    phys = _detect_physical_gpus()
    if phys:
        top = phys[0]
        return GpuInfo(
            available=False,
            name=top["name"],
            total_vram_mb=top["vram_mb"],
            vendor=top["vendor"],
            backend="rocm" if top["vendor"] == "amd" else ("cuda" if top["vendor"] == "nvidia" else "cpu"),
        )

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
        device_match=match_device_settings(),
    )
