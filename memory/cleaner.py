"""M.A.Y.D.A.Y Memory Cleaner — v5.0 with model lifecycle support"""
import gc
import logging
import os
import time
from pathlib import Path

import psutil

logger = logging.getLogger("mayday.memory.cleaner")


class MemoryCleaner:
    def __init__(self, cache_dir: str = "cache"):
        self.cache_dir = Path(cache_dir)
        self._last_clean = 0

    def clean_python_gc(self) -> int:
        """Run Python garbage collector and return objects freed."""
        before = len(gc.get_objects())
        gc.collect()
        gc.collect()  # Double pass for reference cycles
        after = len(gc.get_objects())
        freed = before - after
        logger.info("GC freed %d objects", freed)
        return freed

    def clean_cache(self, max_age_hours: int = 24) -> int:
        """Remove stale cache files older than max_age_hours."""
        if not self.cache_dir.exists():
            return 0
        cutoff = time.time() - (max_age_hours * 3600)
        removed = 0
        for p in self.cache_dir.rglob("*"):
            if p.is_file() and p.stat().st_mtime < cutoff:
                try:
                    p.unlink()
                    removed += 1
                except Exception:
                    pass
        logger.info("Cleaned %d stale cache files", removed)
        self._last_clean = time.time()
        return removed

    def force_model_cleanup(self, loader=None) -> dict:
        """
        Force-destroy model and aggressively free all memory.

        Args:
            loader: ModelLoader instance to destroy. If None, just runs GC.

        Returns:
            dict with ram_before, ram_after, freed_mb
        """
        ram_before = self.get_ram_mb()

        if loader is not None:
            try:
                loader.destroy_model()
            except Exception as e:
                logger.warning("force_model_cleanup: destroy_model error: %s", e)

        # Triple GC pass
        gc.collect()
        gc.collect()
        gc.collect()

        ram_after = self.get_ram_mb()
        freed = ram_before - ram_after

        logger.info(
            "Force cleanup: RAM %.1f → %.1f MB (freed %.1f MB)",
            ram_before, ram_after, freed,
        )
        return {
            "ram_before_mb": round(ram_before, 1),
            "ram_after_mb": round(ram_after, 1),
            "freed_mb": round(freed, 1),
        }

    def clear_all_tensors(self) -> None:
        """
        Interface preserved for compatibility.
        No-op since torch is removed — no tensors to clear.
        """
        gc.collect()

    @staticmethod
    def get_ram_mb() -> float:
        """Get current process RSS in MB."""
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / (1024 * 1024)

    @staticmethod
    def get_system_ram() -> dict:
        """Get system RAM info."""
        mem = psutil.virtual_memory()
        return {
            "total_gb": round(mem.total / 1e9, 1),
            "used_gb": round(mem.used / 1e9, 1),
            "available_gb": round(mem.available / 1e9, 1),
            "percent": mem.percent,
        }

    def clean_all(self) -> dict:
        gc_freed = self.clean_python_gc()
        cache_removed = self.clean_cache()
        return {
            "gc_freed": gc_freed,
            "cache_removed": cache_removed,
            "ram_mb": round(self.get_ram_mb(), 1),
        }
