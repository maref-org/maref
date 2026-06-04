#!/usr/bin/env bash
set -euo pipefail
echo "[fix-pythonpath] Uninstalling global maref editable install..."
python3 -m pip uninstall maref -y --break-system-packages 2>/dev/null || true
echo "[fix-pythonpath] Installing maref from current repo..."
.venv/bin/pip install -e ".[dev]" --no-build-isolation
echo "[fix-pythonpath] Verifying..."
.venv/bin/python -c "from maref.executor.budget import BudgetTracker; print('OK')"
