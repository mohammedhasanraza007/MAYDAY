"""
M.A.Y.D.A.Y Physical Model Downloader CLI
=========================================
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(ROOT_DIR))

from model.downloader import ModelDownloader


def progress_bar(tier: int, pct: int, status: str) -> None:
    bar_len = 20
    filled_len = int(bar_len * pct / 100)
    bar = "=" * filled_len + "-" * (bar_len - filled_len)
    sys.stdout.write(f"\r[TIER {tier}] [{bar}] {pct}% | {status}    ")
    sys.stdout.flush()
    if pct >= 100:
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="MAYDAY Physical Model Downloader")
    parser.add_argument("--tier", type=int, choices=[1, 2, 3], help="Specific tier to download")
    parser.add_argument("--all", action="store_true", help="Download all tiers (continues on errors)")
    parser.add_argument("--force", action="store_true", help="Force re-download")

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    downloader = ModelDownloader()
    downloader.set_progress_callback(progress_bar)

    print("--- M.A.Y.D.A.Y Model Downloader ---")
    print(f"Target Directory: {downloader.model_dir}\n")

    any_ok = False
    try:
        if args.all:
            for t in (1, 2, 3):
                try:
                    downloader.download_tier(t, force=args.force)
                    any_ok = True
                except Exception as e:
                    print(f"\n[WARN] Tier {t} failed: {e}")
            if not any_ok:
                raise RuntimeError("All tier downloads failed.")
        elif args.tier:
            downloader.download_tier(args.tier, force=args.force)
            any_ok = True
        else:
            print("No tier specified — downloading Tier 1 (Qwen2.5-3B) then falling back...")
            for t in (1, 2, 3):
                try:
                    downloader.download_tier(t, force=args.force)
                    any_ok = True
                    break
                except Exception as e:
                    print(f"\n[WARN] Tier {t} failed: {e}")
            if not any_ok:
                raise RuntimeError("Could not download any tier.")

        print("\n[SUCCESS] Download pipeline finished.")
    except KeyboardInterrupt:
        print("\n[CANCELLED] Download aborted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n[FATAL] Download failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
