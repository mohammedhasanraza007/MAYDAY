"""
Portable model downloader. Reads a manifest and fetches models into
ROOT/models/<model_id>/ . No hardcoded paths.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from huggingface_hub import snapshot_download


ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "models"
DEFAULT_MANIFEST = [
    {
        "repo_id": "Qwen/Qwen2.5-Coder-1.5B-Instruct",
        "local_dir": "qwen2_5_coder_1_5b",
    }
]


def main() -> int:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    manifest_file = ROOT / "models_manifest.json"
    manifest = (
        json.loads(manifest_file.read_text(encoding="utf-8"))
        if manifest_file.exists()
        else DEFAULT_MANIFEST
    )
    for entry in manifest:
        target = MODELS_DIR / entry["local_dir"]
        if target.exists() and any(target.iterdir()):
            print(f"[skip] {entry['local_dir']} already present")
            continue
        print(f"[get ] {entry['repo_id']} -> {target}")
        snapshot_download(
            repo_id=entry["repo_id"],
            local_dir=str(target),
            local_dir_use_symlinks=False,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
