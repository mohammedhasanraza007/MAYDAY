#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# M.A.Y.D.A.Y v4.5 — Linux/macOS Bootstrap Installer
# ═══════════════════════════════════════════════════════════════════════════
# Same flow as build.bat, adapted for Unix.
# L5 FIX: playwright install chromium --with-deps (Linux OK)
# L2 FIX: 3 separate model filenames
# L8 FIX: Launches bootstrap_ui.py (real PyQt6 GUI)
# ═══════════════════════════════════════════════════════════════════════════

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$ROOT/venv"
MODEL_DIR="$ROOT/models"
RUNTIME_DIR="$ROOT/runtime"
LOG_DIR="$ROOT/logs"
CACHE_DIR="$ROOT/cache"
WHEEL_CACHE="$RUNTIME_DIR/wheel_cache"

echo "[MAYDAY] Creating directory structure..."
mkdir -p "$MODEL_DIR" "$RUNTIME_DIR" "$LOG_DIR" "$CACHE_DIR" "$WHEEL_CACHE"
mkdir -p "$ROOT/projects" "$ROOT/lora_training_data" "$ROOT/lora_adapters" "$ROOT/crash_reports"

# ── Step 1: Detect Python ───────────────────────────────────────────────
echo "[MAYDAY] Checking for Python..."

PYTHON_CMD=""

# Check portable runtime first
if [ -x "$RUNTIME_DIR/python/bin/python3" ]; then
    echo "[MAYDAY] Found portable Python runtime."
    PYTHON_CMD="$RUNTIME_DIR/python/bin/python3"
elif command -v python3 &>/dev/null; then
    PY_VER=$(python3 --version 2>&1)
    echo "[MAYDAY] Found system $PY_VER"
    PYTHON_CMD="python3"
elif command -v python &>/dev/null; then
    PY_VER=$(python --version 2>&1)
    echo "[MAYDAY] Found system $PY_VER"
    PYTHON_CMD="python"
else
    echo "[MAYDAY] ERROR: Python not found. Install Python 3.11+."
    exit 1
fi

# ── Step 2: Create Virtual Environment ──────────────────────────────────
if [ ! -f "$VENV_DIR/bin/python" ]; then
    echo "[MAYDAY] Creating virtual environment..."
    $PYTHON_CMD -m venv "$VENV_DIR"
fi

VENV_PYTHON="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

# ── Step 3: Upgrade pip/setuptools/wheel (STEP 1 of 3) ─────────────────
echo "[MAYDAY] Step 1/3: Upgrading pip, setuptools, wheel..."
"$VENV_PIP" install --upgrade pip==24.0 setuptools==70.3.0 wheel==0.43.0

# ── Step 4: Install PyTorch CPU (STEP 2 of 3) ──────────────────────────
echo "[MAYDAY] Step 2/3: Installing PyTorch (CPU)..."
"$VENV_PIP" install torch==2.3.1 --index-url https://download.pytorch.org/whl/cpu

# ── Step 5: Install requirements.txt (STEP 3 of 3) ─────────────────────
echo "[MAYDAY] Step 3/3: Installing requirements..."
"$VENV_PIP" install -r "$ROOT/requirements.txt"

# ── Step 6: Install Playwright Chromium ─────────────────────────────────
# L5 FIX: --with-deps IS correct for Linux/macOS
echo "[MAYDAY] Installing Playwright Chromium..."
"$VENV_PYTHON" -m playwright install chromium --with-deps || {
    echo "[MAYDAY] WARNING: Playwright install failed. Browser tools will be unavailable."
}

# ── Step 7: Model Download Targets (L2 FIX) ─────────────────────────────
TIER1_MODEL="$MODEL_DIR/qwen35-4b.gguf"
TIER2_MODEL="$MODEL_DIR/qwen3-3b.gguf"
TIER3_MODEL="$MODEL_DIR/qwen25-1b.gguf"

echo "[MAYDAY] Model targets configured:"
echo "  Tier 1: $TIER1_MODEL (Qwen3.5-4B-Instruct)"
echo "  Tier 2: $TIER2_MODEL (Qwen3-3B-Instruct)"
echo "  Tier 3: $TIER3_MODEL (Qwen2.5-1.5B-Instruct)"

# ── Step 8: Post-install verification ───────────────────────────────────
echo "[MAYDAY] Running post-install verification..."

"$VENV_PYTHON" -c "import torch; print(f'torch {torch.__version__} OK')"
"$VENV_PYTHON" -c "from transformers import AutoTokenizer; print('transformers OK')"
"$VENV_PYTHON" -c "from PyQt6.QtWidgets import QApplication; print('PyQt6 OK')"
"$VENV_PYTHON" -c "import httpx; print('httpx OK')"
"$VENV_PYTHON" -c "from peft import LoraConfig; print('peft OK')"
"$VENV_PYTHON" -c "from cryptography.fernet import Fernet; print('cryptography OK')"

# ── Step 9: Launch Bootstrap UI (L8 FIX) ────────────────────────────────
echo "[MAYDAY] Launching M.A.Y.D.A.Y Bootstrap GUI..."
"$VENV_PYTHON" "$ROOT/bootstrap/bootstrap_ui.py" "$ROOT"

echo "[MAYDAY] Bootstrap complete."
