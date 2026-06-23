# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['/Volumes/1TB-M2/public/maref/packaging/sidecar_boot.py'],
    pathex=['/Volumes/1TB-M2/public/maref/src'],
    binaries=[],
    datas=[('/Volumes/1TB-M2/public/maref/packaging/sidecar_boot.py', 'packaging')],
    hiddenimports=['cryptography', 'cryptography.x509', 'uvicorn', 'uvicorn.logging', 'uvicorn.loops.auto', 'uvicorn.protocols.http.auto', 'uvicorn.protocols.websockets.auto', 'uvicorn.middleware.wsgi', 'fastapi', 'fastapi.routing', 'pydantic', 'pydantic.deprecated', 'starlette', 'starlette.middleware.cors', 'starlette.routing', 'starlette.websockets', 'sse_starlette', 'websockets', 'websockets.legacy.server', 'maref', 'maref.governance', 'maref.integration', 'maref.integration.a2a_bridge', 'maref.integration.a2a_server', 'maref.integration.mcp_security', 'maref.integration.mcp_server', 'maref.integration.mcp_transport', 'maref.observability', 'maref.observability.guardrail_metrics', 'maref.observability.metric_store', 'maref.observability.security_headers_middleware', 'maref.recursive', 'maref.recursive.cost_tracker', 'maref.obs', 'sidecar', 'sidecar.collector', 'sidecar.exfiltration_probe', 'sidecar.gaas_router', 'sidecar.mcp_bridge', 'sidecar.mcp_gateway', 'sidecar.monitor', 'sidecar.obs_bridge', 'sidecar.server'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'scipy', 'PIL', 'PyQt5', 'PyQt6', 'notebook', 'jupyter', 'ipython', 'pytest', 'torch', 'transformers', 'peft', 'datasets', 'accelerate', 'playwright', 'pyautogui', 'tensorflow', 'pandas', 'networkx', 'test'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='maref-sidecar',
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
