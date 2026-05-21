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
            suggested_layers = 20  # Safe partial offloading for RX 6600
        elif "NVIDIA" in gpu_name_upper or "GEFORCE" in gpu_name_upper:
            vendor = "NVIDIA"
            backend = "CUDA"
            suggested_layers = 24
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
                suggested_layers = 20
            else:
                suggested_layers = 0

        cls._cached_info = {
            "gpu_name": gpu_name or "Standard Video Controller",
            "vendor": vendor,
            "backend": backend,
            "adapter_ram_gb": round(adapter_ram / (1024**3), 2) if adapter_ram else 0.0,
            "suggested_layers": suggested_layers,
        }

        logger.info(
            "GPU hardware detected: %s (Vendor: %s, Selected Backend: %s, VRAM: %.2f GB)",
            cls._cached_info["gpu_name"],
            cls._cached_info["vendor"],
            cls._cached_info["backend"],
            cls._cached_info["adapter_ram_gb"],
        )
        return cls._cached_info
