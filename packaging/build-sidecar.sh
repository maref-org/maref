#!/usr/bin/env bash
#
# Build MAREF Sidecar binary with PyInstaller.
#
# Usage:
#   bash packaging/build-sidecar.sh
#
# Output:
#   dist/maref-sidecar   (macOS/Linux)
#   dist/maref-sidecar.exe  (Windows)
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "==> MAREF Sidecar Binary Build"
echo "    Project root: $PROJECT_ROOT"
echo ""

# 1. Check prerequisites
echo "==> Checking prerequisites..."
command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 not found"; exit 1; }

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "    python3:  $(python3 --version)"

# Python 3.14 compatibility note: PyInstaller 6.21+ supports Python 3.14
if python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,14) else 1)" 2>/dev/null; then
    echo "    NOTE: Python 3.14 detected. PyInstaller 6.21+ is required."
    echo "    If the build fails, try: pip install 'pyinstaller>=6.21'"
fi
if python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,13) else 1)" 2>/dev/null; then
    echo "    NOTE: Python 3.13+ detected. The binary requires these PyInstaller-compatible versions."
fi

python3 -c "import PyInstaller" 2>/dev/null || {
    echo "PyInstaller not found. Installing..."
    pip install pyinstaller
}
echo "    pyinstaller: $(python3 -c 'import PyInstaller; print(PyInstaller.__version__)' 2>/dev/null || echo 'installed')"
echo ""

# 2. Install MAREF with sidecar dependencies (if not already installed)
echo "==> Ensuring MAREF + sidecar dependencies..."
pip install -e "$PROJECT_ROOT[sidecar,identity,sentinel]" 2>/dev/null || {
    echo "WARNING: pip install failed, proceeding with PYTHONPATH fallback"
}

# 3. Clean previous builds
echo "==> Cleaning previous builds..."
rm -rf "$PROJECT_ROOT/dist" "$PROJECT_ROOT/build" "$PROJECT_ROOT/*.spec"
echo ""

# 4. Build binary
echo "==> Building maref-sidecar binary..."
echo "    Mode: onefile"
echo "    Target: maref-sidecar"
echo ""

PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
    pyinstaller \
    --onefile \
    --name maref-sidecar \
    --distpath "$PROJECT_ROOT/dist" \
    --workpath "$PROJECT_ROOT/build" \
    --specpath "$PROJECT_ROOT/packaging" \
    --add-data "$PROJECT_ROOT/packaging/sidecar_boot.py:packaging" \
    --paths "$PROJECT_ROOT/src" \
    --hiddenimport cryptography \
    --hiddenimport cryptography.x509 \
    --hiddenimport uvicorn \
    --hiddenimport uvicorn.logging \
    --hiddenimport uvicorn.loops.auto \
    --hiddenimport uvicorn.protocols.http.auto \
    --hiddenimport uvicorn.protocols.websockets.auto \
    --hiddenimport uvicorn.middleware.wsgi \
    --hiddenimport fastapi \
    --hiddenimport fastapi.routing \
    --hiddenimport pydantic \
    --hiddenimport pydantic.deprecated \
    --hiddenimport starlette \
    --hiddenimport starlette.middleware.cors \
    --hiddenimport starlette.routing \
    --hiddenimport starlette.websockets \
    --hiddenimport sse_starlette \
    --hiddenimport websockets \
    --hiddenimport websockets.legacy.server \
    --hiddenimport maref \
    --hiddenimport maref.crypto.ed25519_keys \
    --hiddenimport maref.crypto.sm2 \
    --hiddenimport gmssl \
    --hiddenimport maref.governance \
    --hiddenimport maref.integration \
    --hiddenimport maref.integration.a2a_bridge \
    --hiddenimport maref.integration.a2a_server \
    --hiddenimport maref.integration.mcp_security \
    --hiddenimport maref.integration.mcp_server \
    --hiddenimport maref.integration.mcp_transport \
    --hiddenimport maref.observability \
    --hiddenimport maref.observability.guardrail_metrics \
    --hiddenimport maref.observability.metric_store \
    --hiddenimport maref.observability.security_headers_middleware \
    --hiddenimport maref.recursive \
    --hiddenimport maref.recursive.cost_tracker \
    --hiddenimport maref.obs \
    --hiddenimport sidecar \
    --hiddenimport sidecar.collector \
    --hiddenimport sidecar.exfiltration_probe \
    --hiddenimport sidecar.gaas_router \
    --hiddenimport sidecar.mcp_bridge \
    --hiddenimport sidecar.mcp_gateway \
    --hiddenimport sidecar.monitor \
    --hiddenimport sidecar.obs_bridge \
    --hiddenimport sidecar.server \
    --exclude-module tkinter \
    --exclude-module matplotlib \
    --exclude-module scipy \
    --exclude-module PIL \
    --exclude-module PyQt5 \
    --exclude-module PyQt6 \
    --exclude-module notebook \
    --exclude-module jupyter \
    --exclude-module ipython \
    --exclude-module pytest \
    --exclude-module torch \
    --exclude-module transformers \
    --exclude-module peft \
    --exclude-module datasets \
    --exclude-module accelerate \
    --exclude-module playwright \
    --exclude-module pyautogui \
    --exclude-module tensorflow \
    --exclude-module pandas \
    --exclude-module networkx \
    --exclude-module test \
    "$PROJECT_ROOT/packaging/sidecar_boot.py"

echo ""
echo "==> Build complete!"
BINARY="$PROJECT_ROOT/dist/maref-sidecar"
if [ -f "$BINARY" ]; then
    SIZE_MB=$(du -h "$BINARY" 2>/dev/null | cut -f1 || echo "unknown")
    echo "    Binary: $BINARY"
    echo "    Size:   $SIZE_MB"
    file "$BINARY"
else
    echo "    WARNING: Binary not found at $BINARY"
    ls -la "$PROJECT_ROOT/dist/" 2>/dev/null || true
fi
echo ""
echo "==> Run:"
echo "    ./dist/maref-sidecar --help"
echo "    ./dist/maref-sidecar --port 8000"
