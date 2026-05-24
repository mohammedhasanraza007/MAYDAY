"""
M.A.Y.D.A.Y GPU Detection & Hardware Profiling Engine
======================================================
Identifies AMD / NVIDIA hardware to enable proper acceleration (DirectML / Vulkan).
Prevents silent CPU fallback and optimizes execution backend.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from typing import Dict, Any

logger = logging.getLogger("mayday.gpu")


class GPUDetector:
    """Detects GPU vendor and determines the correct acceleration backend.

    On Windows AMD:
    - DirectML or Vulkan is prioritized.
    - CUDA is prioritized only for NVIDIA.
    """

    _cached_info: Dict[str, Any] | None = None

    @classmethod
    def get_info(cls) -> Dict[str, Any]:
        """Detect GPU hardware and return system info dict."""
        if cls._cached_info is not None:
            return cls._cached_info

        gpu_name = ""
        adapter_ram = 0.0
        vendor = "UNKNOWN"
        backend = "CPU"
        suggested_layers = 0

        # Try executing PowerShell to get video controller information on Windows
        if sys.platform == "win32":
            try:
                cmd = (
                    "powershell -NoProfile -Command "
                    '"Get-CimInstance Win32_VideoController | Select-Object Name, AdapterRAM | ConvertTo-Json"'
                )
                res = subprocess.run(
                    cmd, shell=True, capture_output=True, text=True, timeout=5
                )
                if res.returncode == 0 and res.stdout.strip():
                    import json
                    data = json.loads(res.stdout.strip())
                    if isinstance(data, list) and len(data) > 0:
                        # Grab the first active one or prefer discrete AMD/NVIDIA
                        for entry in data:
                            name = str(entry.get("Name", "")).upper()
                            if "AMD" in name or "RADEON" in name or "NVIDIA" in name:
                                gpu_name = entry.get("Name", "")
                                adapter_ram = float(entry.get("AdapterRAM", 0))
                                break
                        if not gpu_name:
                            gpu_name = data[0].get("Name", "")
                            adapter_ram = float(data[0].get("AdapterRAM", 0))
                    elif isinstance(data, dict):
                        gpu_name = data.get("Name", "")
                        adapter_ram = float(data.get("AdapterRAM", 0))
            except Exception as e:
                logger.debug("Failed detecting GPU via CIM instance: %s", e)

        # Fallback to general system check if empty
        gpu_name_upper = gpu_name.upper()

        if "AMD" in gpu_name_upper or "RADEON" in gpu_name_upper:
            vendor = "AMD"
            backend = "DIRECTML"
            suggested_layers = 36
        elif "NVIDIA" in gpu_name_upper or "GEFORCE" in gpu_name_upper:
            vendor = "NVIDIA"
            backend = "CUDA"
            suggested_layers = 36
        elif "INTEL" in gpu_name_upper:
            vendor = "INTEL"
            # Intel can use Vulkan or CPU fallback
            backend = "CPU"
            suggested_layers = 0
        else:
            vendor = "UNKNOWN"
            backend = "CPU"
            suggested_layers = 0

        # Allow environment overrides (e.g. MODEL_BACKEND=VULKAN)
        env_backend = os.environ.get("MODEL_BACKEND") or os.environ.get("MAYDAY_GPU_BACKEND")
        if env_backend:
            backend = env_backend.upper()
            if backend in ("DIRECTML", "VULKAN", "CUDA"):
                suggested_layers = 36
            else:
                suggested_layers = 0
        if vendor == "AMD" and backend == "CUDA":
            logger.warning("AMD GPU detected with CUDA backend request; falling back to DIRECTML")
            backend = "DIRECTML"
            suggested_layers = 36

        adapter_ram_gb = round(adapter_ram / (1024**3), 2) if adapter_ram else 0.0
        cls._cached_info = {
            "gpu_name": gpu_name or "Standard Video Controller",
            "vendor": vendor,
            "backend": backend,
            "adapter_ram_gb": adapter_ram_gb,
            "suggested_layers": suggested_layers,
            "gpu_active_percent": 0.0,
            "vram_usage_mb": 0.0,
            "tokens_per_second": 0.0,
            "backend_name": backend,
        }

        logger.info(
            "GPU hardware detected: %s (Vendor: %s, Selected Backend: %s, VRAM: %.2f GB)",
            cls._cached_info["gpu_name"],
            cls._cached_info["vendor"],
            cls._cached_info["backend"],
            cls._cached_info["adapter_ram_gb"],
        )
        return cls._cached_info

    @staticmethod
    def effective_backend_name(backend: str, gpu_percent: float | None, vram_mb: float | None) -> str:
        """Return the backend name users can trust from observed telemetry."""
        backend_name = (backend or "CPU").upper()
        gpu_value = float(gpu_percent or 0.0)
        vram_value = float(vram_mb or 0.0)
        if backend_name in {"DIRECTML", "VULKAN", "CUDA"} and gpu_value < 1.0 and vram_value < 50.0:
            return f"CPU ({backend_name} offload not confirmed)"
        return backend_name

    @classmethod
    def record_inference_telemetry(cls, tokens_per_sec: float = 0.0) -> Dict[str, Any]:
        info = dict(cls.get_info())
        utilization = cls._query_gpu_utilization_percent()
        if utilization is not None:
            info["gpu_active_percent"] = utilization
        info["vram_usage_mb"] = cls._query_vram_usage_mb()
        info["tokens_per_second"] = round(float(tokens_per_sec), 2)
        info["backend_name"] = info.get("backend", "CPU")
        cls._cached_info = {**cls.get_info(), **info}
        return info

    @staticmethod
    def _query_gpu_utilization_percent() -> float | None:
        if sys.platform != "win32":
            return None
        try:
            cmd = (
                "powershell -NoProfile -Command "
                '"$c=(Get-Counter ''\\GPU Engine(*)\\Utilization Percentage'' -ErrorAction SilentlyContinue).CounterSamples | '
                'Measure-Object CookedValue -Sum; [math]::Round($c.Sum,2)"'
            )
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=3)
            if res.returncode == 0 and res.stdout.strip():
                return max(0.0, min(float(res.stdout.strip()), 100.0))
        except Exception:
            return None
        return None

    @staticmethod
    def _query_vram_usage_mb() -> float:
        if sys.platform != "win32":
            return 0.0
        try:
            cmd = (
                "powershell -NoProfile -Command "
                '"$p=(Get-Counter ''\\GPU Adapter Memory(*)\\Dedicated Usage'' -ErrorAction SilentlyContinue).CounterSamples | '
                'Measure-Object CookedValue -Sum; [math]::Round($p.Sum/1MB,2)"'
            )
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=3)
            if res.returncode == 0 and res.stdout.strip():
                return max(0.0, float(res.stdout.strip()))
        except Exception:
            return 0.0
        return 0.0
