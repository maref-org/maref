# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for MAREF Sidecar binary.
#
# Build:
#   pyinstaller packaging/sidecar.spec
#
"""MAREF Sidecar PyInstaller specification."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = str(PROJECT_ROOT / "src")

block_cipher = None

a = Analysis(
    ["packaging/sidecar_boot.py"],
    pathex=[SRC_DIR],
    binaries=[],
    datas=[],
    hiddenimports=[
        # cryptography (required by maref.integration.a2a_secure_transport)
        "cryptography",
        "cryptography.x509",
        # FastAPI / uvicorn
        "uvicorn",
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.middleware",
        "uvicorn.middleware.wsgi",
        "fastapi",
        "fastapi.routing",
        "fastapi.openapi",
        "fastapi.openapi.utils",
        "pydantic",
        "pydantic.deprecated",
        "pydantic.json",
        "pydantic.schema",
        "starlette",
        "starlette.middleware",
        "starlette.middleware.cors",
        "starlette.routing",
        "starlette.schemas",
        "starlette.websockets",
        "sse_starlette",
        "websockets",
        "websockets.legacy",
        "websockets.legacy.server",
        # MAREF core
        "maref",
        "maref.governance",
        "maref.integration",
        "maref.integration.a2a_bridge",
        "maref.integration.a2a_server",
        "maref.integration.mcp_security",
        "maref.integration.mcp_server",
        "maref.integration.mcp_transport",
        "maref.observability",
        "maref.observability.guardrail_metrics",
        "maref.observability.metric_store",
        "maref.observability.security_headers_middleware",
        "maref.recursive",
        "maref.recursive.cost_tracker",
        "maref.obs",
        # Sidecar
        "sidecar",
        "sidecar.collector",
        "sidecar.exfiltration_probe",
        "sidecar.gaas_router",
        "sidecar.mcp_bridge",
        "sidecar.mcp_gateway",
        "sidecar.monitor",
        "sidecar.obs_bridge",
        "sidecar.server",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "scipy",
        "PIL",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        "notebook",
        "jupyter",
        "jupyter_client",
        "ipython",
        "nbformat",
        "nbconvert",
        "pytest",
        "nose",
        "torch",
        "transformers",
        "peft",
        "datasets",
        "accelerate",
        "playwright",
        "pyautogui",
        "PyAutoGUI",
        "tensorflow",
        "pandas",
        "networkx",
        "onnx",
        "onnxruntime",
        "_tkinter",
        "test",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="maref-sidecar",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
